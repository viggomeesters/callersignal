from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from callersignal.storage import (
    EntityKind,
    LocalStore,
    PrivacyBoundaryError,
    RecordNotFound,
)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 29, 10, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(clock: Clock) -> LocalStore:
    return LocalStore(clock=clock)


def test_record_and_outbox_commit_atomically(store: LocalStore) -> None:
    with store.transaction() as transaction:
        transaction.put(
            kind=EntityKind.WATCH,
            record_id="watch_synthetic_example",
            payload={"state": "active", "contact_ref": "contact_digest_example"},
            dedupe_key="watch:synthetic-example",
        )
        transaction.enqueue(
            message_id="msg_synthetic_example",
            event_type="watch.created",
            aggregate_kind=EntityKind.WATCH,
            aggregate_id="watch_synthetic_example",
            payload={"template": "watch_confirmation"},
            idempotency_key="watch-created:synthetic-example",
        )

    assert store.get(EntityKind.WATCH, "watch_synthetic_example").version == 1
    assert [message.message_id for message in store.pending_outbox()] == [
        "msg_synthetic_example"
    ]


def test_privacy_failure_rolls_back_record_and_outbox(store: LocalStore) -> None:
    with pytest.raises(PrivacyBoundaryError):
        with store.transaction() as transaction:
            transaction.put(
                kind=EntityKind.REPORT,
                record_id="report_synthetic_example",
                payload={"state": "pending"},
            )
            transaction.enqueue(
                message_id="msg_invalid_private_payload",
                event_type="report.created",
                aggregate_kind=EntityKind.REPORT,
                aggregate_id="report_synthetic_example",
                payload={"requester_ip": "192.0.2.1"},
                idempotency_key="invalid-private-payload",
            )

    with pytest.raises(RecordNotFound):
        store.get(EntityKind.REPORT, "report_synthetic_example")
    assert store.pending_outbox() == []


def test_correction_is_versioned_and_audited(store: LocalStore) -> None:
    with store.transaction() as transaction:
        transaction.put(
            kind=EntityKind.CAMPAIGN,
            record_id="campaign_synthetic_example",
            payload={"status": "monitoring"},
        )

    with store.transaction() as transaction:
        corrected = transaction.correct(
            kind=EntityKind.CAMPAIGN,
            record_id="campaign_synthetic_example",
            payload={"status": "active"},
            expected_version=1,
            reason="evidence_corroborated",
        )

    assert corrected.version == 2
    assert corrected.payload == {"status": "active"}
    assert [receipt.action for receipt in store.audit_receipts()] == [
        "created",
        "corrected",
    ]
    assert store.audit_receipts()[-1].reason == "evidence_corroborated"


def test_retention_purge_deletes_expired_records_with_audit_receipt(
    store: LocalStore,
    clock: Clock,
) -> None:
    with store.transaction() as transaction:
        transaction.put(
            kind=EntityKind.REPORT,
            record_id="report_retention_example",
            payload={"state": "pending"},
            expires_at=clock.now + timedelta(days=30),
        )
    clock.advance(timedelta(days=30, seconds=1))

    receipts = store.purge_expired()

    assert len(receipts) == 1
    assert receipts[0].action == "deleted"
    assert receipts[0].reason == "retention_expired"
    with pytest.raises(RecordNotFound):
        store.get(EntityKind.REPORT, "report_retention_example")


@pytest.mark.parametrize("kind", list(EntityKind))
def test_every_entity_kind_is_deduplicated_by_explicit_key(
    store: LocalStore,
    kind: EntityKind,
) -> None:
    with store.transaction() as transaction:
        first = transaction.put(
            kind=kind,
            record_id=f"{kind.value}_first",
            payload={"state": "synthetic"},
            dedupe_key=f"{kind.value}:same-subject",
        )
    with store.transaction() as transaction:
        duplicate = transaction.put(
            kind=kind,
            record_id=f"{kind.value}_duplicate",
            payload={"state": "should_not_replace"},
            dedupe_key=f"{kind.value}:same-subject",
        )

    assert duplicate == first
    assert [record.record_id for record in store.list_records(kind)] == [first.record_id]


def test_outbox_delivery_is_idempotent_and_retryable(
    store: LocalStore,
    clock: Clock,
) -> None:
    with store.transaction() as transaction:
        transaction.put(
            kind=EntityKind.WATCH,
            record_id="watch_delivery_example",
            payload={"state": "active"},
        )
        first = transaction.enqueue(
            message_id="msg_delivery_example",
            event_type="watch.changed",
            aggregate_kind=EntityKind.WATCH,
            aggregate_id="watch_delivery_example",
            payload={"template": "material_change"},
            idempotency_key="watch-change:state-v2",
        )
        duplicate = transaction.enqueue(
            message_id="msg_duplicate_delivery",
            event_type="watch.changed",
            aggregate_kind=EntityKind.WATCH,
            aggregate_id="watch_delivery_example",
            payload={"template": "must_not_replace"},
            idempotency_key="watch-change:state-v2",
        )
    assert duplicate == first

    failed = store.record_outbox_attempt(first.message_id, delivered=False)
    assert failed.attempts == 1
    assert failed.delivered_at is None
    assert len(store.pending_outbox()) == 1

    clock.advance(timedelta(seconds=1))
    delivered = store.record_outbox_attempt(first.message_id, delivered=True)
    assert delivered.attempts == 2
    assert delivered.delivered_at == clock.now
    assert store.pending_outbox() == []
