"""Consent, verification, and material-change workflow for private watches."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from callersignal.storage import DataStore, EntityKind, RecordNotFound

_GENERIC_MESSAGE = "If the request is eligible, verification instructions will be sent."
_E164 = re.compile(r"^\+[1-9][0-9]{1,14}$")


class WatchVerificationFailed(ValueError):
    """A challenge failed without revealing which watch or contact exists."""

    def __init__(self) -> None:
        super().__init__("verification_failed")


@dataclass(frozen=True)
class WatchPolicy:
    challenge_ttl: timedelta
    watch_ttl: timedelta
    request_window: timedelta
    max_requests: int
    max_attempts: int


@dataclass(frozen=True)
class WatchRequestResult:
    message: str = _GENERIC_MESSAGE


@dataclass(frozen=True)
class NotificationDecision:
    enqueued: bool
    reason: str


class WatchService:
    def __init__(
        self,
        *,
        store: DataStore,
        clock: Callable[[], datetime],
        secret: bytes,
        code_factory: Callable[[], str],
        policy: WatchPolicy,
    ) -> None:
        if len(secret) < 16:
            raise ValueError("watch secret must contain at least 16 bytes")
        self._store = store
        self._clock = clock
        self._secret = secret
        self._code_factory = code_factory
        self._policy = policy

    def request_watch(
        self,
        *,
        displayed_e164: str,
        contact: str,
        consent_policy_version: str,
    ) -> WatchRequestResult:
        now = self._clock()
        normalized_contact = _normalize_contact(contact)
        if _E164.fullmatch(displayed_e164) is None:
            return WatchRequestResult()
        contact_ref = f"contact_{self._digest(f'contact:{normalized_contact}')[:32]}"
        number_ref = f"num_{self._digest(f'number:{displayed_e164}')[:32]}"
        if any(
            record.payload.get("contact", {}).get("contact_ref") == contact_ref
            and record.payload.get("subject", {}).get("number_ref") == number_ref
            for record in self._store.list_records(EntityKind.WATCH)
        ):
            return WatchRequestResult()
        watch_id = f"watch_{self._digest(f'watch:{contact_ref}:{number_ref}')[:24]}"
        try:
            self._store.get(EntityKind.WATCH, watch_id)
        except RecordNotFound:
            pass
        else:
            return WatchRequestResult()
        recent_requests = [
            record
            for record in self._store.list_records(EntityKind.VERIFICATION_CHALLENGE)
            if record.payload.get("contact_ref") == contact_ref
            and record.created_at > now - self._policy.request_window
        ]
        if len(recent_requests) >= self._policy.max_requests:
            return WatchRequestResult()
        code = self._code_factory()
        if re.fullmatch(r"[0-9]{6}", code) is None:
            raise ValueError("verification code factory must return six digits")
        challenge_id = (
            "challenge_"
            + self._digest(f"challenge:{watch_id}:{_timestamp(now)}")[:24]
        )
        challenge_expires_at = now + self._policy.challenge_ttl
        watch_expires_at = now + self._policy.watch_ttl
        watch_payload = {
            "schema_version": "1.0.0",
            "kind": "watch_subscription",
            "watch_id": watch_id,
            "status": "pending_verification",
            "subject": {
                "number_ref": number_ref,
                "semantics": "displayed_number_digest",
            },
            "contact": {"contact_ref": contact_ref, "visibility": "private"},
            "consent": {
                "policy_version": consent_policy_version,
                "receipt_id": f"consent_{self._digest(f'consent:{watch_id}:{now}')[:24]}",
                "purpose": "material_risk_change_notifications",
                "granted_at": _timestamp(now),
            },
            "verification": {
                "status": "pending",
                "verified_at": None,
            },
            "notification": {
                "last_material_fingerprint": None,
                "last_notified_at": None,
            },
            "correction": {
                "status": "none",
                "updated_at": None,
                "reason_codes": [],
            },
            "created_at": _timestamp(now),
            "updated_at": _timestamp(now),
            "expires_at": _timestamp(watch_expires_at),
        }
        challenge_payload = {
            "watch_id": watch_id,
            "contact_ref": contact_ref,
            "challenge_digest": self._digest(f"code:{challenge_id}:{code}"),
            "status": "pending",
            "attempts": 0,
            "max_attempts": self._policy.max_attempts,
            "expires_at": _timestamp(challenge_expires_at),
        }
        with self._store.transaction() as transaction:
            transaction.put(
                kind=EntityKind.WATCH,
                record_id=watch_id,
                payload=watch_payload,
                dedupe_key=f"{contact_ref}:{number_ref}",
            )
            transaction.put(
                kind=EntityKind.VERIFICATION_CHALLENGE,
                record_id=challenge_id,
                payload=challenge_payload,
                expires_at=challenge_expires_at,
                dedupe_key=f"watch-verification:{watch_id}",
            )
            transaction.enqueue(
                message_id=f"msg_{self._digest(f'verify:{challenge_id}')[:24]}",
                event_type="watch.verify",
                aggregate_kind=EntityKind.VERIFICATION_CHALLENGE,
                aggregate_id=challenge_id,
                payload={
                    "template": "watch_verification",
                    "contact_ref": contact_ref,
                    "watch_id": watch_id,
                    "challenge_id": challenge_id,
                    "verification_code": code,
                    "expires_at": _timestamp(challenge_expires_at),
                },
                idempotency_key=f"watch-verify:{challenge_id}",
            )
        return WatchRequestResult()

    def confirm_watch(self, *, challenge_id: str, code: str) -> None:
        try:
            challenge = self._store.get(
                EntityKind.VERIFICATION_CHALLENGE,
                challenge_id,
            )
        except RecordNotFound as exc:
            raise WatchVerificationFailed() from exc
        payload = deepcopy(challenge.payload)
        expected = str(payload["challenge_digest"])
        supplied = self._digest(f"code:{challenge_id}:{code}")
        if payload["status"] != "pending" or not hmac.compare_digest(expected, supplied):
            self._record_failed_attempt(challenge_id, challenge.version, payload)
            raise WatchVerificationFailed()
        try:
            watch = self._store.get(EntityKind.WATCH, str(payload["watch_id"]))
        except RecordNotFound as exc:
            raise WatchVerificationFailed() from exc
        now = self._clock()
        watch_payload = deepcopy(watch.payload)
        watch_payload["status"] = "active"
        watch_payload["verification"] = {
            "status": "verified",
            "verified_at": _timestamp(now),
        }
        watch_payload["updated_at"] = _timestamp(now)
        with self._store.transaction() as transaction:
            transaction.correct(
                kind=EntityKind.WATCH,
                record_id=watch.record_id,
                payload=watch_payload,
                expected_version=watch.version,
                reason="contact_verified",
            )
            transaction.delete(
                kind=EntityKind.VERIFICATION_CHALLENGE,
                record_id=challenge_id,
                reason="challenge_consumed",
            )
            transaction.enqueue(
                message_id=f"msg_{self._digest(f'verified:{watch.record_id}')[:24]}",
                event_type="watch.verified",
                aggregate_kind=EntityKind.WATCH,
                aggregate_id=watch.record_id,
                payload={
                    "template": "watch_verified",
                    "contact_ref": watch_payload["contact"]["contact_ref"],
                    "no_safety_caveat": (
                        "A watch reports evidence changes; it never means a number is safe."
                    ),
                },
                idempotency_key=f"watch-verified:{watch.record_id}",
            )

    def list_for_contact(self, contact: str) -> list[dict[str, Any]]:
        contact_ref = f"contact_{self._digest(f'contact:{_normalize_contact(contact)}')[:32]}"
        self.expire_due()
        return [
            deepcopy(record.payload)
            for record in self._store.list_records(EntityKind.WATCH)
            if record.payload.get("contact", {}).get("contact_ref") == contact_ref
            and record.payload.get("status") == "active"
        ]

    def notify_if_material(
        self,
        *,
        watch_id: str,
        campaign_id: str,
        risk_state: str,
        campaign_status: str,
        correction_status: str,
        recommended_action: str,
    ) -> NotificationDecision:
        if risk_state not in {
            "official_warning",
            "elevated_signals",
            "no_risk_evidence",
            "insufficient_evidence",
        }:
            raise ValueError("invalid risk_state")
        material = {
            "campaign_id": campaign_id,
            "risk_state": risk_state,
            "campaign_status": campaign_status,
            "correction_status": correction_status,
            "recommended_action": recommended_action,
        }
        fingerprint = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        try:
            watch = self._store.get(EntityKind.WATCH, watch_id)
        except RecordNotFound:
            return NotificationDecision(enqueued=False, reason="inactive")
        payload = deepcopy(watch.payload)
        if payload.get("status") != "active" or payload.get("verification", {}).get(
            "status"
        ) != "verified":
            return NotificationDecision(enqueued=False, reason="inactive")
        if payload["notification"]["last_material_fingerprint"] == fingerprint:
            return NotificationDecision(enqueued=False, reason="unchanged")
        now = self._clock()
        payload["notification"] = {
            "last_material_fingerprint": fingerprint,
            "last_notified_at": _timestamp(now),
        }
        payload["updated_at"] = _timestamp(now)
        with self._store.transaction() as transaction:
            transaction.correct(
                kind=EntityKind.WATCH,
                record_id=watch_id,
                payload=payload,
                expected_version=watch.version,
                reason="material_campaign_change",
            )
            transaction.enqueue(
                message_id=f"msg_{self._digest(f'change:{watch_id}:{fingerprint}')[:24]}",
                event_type="watch.material_change",
                aggregate_kind=EntityKind.WATCH,
                aggregate_id=watch_id,
                payload={
                    "template": "watch_material_change",
                    "contact_ref": payload["contact"]["contact_ref"],
                    **material,
                    "no_safety_caveat": (
                        "Caller ID can be spoofed; no CallerSignal state means a number is safe."
                    ),
                },
                idempotency_key=f"watch-change:{watch_id}:{fingerprint}",
            )
        return NotificationDecision(enqueued=True, reason="material_change")

    def correct_watch(
        self,
        *,
        watch_id: str,
        contact: str,
        displayed_e164: str,
    ) -> dict[str, Any]:
        if _E164.fullmatch(displayed_e164) is None:
            raise WatchVerificationFailed()
        watch = self._owned_watch(watch_id, contact)
        now = self._clock()
        payload = deepcopy(watch.payload)
        payload["subject"]["number_ref"] = (
            f"num_{self._digest(f'number:{displayed_e164}')[:32]}"
        )
        payload["notification"] = {
            "last_material_fingerprint": None,
            "last_notified_at": None,
        }
        payload["correction"] = {
            "status": "corrected",
            "updated_at": _timestamp(now),
            "reason_codes": ["subscriber_scope_correction"],
        }
        payload["updated_at"] = _timestamp(now)
        with self._store.transaction() as transaction:
            corrected = transaction.correct(
                kind=EntityKind.WATCH,
                record_id=watch_id,
                payload=payload,
                expected_version=watch.version,
                reason="subscriber_scope_correction",
            )
        return deepcopy(corrected.payload)

    def revoke_watch(self, *, watch_id: str, contact: str) -> dict[str, Any]:
        watch = self._owned_watch(watch_id, contact)
        payload = deepcopy(watch.payload)
        if payload.get("status") == "revoked":
            return payload
        now = self._clock()
        payload["status"] = "revoked"
        payload["updated_at"] = _timestamp(now)
        with self._store.transaction() as transaction:
            revoked = transaction.correct(
                kind=EntityKind.WATCH,
                record_id=watch_id,
                payload=payload,
                expected_version=watch.version,
                reason="subscriber_unsubscribe",
            )
            transaction.enqueue(
                message_id=f"msg_{self._digest(f'revoked:{watch_id}')[:24]}",
                event_type="watch.revoked",
                aggregate_kind=EntityKind.WATCH,
                aggregate_id=watch_id,
                payload={
                    "template": "watch_revoked",
                    "contact_ref": payload["contact"]["contact_ref"],
                },
                idempotency_key=f"watch-revoked:{watch_id}",
            )
        return deepcopy(revoked.payload)

    def delete_watch(self, *, watch_id: str, contact: str):
        self._owned_watch(watch_id, contact)
        with self._store.transaction() as transaction:
            return transaction.delete(
                kind=EntityKind.WATCH,
                record_id=watch_id,
                reason="subscriber_deletion",
            )

    def expire_due(self) -> int:
        now = self._clock()
        expired = 0
        for record in self._store.list_records(EntityKind.WATCH):
            payload = deepcopy(record.payload)
            if payload.get("status") not in {"active", "pending_verification"}:
                continue
            expires_at = datetime.fromisoformat(str(payload["expires_at"]).replace("Z", "+00:00"))
            if expires_at >= now:
                continue
            payload["status"] = "expired"
            payload["updated_at"] = _timestamp(now)
            with self._store.transaction() as transaction:
                transaction.correct(
                    kind=EntityKind.WATCH,
                    record_id=record.record_id,
                    payload=payload,
                    expected_version=record.version,
                    reason="consent_expired",
                )
            expired += 1
        return expired

    def _record_failed_attempt(
        self,
        challenge_id: str,
        version: int,
        payload: dict[str, Any],
    ) -> None:
        payload["attempts"] = int(payload["attempts"]) + 1
        if payload["attempts"] >= int(payload["max_attempts"]):
            payload["status"] = "locked"
        with self._store.transaction() as transaction:
            transaction.correct(
                kind=EntityKind.VERIFICATION_CHALLENGE,
                record_id=challenge_id,
                payload=payload,
                expected_version=version,
                reason="challenge_failed",
            )

    def _owned_watch(self, watch_id: str, contact: str):
        try:
            watch = self._store.get(EntityKind.WATCH, watch_id)
        except RecordNotFound as exc:
            raise WatchVerificationFailed() from exc
        contact_ref = f"contact_{self._digest(f'contact:{_normalize_contact(contact)}')[:32]}"
        stored_ref = str(watch.payload.get("contact", {}).get("contact_ref", ""))
        if (
            not hmac.compare_digest(stored_ref, contact_ref)
            or watch.payload.get("verification", {}).get("status") != "verified"
        ):
            raise WatchVerificationFailed()
        return watch

    def _digest(self, value: str) -> str:
        return hmac.new(self._secret, value.encode(), hashlib.sha256).hexdigest()


def _normalize_contact(contact: str) -> str:
    normalized = contact.strip().lower()
    if len(normalized) > 254 or re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized) is None:
        raise ValueError("a valid email contact is required")
    return normalized


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
