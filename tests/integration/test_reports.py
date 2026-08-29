from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from callersignal.reports import (
    ReportAuthorizationError,
    ReportNotFound,
    ReportPolicy,
    ReportRejected,
    ReportService,
)

ROOT = Path(__file__).resolve().parents[2]


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 29, 8, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def _e164() -> str:
    return "+1" + "202" + "555" + "0147"


def _phone_number() -> dict:
    return {
        "schema_version": "1.0.0",
        "kind": "phone_number",
        "raw_input": "202-555-0147",
        "origin_region": "US",
        "interpretation": {
            "input_mode": "national",
            "region_source": "explicit_origin_region",
            "status": "valid",
            "reason_codes": ["parsed_with_explicit_region"],
        },
        "canonical": {
            "e164": _e164(),
            "country_calling_code": "1",
            "region": "US",
            "national_significant_number": "202" + "555" + "0147",
            "number_type": "fixed_or_mobile",
        },
        "presentation": {
            "international": "+1 " + "202-555-0147",
            "national": "(202) 555-0147",
        },
    }


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def service(clock: Clock) -> ReportService:
    return ReportService(
        clock=clock,
        secret=b"synthetic-test-secret",
        policy=ReportPolicy(
            retention=timedelta(days=30),
            rate_window=timedelta(hours=1),
            actor_limit=3,
            distinct_actor_limit=3,
        ),
    )


def _submit(
    service: ReportService,
    *,
    actor_token: str = "synthetic-actor-a",
    categories: tuple[str, ...] = ("impersonation_attempt",),
):
    return service.submit(
        displayed_number=_phone_number(),
        actor_token=actor_token,
        categories=categories,
        channel="voice",
        contact_outcome="answered",
        occurred_at=datetime(2026, 8, 29, 7, 55, tzinfo=UTC),
        submission_channel="web",
        reporter_region="US",
    )


def test_submission_is_schema_valid_unverified_displayed_number_observation(
    service: ReportService,
) -> None:
    receipt = _submit(service)
    report = service.get_for_moderation(receipt.report_id)

    schemas = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in (ROOT / "schemas").glob("*.schema.json")
    }
    from referencing import Registry, Resource

    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )
    Draft202012Validator(
        schemas["call-report.schema.json"],
        registry=registry,
        format_checker=FormatChecker(),
    ).validate(report)

    assert receipt.created is True
    assert report["subject_semantics"] == "call_displayed_number"
    assert report["moderation"]["verification_status"] == "unverified_observation"
    assert report["privacy"]["contains_free_text"] is False
    assert "actor" not in json.dumps(report).lower()


def test_actor_rate_limit_rejects_excess_reports_without_storing_raw_actor(
    service: ReportService,
    clock: Clock,
) -> None:
    for categories in (("unwanted",), ("silent_call",), ("robocall",)):
        _submit(service, categories=categories)

    with pytest.raises(ReportRejected) as rejected:
        _submit(service, categories=("payment_request",))

    assert rejected.value.code == "actor_rate_limit"
    assert service.privacy_snapshot() == {
        "active_reports": 3,
        "raw_actor_tokens": 0,
        "raw_requester_ips": 0,
        "raw_lookup_histories": 0,
    }

    clock.advance(timedelta(hours=1, seconds=1))
    assert _submit(service, categories=("credential_request",)).created is True


def test_distinct_actor_threshold_quarantines_possible_brigading(
    service: ReportService,
) -> None:
    for actor in ("synthetic-actor-a", "synthetic-actor-b", "synthetic-actor-c"):
        _submit(service, actor_token=actor)

    with pytest.raises(ReportRejected) as rejected:
        _submit(service, actor_token="synthetic-actor-d")

    assert rejected.value.code == "brigading_threshold"
    assert service.privacy_snapshot()["active_reports"] == 3


def test_reporter_can_correct_structured_fields_with_receipt_proof(
    service: ReportService,
) -> None:
    receipt = _submit(service)

    with pytest.raises(ReportAuthorizationError):
        service.correct(
            report_id=receipt.report_id,
            receipt_id=receipt.receipt_id,
            actor_token="synthetic-other-actor",
            categories=("payment_request",),
        )

    corrected = service.correct(
        report_id=receipt.report_id,
        receipt_id=receipt.receipt_id,
        actor_token="synthetic-actor-a",
        categories=("payment_request", "credential_request"),
    )

    assert corrected["observation"]["categories"] == [
        "credential_request",
        "payment_request",
    ]
    assert corrected["moderation"] == {
        "workflow_status": "pending",
        "verification_status": "unverified_observation",
        "reason_codes": ["reporter_correction"],
    }


def test_reporter_deletion_removes_report_and_returns_minimized_receipt(
    service: ReportService,
) -> None:
    receipt = _submit(service)

    deleted = service.delete(
        report_id=receipt.report_id,
        receipt_id=receipt.receipt_id,
        actor_token="synthetic-actor-a",
    )

    assert deleted.report_id == receipt.report_id
    assert deleted.reason == "reporter_request"
    assert deleted.deletion_id.startswith("del_")
    with pytest.raises(ReportNotFound):
        service.get_for_moderation(receipt.report_id)
    assert service.privacy_snapshot()["active_reports"] == 0


def test_retention_expiry_purges_report_content(
    service: ReportService,
    clock: Clock,
) -> None:
    receipt = _submit(service)
    clock.advance(timedelta(days=30, seconds=1))

    deletions = service.purge_expired()

    assert len(deletions) == 1
    assert deletions[0].report_id == receipt.report_id
    assert deletions[0].reason == "retention_expired"
    with pytest.raises(ReportNotFound):
        service.get_for_moderation(receipt.report_id)


def test_moderation_can_accept_observation_without_turning_it_into_identity_proof(
    service: ReportService,
) -> None:
    receipt = _submit(service)

    moderated = service.moderate(
        report_id=receipt.report_id,
        decision="accept_observation",
        reason_codes=("structured_direct_observation",),
    )

    assert moderated["moderation"] == {
        "workflow_status": "accepted_observation",
        "verification_status": "unverified_observation",
        "reason_codes": ["structured_direct_observation"],
    }
    assert moderated["subject_semantics"] == "call_displayed_number"


def test_exact_resubmission_is_deduplicated(service: ReportService) -> None:
    first = _submit(service)
    second = _submit(service)

    assert second == type(first)(
        report_id=first.report_id,
        receipt_id=first.receipt_id,
        created=False,
    )
    assert service.privacy_snapshot()["active_reports"] == 1


def test_unstructured_or_invalid_submission_is_rejected_before_storage(
    service: ReportService,
) -> None:
    with pytest.raises(ReportRejected) as rejected:
        _submit(service, categories=("free_text_accusation",))

    assert rejected.value.code == "invalid_categories"
    assert service.privacy_snapshot()["active_reports"] == 0


def test_expired_report_fails_closed_even_before_scheduled_purge(
    service: ReportService,
    clock: Clock,
) -> None:
    receipt = _submit(service)
    clock.advance(timedelta(days=30, seconds=1))

    with pytest.raises(ReportNotFound):
        service.get_for_moderation(receipt.report_id)

    assert service.privacy_snapshot()["active_reports"] == 0
