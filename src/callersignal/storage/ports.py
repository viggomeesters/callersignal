"""Structural persistence interfaces consumed by product services."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from callersignal.storage.model import (
    AuditReceipt,
    EntityKind,
    OutboxMessage,
    StoredRecord,
)


class StorageTransaction(Protocol):
    def put(
        self,
        *,
        kind: EntityKind,
        record_id: str,
        payload: Mapping[str, Any],
        expires_at: datetime | None = None,
        dedupe_key: str | None = None,
    ) -> StoredRecord: ...

    def correct(
        self,
        *,
        kind: EntityKind,
        record_id: str,
        payload: Mapping[str, Any],
        expected_version: int,
        reason: str,
    ) -> StoredRecord: ...

    def delete(
        self,
        *,
        kind: EntityKind,
        record_id: str,
        reason: str,
    ) -> AuditReceipt: ...

    def enqueue(
        self,
        *,
        message_id: str,
        event_type: str,
        aggregate_kind: EntityKind,
        aggregate_id: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> OutboxMessage: ...


@runtime_checkable
class DataStore(Protocol):
    def transaction(self) -> AbstractContextManager[StorageTransaction]: ...

    def get(self, kind: EntityKind, record_id: str) -> StoredRecord: ...

    def list_records(self, kind: EntityKind) -> Sequence[StoredRecord]: ...

    def pending_outbox(self) -> Sequence[OutboxMessage]: ...

    def record_outbox_attempt(
        self,
        message_id: str,
        *,
        delivered: bool,
    ) -> OutboxMessage: ...

    def purge_expired(self) -> Sequence[AuditReceipt]: ...

    def audit_receipts(self) -> Sequence[AuditReceipt]: ...
