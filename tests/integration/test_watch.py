from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from callersignal.storage import EntityKind, LocalStore, RecordNotFound
from callersignal.watch import (
    WatchPolicy,
    WatchService,
    WatchVerificationFailed,
)

ROOT = Path(__file__).resolve().parents[2]


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


@pytest.fixture
def service(store: LocalStore, clock: Clock) -> WatchService:
    return WatchService(
        store=store,
        clock=clock,
        secret=b"synthetic-watch-secret",
        code_factory=lambda: "731924",
        policy=WatchPolicy(
            challenge_ttl=timedelta(minutes=15),
            watch_ttl=timedelta(days=365),
            request_window=timedelta(hours=1),
            max_requests=3,
            max_attempts=3,
        ),
    )


def _e164() -> str:
    return "+1" + "202" + "555" + "0147"


def _request(service: WatchService):
    return service.request_watch(
        displayed_e164=_e164(),
        contact="person@example.test",
        consent_policy_version="1.0.0",
    )


def _challenge_from_outbox(store: LocalStore) -> dict:
    message = next(
        item for item in store.pending_outbox() if item.event_type == "watch.verify"
    )
    return message.payload


def _activate(service: WatchService, store: LocalStore) -> str:
    _request(service)
    challenge = _challenge_from_outbox(store)
    service.confirm_watch(
        challenge_id=challenge["challenge_id"],
        code=challenge["verification_code"],
    )
    return str(challenge["watch_id"])


