"""Challenge-gated organisation declarations with spoofing-safe public projection."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from callersignal.storage import DataStore, EntityKind, RecordNotFound

_GENERIC_MESSAGE = "If the declaration is eligible, verification instructions will be sent."
_E164 = re.compile(r"^\+[1-9][0-9]{1,14}$")
_DOMAIN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


class OrganizationVerificationFailed(ValueError):
    def __init__(self) -> None:
        super().__init__("verification_failed")


@dataclass(frozen=True)
class OrganizationPolicy:
    challenge_ttl: timedelta
    verification_ttl: timedelta
    max_attempts: int
    max_portfolio_size: int


@dataclass(frozen=True)
class OrganizationRequestResult:
    message: str = _GENERIC_MESSAGE


class OrganizationService:
    def __init__(
        self,
        *,
        store: DataStore,
        clock: Callable[[], datetime],
        secret: bytes,
        code_factory: Callable[[], str],
        policy: OrganizationPolicy,
    ) -> None:
        if len(secret) < 16:
            raise ValueError("organization secret must contain at least 16 bytes")
        self._store = store
        self._clock = clock
        self._secret = secret
        self._code_factory = code_factory
        self._policy = policy

    def request_verification(
        self,
        *,
        display_name: str,
        domain: str,
        administrator_contact: str,
        jurisdiction: str,
        declared_numbers: Sequence[str],
    ) -> OrganizationRequestResult:
        now = self._clock()
        domain = domain.strip().lower()
        contact = administrator_contact.strip().lower()
        numbers = sorted(set(declared_numbers))
        _validate_declaration(
            display_name=display_name,
            domain=domain,
            contact=contact,
            jurisdiction=jurisdiction,
            numbers=numbers,
            max_portfolio_size=self._policy.max_portfolio_size,
        )
        organization_id = f"org_{self._digest(f'organization:{domain}')[:24]}"
        try:
            self._store.get(EntityKind.ORGANIZATION_PORTFOLIO, organization_id)
        except RecordNotFound:
            pass
        else:
            return OrganizationRequestResult()
        administrator_ref = (
            f"admin_{self._digest(f'administrator:{contact}')[:32]}"
        )
        code = self._code_factory()
        if re.fullmatch(r"[0-9]{6}", code) is None:
            raise ValueError("verification code factory must return six digits")
        challenge_id = (
            "challenge_"
            + self._digest(f"organization:{organization_id}:{_timestamp(now)}")[:24]
        )
        challenge_expires_at = now + self._policy.challenge_ttl
        organization = {
            "organization_id": organization_id,
            "display_name": display_name.strip(),
            "domain": domain,
            "jurisdiction": jurisdiction,
            "status": "pending_verification",
            "administrator_ref": administrator_ref,
            "numbers": [
                {
                    "canonical_e164": number,
                    "label": "Declared official contact",
                    "status": "active",
                    "declared_at": _timestamp(now),
                }
                for number in numbers
            ],
            "verification": {
                "method": "domain_email_challenge",
                "verified_at": None,
                "valid_until": None,
                "claim_scope": "organization_declared_official_contact_routes",
            },
            "correction": {
                "status": "none",
                "updated_at": None,
                "reason_codes": [],
            },
            "updated_at": _timestamp(now),
        }
        challenge = {
            "purpose": "organization_control",
            "organization_id": organization_id,
            "administrator_ref": administrator_ref,
            "challenge_digest": self._digest(f"code:{challenge_id}:{code}"),
            "status": "pending",
            "attempts": 0,
            "max_attempts": self._policy.max_attempts,
            "expires_at": _timestamp(challenge_expires_at),
        }
        with self._store.transaction() as transaction:
            transaction.put(
                kind=EntityKind.ORGANIZATION_PORTFOLIO,
                record_id=organization_id,
                payload=organization,
                dedupe_key=domain,
            )
            transaction.put(
                kind=EntityKind.VERIFICATION_CHALLENGE,
                record_id=challenge_id,
                payload=challenge,
                expires_at=challenge_expires_at,
                dedupe_key=f"organization-verification:{organization_id}",
            )
            transaction.enqueue(
                message_id=f"msg_{self._digest(f'organization-verify:{challenge_id}')[:24]}",
                event_type="organization.verify",
                aggregate_kind=EntityKind.VERIFICATION_CHALLENGE,
                aggregate_id=challenge_id,
                payload={
                    "template": "organization_verification",
                    "domain": domain,
                    "administrator_ref": administrator_ref,
                    "organization_id": organization_id,
                    "challenge_id": challenge_id,
                    "verification_code": code,
                    "expires_at": _timestamp(challenge_expires_at),
                },
                idempotency_key=f"organization-verify:{challenge_id}",
            )
        return OrganizationRequestResult()

    def confirm_verification(self, *, challenge_id: str, code: str) -> None:
        try:
            challenge = self._store.get(EntityKind.VERIFICATION_CHALLENGE, challenge_id)
        except RecordNotFound as exc:
            raise OrganizationVerificationFailed() from exc
        challenge_payload = deepcopy(challenge.payload)
        supplied = self._digest(f"code:{challenge_id}:{code}")
        if challenge_payload["status"] != "pending" or not hmac.compare_digest(
            str(challenge_payload["challenge_digest"]), supplied
        ):
            self._record_failed_attempt(challenge, challenge_payload)
            raise OrganizationVerificationFailed()
        organization_id = str(challenge_payload["organization_id"])
        try:
            organization = self._store.get(
                EntityKind.ORGANIZATION_PORTFOLIO,
                organization_id,
            )
        except RecordNotFound as exc:
            raise OrganizationVerificationFailed() from exc
        if self._conflicting_organization(organization_id, organization.payload["numbers"]):
            self._mark_conflict(organization, challenge_id=challenge_id)
            raise OrganizationVerificationFailed()
        now = self._clock()
        payload = deepcopy(organization.payload)
        payload["status"] = "verified"
        payload["verification"]["verified_at"] = _timestamp(now)
        payload["verification"]["valid_until"] = _timestamp(
            now + self._policy.verification_ttl
        )
        payload["updated_at"] = _timestamp(now)
        with self._store.transaction() as transaction:
            transaction.correct(
                kind=EntityKind.ORGANIZATION_PORTFOLIO,
                record_id=organization_id,
                payload=payload,
                expected_version=organization.version,
                reason="organization_control_verified",
            )
            transaction.delete(
                kind=EntityKind.VERIFICATION_CHALLENGE,
                record_id=challenge_id,
                reason="challenge_consumed",
            )
            transaction.enqueue(
                message_id=f"msg_{self._digest(f'organization-verified:{organization_id}')[:24]}",
                event_type="organization.verified",
                aggregate_kind=EntityKind.ORGANIZATION_PORTFOLIO,
                aggregate_id=organization_id,
                payload={
                    "template": "organization_verified",
                    "administrator_ref": payload["administrator_ref"],
                    "organization_id": organization_id,
                    "origin_caveat": (
                        "The declaration does not prove that a displayed call came from the "
                        "organisation."
                    ),
                },
                idempotency_key=f"organization-verified:{organization_id}",
            )

    def public_portfolio(self, organization_id: str) -> dict[str, Any] | None:
        self.expire_due()
        try:
            record = self._store.get(EntityKind.ORGANIZATION_PORTFOLIO, organization_id)
        except RecordNotFound:
            return None
        if record.payload.get("status") != "verified":
            return None
        return _public_projection(record.payload)

    def update_portfolio(
        self,
        *,
        organization_id: str,
        administrator_contact: str,
        declared_numbers: Sequence[str],
    ) -> dict[str, Any]:
        organization = self._controlled_organization(
            organization_id,
            administrator_contact,
        )
        numbers = sorted(set(declared_numbers))
        if not numbers or len(numbers) > self._policy.max_portfolio_size:
            raise ValueError("declared number portfolio is empty or exceeds its bound")
        if any(_E164.fullmatch(number) is None for number in numbers):
            raise ValueError("declared numbers must use E.164")
        proposed = [
            {
                "canonical_e164": number,
                "label": "Declared official contact",
                "status": "active",
                "declared_at": _timestamp(self._clock()),
            }
            for number in numbers
        ]
        if self._conflicting_organization(organization_id, proposed):
            self._mark_conflict(organization)
            raise OrganizationVerificationFailed()
        now = self._clock()
        payload = deepcopy(organization.payload)
        payload["numbers"] = proposed
        payload["correction"] = {
            "status": "corrected",
            "updated_at": _timestamp(now),
            "reason_codes": ["portfolio_updated"],
        }
        payload["updated_at"] = _timestamp(now)
        with self._store.transaction() as transaction:
            updated = transaction.correct(
                kind=EntityKind.ORGANIZATION_PORTFOLIO,
                record_id=organization_id,
                payload=payload,
                expected_version=organization.version,
                reason="portfolio_updated",
            )
        return _public_projection(updated.payload)

    def report_impersonation(
        self,
        *,
        organization_id: str,
        reason_code: str,
    ) -> None:
        if re.fullmatch(r"[a-z0-9]+(?:[_-][a-z0-9]+)*", reason_code) is None:
            raise ValueError("reason_code must be a machine-readable token")
        try:
            organization = self._store.get(
                EntityKind.ORGANIZATION_PORTFOLIO,
                organization_id,
            )
        except RecordNotFound as exc:
            raise OrganizationVerificationFailed() from exc
        now = self._clock()
        payload = deepcopy(organization.payload)
        payload["status"] = "suspended"
        payload["correction"] = {
            "status": "under_review",
            "updated_at": _timestamp(now),
            "reason_codes": [reason_code],
        }
        payload["updated_at"] = _timestamp(now)
        with self._store.transaction() as transaction:
            transaction.correct(
                kind=EntityKind.ORGANIZATION_PORTFOLIO,
                record_id=organization_id,
                payload=payload,
                expected_version=organization.version,
                reason=reason_code,
            )

    def resolve_appeal(
        self,
        *,
        organization_id: str,
        decision: str,
        reason_code: str,
    ) -> dict[str, Any]:
        if decision not in {"reinstate", "revoke"}:
            raise ValueError("appeal decision must be reinstate or revoke")
        if re.fullmatch(r"[a-z0-9]+(?:[_-][a-z0-9]+)*", reason_code) is None:
            raise ValueError("reason_code must be a machine-readable token")
        try:
            organization = self._store.get(
                EntityKind.ORGANIZATION_PORTFOLIO,
                organization_id,
            )
        except RecordNotFound as exc:
            raise OrganizationVerificationFailed() from exc
        if organization.payload.get("status") not in {"suspended", "conflict_review"}:
            raise OrganizationVerificationFailed()
        now = self._clock()
        payload = deepcopy(organization.payload)
        if decision == "revoke":
            payload["status"] = "revoked"
        else:
            valid_until = datetime.fromisoformat(
                str(payload["verification"]["valid_until"]).replace("Z", "+00:00")
            )
            payload["status"] = "verified" if valid_until >= now else "expired"
        payload["correction"] = {
            "status": "appeal_resolved",
            "updated_at": _timestamp(now),
            "reason_codes": [reason_code],
        }
        payload["updated_at"] = _timestamp(now)
        with self._store.transaction() as transaction:
            resolved = transaction.correct(
                kind=EntityKind.ORGANIZATION_PORTFOLIO,
                record_id=organization_id,
                payload=payload,
                expected_version=organization.version,
                reason=f"appeal_{decision}",
            )
        return _public_projection(resolved.payload)

    def delete_portfolio(
        self,
        *,
        organization_id: str,
        administrator_contact: str,
    ):
        self._organization_with_administrator(
            organization_id,
            administrator_contact,
            require_verified=False,
        )
        with self._store.transaction() as transaction:
            return transaction.delete(
                kind=EntityKind.ORGANIZATION_PORTFOLIO,
                record_id=organization_id,
                reason="organization_deletion",
            )

    def expire_due(self) -> int:
        now = self._clock()
        expired = 0
        for record in self._store.list_records(EntityKind.ORGANIZATION_PORTFOLIO):
            payload = deepcopy(record.payload)
            if payload.get("status") != "verified":
                continue
            valid_until = datetime.fromisoformat(
                str(payload["verification"]["valid_until"]).replace("Z", "+00:00")
            )
            if valid_until >= now:
                continue
            payload["status"] = "expired"
            payload["updated_at"] = _timestamp(now)
            with self._store.transaction() as transaction:
                transaction.correct(
                    kind=EntityKind.ORGANIZATION_PORTFOLIO,
                    record_id=record.record_id,
                    payload=payload,
                    expected_version=record.version,
                    reason="verification_expired",
                )
            expired += 1
        return expired

    def _conflicting_organization(
        self,
        organization_id: str,
        numbers: Sequence[dict[str, Any]],
    ) -> bool:
        requested = {str(item["canonical_e164"]) for item in numbers}
        return any(
            record.record_id != organization_id
            and record.payload.get("status") == "verified"
            and requested.intersection(
                str(item["canonical_e164"]) for item in record.payload.get("numbers", [])
            )
            for record in self._store.list_records(EntityKind.ORGANIZATION_PORTFOLIO)
        )

    def _mark_conflict(self, organization, *, challenge_id: str | None = None) -> None:
        now = self._clock()
        payload = deepcopy(organization.payload)
        payload["status"] = "conflict_review"
        if payload["verification"]["verified_at"] is None:
            payload["verification"]["verified_at"] = _timestamp(now)
            payload["verification"]["valid_until"] = _timestamp(
                now + self._policy.verification_ttl
            )
        payload["correction"] = {
            "status": "under_review",
            "updated_at": _timestamp(now),
            "reason_codes": ["number_declaration_conflict"],
        }
        payload["updated_at"] = _timestamp(now)
        with self._store.transaction() as transaction:
            transaction.correct(
                kind=EntityKind.ORGANIZATION_PORTFOLIO,
                record_id=organization.record_id,
                payload=payload,
                expected_version=organization.version,
                reason="number_declaration_conflict",
            )
            if challenge_id is not None:
                transaction.delete(
                    kind=EntityKind.VERIFICATION_CHALLENGE,
                    record_id=challenge_id,
                    reason="challenge_consumed_conflict_review",
                )

    def _record_failed_attempt(self, challenge, payload: dict[str, Any]) -> None:
        payload["attempts"] = int(payload["attempts"]) + 1
        if payload["attempts"] >= int(payload["max_attempts"]):
            payload["status"] = "locked"
        with self._store.transaction() as transaction:
            transaction.correct(
                kind=EntityKind.VERIFICATION_CHALLENGE,
                record_id=challenge.record_id,
                payload=payload,
                expected_version=challenge.version,
                reason="organization_challenge_failed",
            )

    def _controlled_organization(
        self,
        organization_id: str,
        administrator_contact: str,
    ):
        return self._organization_with_administrator(
            organization_id,
            administrator_contact,
            require_verified=True,
        )

    def _organization_with_administrator(
        self,
        organization_id: str,
        administrator_contact: str,
        *,
        require_verified: bool,
    ):
        try:
            organization = self._store.get(
                EntityKind.ORGANIZATION_PORTFOLIO,
                organization_id,
            )
        except RecordNotFound as exc:
            raise OrganizationVerificationFailed() from exc
        administrator_ref = (
            "admin_"
            + self._digest(
                f"administrator:{administrator_contact.strip().lower()}"
            )[:32]
        )
        if (
            (require_verified and organization.payload.get("status") != "verified")
            or organization.payload.get("verification", {}).get("verified_at") is None
            or not hmac.compare_digest(
                str(organization.payload.get("administrator_ref", "")),
                administrator_ref,
            )
        ):
            raise OrganizationVerificationFailed()
        return organization

    def _digest(self, value: str) -> str:
        return hmac.new(self._secret, value.encode(), hashlib.sha256).hexdigest()


def _validate_declaration(
    *,
    display_name: str,
    domain: str,
    contact: str,
    jurisdiction: str,
    numbers: Sequence[str],
    max_portfolio_size: int,
) -> None:
    if not 3 <= len(display_name.strip()) <= 120:
        raise ValueError("display_name must contain 3 to 120 characters")
    if _DOMAIN.fullmatch(domain) is None:
        raise ValueError("valid organization domain required")
    if "@" not in contact or contact.rsplit("@", 1)[1] != domain:
        raise ValueError("administrator contact must use the organization domain")
    if re.fullmatch(r"[A-Z]{2}", jurisdiction) is None:
        raise ValueError("jurisdiction must be an ISO alpha-2 code")
    if not numbers or len(numbers) > max_portfolio_size:
        raise ValueError("declared number portfolio is empty or exceeds its bound")
    if any(_E164.fullmatch(number) is None for number in numbers):
        raise ValueError("declared numbers must use E.164")


def _public_projection(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "kind": "organization_portfolio",
        "organization_id": payload["organization_id"],
        "display_name": payload["display_name"],
        "domain": payload["domain"],
        "jurisdiction": payload["jurisdiction"],
        "status": payload["status"],
        "verification": deepcopy(payload["verification"]),
        "numbers": deepcopy(payload["numbers"]),
        "correction": deepcopy(payload["correction"]),
        "updated_at": payload["updated_at"],
        "limitations": [
            "This portfolio is an organisation declaration, not proof that a call originated "
            "from the organisation.",
            "Caller ID can be spoofed; independently use a trusted contact route.",
        ],
    }


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
