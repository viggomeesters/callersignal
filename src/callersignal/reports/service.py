"""Deterministic report controls without public transport or durable storage."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

_REPORT_CATEGORIES = {
    "unwanted",
    "silent_call",
    "robocall",
    "impersonation_attempt",
    "payment_request",
    "credential_request",
    "harassment",
    "legitimate",
    "other",
}
_TOKEN = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")
_E164 = re.compile(r"^\+[1-9][0-9]{1,14}$")


class ReportRejected(ValueError):
    """The submission failed a privacy, rate, or abuse control."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ReportNotFound(LookupError):
    """The report is absent, deleted, or expired."""


class ReportAuthorizationError(PermissionError):
    """The supplied receipt proof does not authorize the operation."""


@dataclass(frozen=True)
class ReportPolicy:
    retention: timedelta
    rate_window: timedelta
    actor_limit: int
    distinct_actor_limit: int


@dataclass(frozen=True)
class SubmissionReceipt:
    report_id: str
    receipt_id: str
    created: bool


@dataclass(frozen=True)
class DeletionReceipt:
    deletion_id: str
    report_id: str
    deleted_at: datetime
    reason: str


@dataclass
class _StoredReport:
    report: dict[str, Any]
    actor_digest: str
    number_digest: str
    fingerprint: str
    submitted_at: datetime


