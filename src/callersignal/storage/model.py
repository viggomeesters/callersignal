"""Storage records shared by every CallerSignal persistence adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class EntityKind(StrEnum):
    REPORT = "report"
    CAMPAIGN = "campaign"
    WATCH = "watch"
    VERIFICATION_CHALLENGE = "verification_challenge"


class PrivacyBoundaryError(ValueError):
    """A payload attempted to cross a forbidden persistence boundary."""


class RecordNotFound(LookupError):
    """A record is absent, deleted, or expired."""


class VersionConflict(RuntimeError):
    """A correction targeted a stale aggregate version."""


@dataclass(frozen=True)
class StoredRecord:
    kind: EntityKind
    record_id: str
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    dedupe_key: str | None
    version: int


@dataclass(frozen=True)
class OutboxMessage:
    message_id: str
    event_type: str
    aggregate_kind: EntityKind
    aggregate_id: str
    payload: dict[str, Any]
    idempotency_key: str
    created_at: datetime
    delivered_at: datetime | None
    attempts: int


@dataclass(frozen=True)
class AuditReceipt:
    receipt_id: str
    action: str
    kind: EntityKind
    record_id: str
    occurred_at: datetime
    reason: str
    version: int
