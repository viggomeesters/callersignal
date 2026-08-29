from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from callersignal.organizations import (
    OrganizationPolicy,
    OrganizationService,
    OrganizationVerificationFailed,
)
from callersignal.storage import EntityKind, LocalStore, RecordNotFound

ROOT = Path(__file__).resolve().parents[2]


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 29, 11, tzinfo=UTC)

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
def service(store: LocalStore, clock: Clock) -> OrganizationService:
    return OrganizationService(
        store=store,
        clock=clock,
        secret=b"synthetic-organization-secret",
        code_factory=lambda: "842615",
        policy=OrganizationPolicy(
            challenge_ttl=timedelta(minutes=20),
            verification_ttl=timedelta(days=365),
            max_attempts=3,
            max_portfolio_size=20,
        ),
    )


def _number(suffix: str = "0147") -> str:
    return "+1" + "202" + "555" + suffix


def _request(
    service: OrganizationService,
    *,
    name: str = "Example Safety Bank",
    domain: str = "example.test",
    contact: str = "security@example.test",
    numbers: tuple[str, ...] = (_number(),),
):
    return service.request_verification(
        display_name=name,
        domain=domain,
        administrator_contact=contact,
        jurisdiction="US",
        declared_numbers=numbers,
    )


def _challenge(store: LocalStore, domain: str = "example.test") -> dict:
    return next(
        message.payload
        for message in store.pending_outbox()
        if message.event_type == "organization.verify" and message.payload["domain"] == domain
    )


def test_portfolio_is_published_only_after_explicit_control_challenge(
    service: OrganizationService,
    store: LocalStore,
) -> None:
    response = _request(service)
    challenge = _challenge(store)

    assert response.message == (
        "If the declaration is eligible, verification instructions will be sent."
    )
    assert service.public_portfolio(challenge["organization_id"]) is None

    service.confirm_verification(
        challenge_id=challenge["challenge_id"],
        code=challenge["verification_code"],
    )
    portfolio = service.public_portfolio(challenge["organization_id"])
    assert portfolio is not None

    schema = json.loads(
        (ROOT / "schemas" / "organization-portfolio.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(portfolio)
    assert portfolio["verification"]["claim_scope"] == (
        "organization_declared_official_contact_routes"
    )
    assert portfolio["numbers"][0]["canonical_e164"] == _number()
    assert "origin" in portfolio["limitations"][0].lower()
    assert "spoof" in " ".join(portfolio["limitations"]).lower()
    assert "administrator" not in json.dumps(portfolio).lower()


def test_challenge_expiry_attempt_limit_and_replay_fail_closed(
    service: OrganizationService,
    store: LocalStore,
    clock: Clock,
) -> None:
    _request(service)
    challenge = _challenge(store)
    for _ in range(3):
        with pytest.raises(OrganizationVerificationFailed):
            service.confirm_verification(
                challenge_id=challenge["challenge_id"],
                code="000000",
            )
    with pytest.raises(OrganizationVerificationFailed):
        service.confirm_verification(
            challenge_id=challenge["challenge_id"],
            code=challenge["verification_code"],
        )

    _request(
        service,
        name="Second Example Bank",
        domain="second.example",
        contact="security@second.example",
        numbers=(_number("0148"),),
    )
    expiring = _challenge(store, "second.example")
    clock.advance(timedelta(minutes=21))
    with pytest.raises(OrganizationVerificationFailed):
        service.confirm_verification(
            challenge_id=expiring["challenge_id"],
            code=expiring["verification_code"],
        )

    _request(
        service,
        name="Third Example Bank",
        domain="third.example",
        contact="security@third.example",
        numbers=(_number("0149"),),
    )
    replayed = _challenge(store, "third.example")
    service.confirm_verification(
        challenge_id=replayed["challenge_id"],
        code=replayed["verification_code"],
    )
    with pytest.raises(OrganizationVerificationFailed):
        service.confirm_verification(
            challenge_id=replayed["challenge_id"],
            code=replayed["verification_code"],
        )


def test_portfolio_changes_are_audited_and_number_conflicts_fail_closed(
    service: OrganizationService,
    store: LocalStore,
) -> None:
    _request(service)
    first_challenge = _challenge(store)
    service.confirm_verification(
        challenge_id=first_challenge["challenge_id"],
        code=first_challenge["verification_code"],
    )

    _request(
        service,
        name="Conflicting Example Bank",
        domain="conflict.example",
        contact="security@conflict.example",
        numbers=(_number(),),
    )
    conflict = _challenge(store, "conflict.example")
    with pytest.raises(OrganizationVerificationFailed):
        service.confirm_verification(
            challenge_id=conflict["challenge_id"],
            code=conflict["verification_code"],
        )
    assert service.public_portfolio(conflict["organization_id"]) is None
    conflict_record = store.get(
        EntityKind.ORGANIZATION_PORTFOLIO,
        conflict["organization_id"],
    )
    assert conflict_record.payload["status"] == "conflict_review"
    assert conflict_record.payload["correction"]["reason_codes"] == [
        "number_declaration_conflict"
    ]

    updated = service.update_portfolio(
        organization_id=first_challenge["organization_id"],
        administrator_contact="security@example.test",
        declared_numbers=(_number("0148"), _number("0149")),
    )
    assert [item["canonical_e164"] for item in updated["numbers"]] == [
        _number("0148"),
        _number("0149"),
    ]
    assert updated["correction"]["status"] == "corrected"
    assert store.audit_receipts()[-1].reason == "portfolio_updated"

    conflict_resolved = service.resolve_appeal(
        organization_id=conflict["organization_id"],
        decision="reinstate",
        reason_code="number_conflict_resolved",
    )
    assert conflict_resolved["status"] == "verified"
    assert service.public_portfolio(conflict["organization_id"]) is not None
    with pytest.raises(OrganizationVerificationFailed):
        service.confirm_verification(
            challenge_id=conflict["challenge_id"],
            code=conflict["verification_code"],
        )


def test_impersonation_review_appeal_expiry_and_deletion_are_fail_closed(
    service: OrganizationService,
    store: LocalStore,
    clock: Clock,
) -> None:
    _request(service)
    challenge = _challenge(store)
    service.confirm_verification(
        challenge_id=challenge["challenge_id"],
        code=challenge["verification_code"],
    )
    organization_id = str(challenge["organization_id"])

    service.report_impersonation(
        organization_id=organization_id,
        reason_code="impersonation_report_under_review",
    )
    assert service.public_portfolio(organization_id) is None
    suspended = store.get(EntityKind.ORGANIZATION_PORTFOLIO, organization_id)
    assert suspended.payload["status"] == "suspended"
    assert suspended.payload["correction"]["status"] == "under_review"

    resolved = service.resolve_appeal(
        organization_id=organization_id,
        decision="reinstate",
        reason_code="organization_control_reconfirmed",
    )
    assert resolved["status"] == "verified"
    assert resolved["correction"]["status"] == "appeal_resolved"

    clock.advance(timedelta(days=365, seconds=1))
    assert service.expire_due() == 1
    assert service.public_portfolio(organization_id) is None

    receipt = service.delete_portfolio(
        organization_id=organization_id,
        administrator_contact="security@example.test",
    )
    assert receipt.action == "deleted"
    assert receipt.reason == "organization_deletion"
    with pytest.raises(RecordNotFound):
        store.get(EntityKind.ORGANIZATION_PORTFOLIO, organization_id)