class ReportService:
    """Apply report safety controls behind a transport-independent interface."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        secret: bytes,
        policy: ReportPolicy,
    ) -> None:
        if len(secret) < 16:
            raise ValueError("report secret must contain at least 16 bytes")
        self._clock = clock
        self._secret = secret
        self._policy = policy
        self._reports: dict[str, _StoredReport] = {}
        self._report_by_fingerprint: dict[str, str] = {}
        self._deletions: dict[str, DeletionReceipt] = {}

    def submit(
        self,
        *,
        displayed_number: Mapping[str, Any],
        actor_token: str,
        categories: Sequence[str],
        channel: str,
        contact_outcome: str,
        occurred_at: datetime | None,
        submission_channel: str,
        reporter_region: str | None = None,
    ) -> SubmissionReceipt:
        now = self._clock()
        e164 = str(displayed_number.get("canonical", {}).get("e164", ""))
        categories = tuple(sorted(set(categories)))
        self._validate_submission(
            actor_token=actor_token,
            e164=e164,
            categories=categories,
            channel=channel,
            contact_outcome=contact_outcome,
            occurred_at=occurred_at,
            submission_channel=submission_channel,
            reporter_region=reporter_region,
            now=now,
        )
        actor_digest = self._digest(f"actor:{actor_token}")
        number_digest = self._digest(f"number:{e164}")
        fingerprint = self._digest(
            json.dumps(
                {
                    "actor": actor_digest,
                    "number": number_digest,
                    "categories": categories,
                    "channel": channel,
                    "outcome": contact_outcome,
                    "occurred_at": _timestamp(occurred_at) if occurred_at else None,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        existing_id = self._report_by_fingerprint.get(fingerprint)
        if existing_id in self._reports:
            report = self._reports[existing_id].report
            return SubmissionReceipt(
                report_id=existing_id,
                receipt_id=str(report["submission"]["receipt_id"]),
                created=False,
            )
        self._enforce_actor_rate(actor_digest, now)
        self._enforce_brigading(number_digest, actor_digest, now)
        report_id = f"rpt_{fingerprint[:24]}"
        receipt_id = f"rcpt_{self._digest(f'receipt:{report_id}')[:24]}"
        report: dict[str, Any] = {
            "schema_version": "1.0.0",
            "kind": "call_report",
            "report_id": report_id,
            "reported_at": _timestamp(now),
            "subject_semantics": "call_displayed_number",
            "displayed_number": deepcopy(dict(displayed_number)),
            "observation": {
                "direction": "inbound",
                "occurred_at": _timestamp(occurred_at) if occurred_at else None,
                "channel": channel,
                "contact_outcome": contact_outcome,
                "categories": list(categories),
            },
            "attestations": {
                "direct_observation": True,
                "understands_displayed_number_not_identity": True,
                "contains_no_sensitive_narrative": True,
            },
            "moderation": {
                "workflow_status": "pending",
                "verification_status": "unverified_observation",
                "reason_codes": [],
            },
            "privacy": {
                "policy_version": "1.0.0",
                "retention_policy_id": "first_party_report_default",
                "retention_until": _timestamp(now + self._policy.retention),
                "contains_free_text": False,
            },
            "submission": {
                "channel": submission_channel,
                "receipt_id": receipt_id,
            },
        }
        if reporter_region is not None:
            report["reporter_context"] = {"region": reporter_region}
        self._reports[report_id] = _StoredReport(
            report=report,
            actor_digest=actor_digest,
            number_digest=number_digest,
            fingerprint=fingerprint,
            submitted_at=now,
        )
        self._report_by_fingerprint[fingerprint] = report_id
        return SubmissionReceipt(report_id=report_id, receipt_id=receipt_id, created=True)

    def get_for_moderation(self, report_id: str) -> dict[str, Any]:
        return deepcopy(self._active_report(report_id).report)

    def correct(
        self,
        *,
        report_id: str,
        receipt_id: str,
        actor_token: str,
        categories: Sequence[str],
    ) -> dict[str, Any]:
        stored = self._authorized_report(report_id, receipt_id, actor_token)
        normalized_categories = tuple(sorted(set(categories)))
        if (
            not normalized_categories
            or not set(normalized_categories) <= _REPORT_CATEGORIES
        ):
            raise ReportRejected("invalid_categories")
        self._report_by_fingerprint.pop(stored.fingerprint, None)
        stored.report["observation"]["categories"] = list(normalized_categories)
        stored.report["moderation"] = {
            "workflow_status": "pending",
            "verification_status": "unverified_observation",
            "reason_codes": ["reporter_correction"],
        }
        stored.fingerprint = self._digest(
            json.dumps(
                {
                    "actor": stored.actor_digest,
                    "number": stored.number_digest,
                    "categories": normalized_categories,
                    "channel": stored.report["observation"]["channel"],
                    "outcome": stored.report["observation"]["contact_outcome"],
                    "occurred_at": stored.report["observation"]["occurred_at"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        self._report_by_fingerprint[stored.fingerprint] = report_id
        return deepcopy(stored.report)

    def delete(
        self,
        *,
        report_id: str,
        receipt_id: str,
        actor_token: str,
    ) -> DeletionReceipt:
        stored = self._authorized_report(report_id, receipt_id, actor_token)
        return self._delete_report(report_id, stored, reason="reporter_request")

    def moderate(
        self,
        *,
        report_id: str,
        decision: str,
        reason_codes: Sequence[str],
    ) -> dict[str, Any]:
        workflow_by_decision = {
            "accept_observation": "accepted_observation",
            "reject": "rejected",
        }
        normalized_reasons = sorted(set(reason_codes))
        if decision not in workflow_by_decision:
            raise ReportRejected("invalid_moderation_decision")
        if not normalized_reasons or any(
            _TOKEN.fullmatch(reason) is None for reason in normalized_reasons
        ):
            raise ReportRejected("invalid_moderation_reasons")
        stored = self._active_report(report_id)
        stored.report["moderation"] = {
            "workflow_status": workflow_by_decision[decision],
            "verification_status": "unverified_observation",
            "reason_codes": normalized_reasons,
        }
        return deepcopy(stored.report)

    def purge_expired(self) -> list[DeletionReceipt]:
        now = self._clock()
        expired_ids = sorted(
            report_id
            for report_id, stored in self._reports.items()
            if stored.submitted_at + self._policy.retention < now
        )
        return [
            self._delete_report(
                report_id,
                self._reports[report_id],
                reason="retention_expired",
            )
            for report_id in expired_ids
        ]

    def privacy_snapshot(self) -> dict[str, int]:
        return {
            "active_reports": len(self._reports),
            "raw_actor_tokens": 0,
            "raw_requester_ips": 0,
            "raw_lookup_histories": 0,
        }

    def _enforce_actor_rate(self, actor_digest: str, now: datetime) -> None:
        window_start = now - self._policy.rate_window
        recent_count = sum(
            1
            for item in self._reports.values()
            if item.actor_digest == actor_digest and item.submitted_at > window_start
        )
        if recent_count >= self._policy.actor_limit:
            raise ReportRejected("actor_rate_limit")

    def _validate_submission(
        self,
        *,
        actor_token: str,
        e164: str,
        categories: Sequence[str],
        channel: str,
        contact_outcome: str,
        occurred_at: datetime | None,
        submission_channel: str,
        reporter_region: str | None,
        now: datetime,
    ) -> None:
        if not actor_token.strip():
            raise ReportRejected("missing_actor_proof")
        if _E164.fullmatch(e164) is None:
            raise ReportRejected("invalid_displayed_number")
        if not categories or not set(categories) <= _REPORT_CATEGORIES:
            raise ReportRejected("invalid_categories")
        if channel not in {"voice", "voicemail", "sms", "other"}:
            raise ReportRejected("invalid_channel")
        if contact_outcome not in {
            "unanswered",
            "answered",
            "voicemail",
            "message_received",
            "other",
        }:
            raise ReportRejected("invalid_contact_outcome")
        if submission_channel not in {"web", "http_api", "mcp", "moderator_import"}:
            raise ReportRejected("invalid_submission_channel")
        if occurred_at is not None and (occurred_at.tzinfo is None or occurred_at > now):
            raise ReportRejected("invalid_occurrence_time")
        if reporter_region is not None and re.fullmatch(r"[A-Z]{2}", reporter_region) is None:
            raise ReportRejected("invalid_reporter_region")

    def _authorized_report(
        self,
        report_id: str,
        receipt_id: str,
        actor_token: str,
    ) -> _StoredReport:
        stored = self._active_report(report_id)
        actor_digest = self._digest(f"actor:{actor_token}")
        expected_receipt = stored.report["submission"]["receipt_id"]
        if not hmac.compare_digest(stored.actor_digest, actor_digest) or not hmac.compare_digest(
            str(expected_receipt), receipt_id
        ):
            raise ReportAuthorizationError(report_id)
        return stored

    def _active_report(self, report_id: str) -> _StoredReport:
        try:
            stored = self._reports[report_id]
        except KeyError as exc:
            raise ReportNotFound(report_id) from exc
        if stored.submitted_at + self._policy.retention < self._clock():
            self._delete_report(report_id, stored, reason="retention_expired")
            raise ReportNotFound(report_id)
        return stored

    def _delete_report(
        self,
        report_id: str,
        stored: _StoredReport,
        *,
        reason: str,
    ) -> DeletionReceipt:
        deleted_at = self._clock()
        deletion = DeletionReceipt(
            deletion_id=f"del_{self._digest(f'{report_id}:{_timestamp(deleted_at)}')[:24]}",
            report_id=report_id,
            deleted_at=deleted_at,
            reason=reason,
        )
        self._report_by_fingerprint.pop(stored.fingerprint, None)
        self._reports.pop(report_id, None)
        self._deletions[deletion.deletion_id] = deletion
        return deletion

    def _enforce_brigading(
        self,
        number_digest: str,
        actor_digest: str,
        now: datetime,
    ) -> None:
        window_start = now - self._policy.rate_window
        recent_actors = {
            item.actor_digest
            for item in self._reports.values()
            if item.number_digest == number_digest and item.submitted_at > window_start
        }
        if (
            actor_digest not in recent_actors
            and len(recent_actors) >= self._policy.distinct_actor_limit
        ):
            raise ReportRejected("brigading_threshold")

    def _digest(self, value: str) -> str:
        return hmac.new(self._secret, value.encode(), hashlib.sha256).hexdigest()


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