def test_watch_is_private_and_inactive_until_contact_challenge_passes(
    service: WatchService,
    store: LocalStore,
) -> None:
    response = _request(service)

    assert response.message == (
        "If the request is eligible, verification instructions will be sent."
    )
    assert service.list_for_contact("person@example.test") == []
    challenge = _challenge_from_outbox(store)
    watch = store.get(EntityKind.WATCH, challenge["watch_id"]).payload

    schema = json.loads(
        (ROOT / "schemas" / "watch-subscription.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(watch)
    persisted = json.dumps(
        {
            "watch": watch,
            "challenge": store.get(
                EntityKind.VERIFICATION_CHALLENGE,
                challenge["challenge_id"],
            ).payload,
            "outbox": challenge,
        }
    )
    assert _e164() not in persisted
    assert "person@example.test" not in persisted
    assert watch["status"] == "pending_verification"

    service.confirm_watch(
        challenge_id=challenge["challenge_id"],
        code=challenge["verification_code"],
    )

    listed = service.list_for_contact("person@example.test")
    assert len(listed) == 1
    assert listed[0]["status"] == "active"
    assert listed[0]["verification"]["status"] == "verified"


def test_failed_or_expired_challenge_never_activates_watch(
    service: WatchService,
    store: LocalStore,
    clock: Clock,
) -> None:
    _request(service)
    challenge = _challenge_from_outbox(store)

    for _ in range(3):
        with pytest.raises(WatchVerificationFailed):
            service.confirm_watch(challenge_id=challenge["challenge_id"], code="000000")
    with pytest.raises(WatchVerificationFailed):
        service.confirm_watch(
            challenge_id=challenge["challenge_id"],
            code=challenge["verification_code"],
        )
    assert service.list_for_contact("person@example.test") == []

    clock.advance(timedelta(minutes=16))
    with pytest.raises(WatchVerificationFailed):
        service.confirm_watch(
            challenge_id=challenge["challenge_id"],
            code=challenge["verification_code"],
        )


def test_request_rate_limit_and_existing_watch_use_same_generic_response(
    service: WatchService,
    store: LocalStore,
) -> None:
    expected = _request(service)
    duplicate = _request(service)
    for suffix in ("0148", "0149"):
        service.request_watch(
            displayed_e164="+1" + "202" + "555" + suffix,
            contact="person@example.test",
            consent_policy_version="1.0.0",
        )
    rate_limited = service.request_watch(
        displayed_e164="+1" + "202" + "555" + "0150",
        contact="person@example.test",
        consent_policy_version="1.0.0",
    )
    invalid = service.request_watch(
        displayed_e164="invalid",
        contact="person@example.test",
        consent_policy_version="1.0.0",
    )

    assert duplicate == rate_limited == invalid == expected
    assert len(
        store.list_records(EntityKind.VERIFICATION_CHALLENGE)
    ) == 3


def test_only_material_changes_enqueue_idempotent_caveated_notification(
    service: WatchService,
    store: LocalStore,
) -> None:
    watch_id = _activate(service, store)

    first = service.notify_if_material(
        watch_id=watch_id,
        campaign_id="cmp_synthetic_example",
        risk_state="elevated_signals",
        campaign_status="active",
        correction_status="none",
        recommended_action="avoid_sensitive_actions",
    )
    duplicate = service.notify_if_material(
        watch_id=watch_id,
        campaign_id="cmp_synthetic_example",
        risk_state="elevated_signals",
        campaign_status="active",
        correction_status="none",
        recommended_action="avoid_sensitive_actions",
    )

    assert first.enqueued is True
    assert duplicate == type(first)(enqueued=False, reason="unchanged")
    change_messages = [
        message
        for message in store.pending_outbox()
        if message.event_type == "watch.material_change"
    ]
    assert len(change_messages) == 1
    payload = change_messages[0].payload
    assert payload["risk_state"] == "elevated_signals"
    assert "safe" in payload["no_safety_caveat"].lower()
    assert "accus" not in json.dumps(payload).lower()
    assert "lookup" not in json.dumps(payload).lower()


def test_verified_owner_can_correct_revoke_and_delete_private_watch(
    service: WatchService,
    store: LocalStore,
) -> None:
    watch_id = _activate(service, store)
    before = store.get(EntityKind.WATCH, watch_id).payload

    corrected = service.correct_watch(
        watch_id=watch_id,
        contact="person@example.test",
        displayed_e164="+1" + "202" + "555" + "0148",
    )

    assert corrected["subject"]["number_ref"] != before["subject"]["number_ref"]
    assert corrected["correction"] == {
        "status": "corrected",
        "updated_at": "2026-08-29T10:00:00Z",
        "reason_codes": ["subscriber_scope_correction"],
    }
    assert "0148" not in json.dumps(corrected)

    revoked = service.revoke_watch(
        watch_id=watch_id,
        contact="person@example.test",
    )
    assert revoked["status"] == "revoked"
    assert service.list_for_contact("person@example.test") == []
    assert service.notify_if_material(
        watch_id=watch_id,
        campaign_id="cmp_synthetic_example",
        risk_state="official_warning",
        campaign_status="active",
        correction_status="none",
        recommended_action="avoid_and_verify",
    ).reason == "inactive"

    receipt = service.delete_watch(
        watch_id=watch_id,
        contact="person@example.test",
    )
    assert receipt.action == "deleted"
    assert receipt.reason == "subscriber_deletion"
    with pytest.raises(RecordNotFound):
        store.get(EntityKind.WATCH, watch_id)


def test_consent_expiry_and_delivery_outage_fail_closed(
    service: WatchService,
    store: LocalStore,
    clock: Clock,
) -> None:
    _request(service)
    verification_message = next(
        message for message in store.pending_outbox() if message.event_type == "watch.verify"
    )
    failed_delivery = store.record_outbox_attempt(
        verification_message.message_id,
        delivered=False,
    )
    assert failed_delivery.attempts == 1
    assert failed_delivery.delivered_at is None
    assert service.list_for_contact("person@example.test") == []

    challenge = verification_message.payload
    service.confirm_watch(
        challenge_id=challenge["challenge_id"],
        code=challenge["verification_code"],
    )
    watch_id = str(challenge["watch_id"])
    clock.advance(timedelta(days=365, seconds=1))

    assert service.expire_due() == 1
    expired = store.get(EntityKind.WATCH, watch_id).payload
    assert expired["status"] == "expired"
    assert service.list_for_contact("person@example.test") == []
    assert service.notify_if_material(
        watch_id=watch_id,
        campaign_id="cmp_synthetic_example",
        risk_state="elevated_signals",
        campaign_status="active",
        correction_status="none",
        recommended_action="avoid_sensitive_actions",
    ).reason == "inactive"
