"""Deterministic in-memory adapter with transactional outbox semantics."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from threading import RLock
from typing import Any

from callersignal.storage.model import (
    AuditReceipt,
    EntityKind,
    OutboxMessage,
    PrivacyBoundaryError,
    RecordNotFound,
    StoredRecord,
    VersionConflict,
)

_FORBIDDEN_KEYS = {
    "ip",
    "ip_address",
    "lookup_history",
    "raw_actor_token",
    "raw_lookup_history",
    "requester_ip",
    "requester_identity",
}


class LocalStore:
    """Local proof adapter; state is process-local and never production data."""

    def __init__(self, *, clock: Callable[[], datetime]) -> None:
        self._clock = clock
        self._lock = RLock()
        self._records: dict[tuple[EntityKind, str], StoredRecord] = {}
        self._dedupe: dict[tuple[EntityKind, str], str] = {}
        self._outbox: dict[str, OutboxMessage] = {}
        self._outbox_dedupe: dict[str, str] = {}
        self._audit: list[AuditReceipt] = []

    @contextmanager
    def transaction(self) -> Iterator[LocalTransaction]:
        with self._lock:
            transaction = LocalTransaction(
                clock=self._clock,
                records=deepcopy(self._records),
                dedupe=deepcopy(self._dedupe),
                outbox=deepcopy(self._outbox),
                outbox_dedupe=deepcopy(self._outbox_dedupe),
                audit=deepcopy(self._audit),
            )
            yield transaction
            self._records = transaction.records
            self._dedupe = transaction.dedupe
            self._outbox = transaction.outbox
            self._outbox_dedupe = transaction.outbox_dedupe
            self._audit = transaction.audit

    def get(self, kind: EntityKind, record_id: str) -> StoredRecord:
        with self._lock:
            try:
                record = self._records[(kind, record_id)]
            except KeyError as exc:
                raise RecordNotFound(record_id) from exc
            if record.expires_at is not None and record.expires_at < self._clock():
                with self.transaction() as transaction:
                    transaction.delete(
                        kind=kind,
                        record_id=record_id,
                        reason="retention_expired",
                    )
                raise RecordNotFound(record_id)
            return deepcopy(record)

    def pending_outbox(self) -> list[OutboxMessage]:
        with self._lock:
            return sorted(
                (deepcopy(item) for item in self._outbox.values() if item.delivered_at is None),
                key=lambda item: (item.created_at, item.message_id),
            )

    def list_records(self, kind: EntityKind) -> list[StoredRecord]:
        self.purge_expired()
        with self._lock:
            return sorted(
                (
                    deepcopy(record)
                    for (record_kind, _), record in self._records.items()
                    if record_kind == kind
                ),
                key=lambda record: record.record_id,
            )

    def audit_receipts(self) -> list[AuditReceipt]:
        with self._lock:
            return deepcopy(self._audit)

    def record_outbox_attempt(
        self,
        message_id: str,
        *,
        delivered: bool,
    ) -> OutboxMessage:
        with self._lock:
            try:
                current = self._outbox[message_id]
            except KeyError as exc:
                raise RecordNotFound(message_id) from exc
            if current.delivered_at is not None:
                return deepcopy(current)
            updated = replace(
                current,
                attempts=current.attempts + 1,
                delivered_at=self._clock() if delivered else None,
            )
            self._outbox[message_id] = updated
            return deepcopy(updated)

    def purge_expired(self) -> list[AuditReceipt]:
        now = self._clock()
        receipts: list[AuditReceipt] = []
        with self.transaction() as transaction:
            expired = sorted(
                (
                    (kind, record_id)
                    for (kind, record_id), record in transaction.records.items()
                    if record.expires_at is not None and record.expires_at < now
                ),
                key=lambda item: (item[0].value, item[1]),
            )
            for kind, record_id in expired:
                receipts.append(
                    transaction.delete(
                        kind=kind,
                        record_id=record_id,
                        reason="retention_expired",
                    )
                )
        return receipts


class LocalTransaction:
    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        records: dict[tuple[EntityKind, str], StoredRecord],
        dedupe: dict[tuple[EntityKind, str], str],
        outbox: dict[str, OutboxMessage],
        outbox_dedupe: dict[str, str],
        audit: list[AuditReceipt],
    ) -> None:
        self._clock = clock
        self.records = records
        self.dedupe = dedupe
        self.outbox = outbox
        self.outbox_dedupe = outbox_dedupe
        self.audit = audit

    def put(
        self,
        *,
        kind: EntityKind,
        record_id: str,
        payload: Mapping[str, Any],
        expires_at: datetime | None = None,
        dedupe_key: str | None = None,
    ) -> StoredRecord:
        _validate_payload(payload)
        if dedupe_key is not None:
            existing_id = self.dedupe.get((kind, dedupe_key))
            if existing_id is not None:
                return deepcopy(self.records[(kind, existing_id)])
        if (kind, record_id) in self.records:
            raise VersionConflict(f"{kind}:{record_id} already exists; use correct")
        now = self._clock()
        if expires_at is not None and expires_at <= now:
            raise ValueError("expires_at must be later than creation time")
        record = StoredRecord(
            kind=kind,
            record_id=record_id,
            payload=deepcopy(dict(payload)),
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
            dedupe_key=dedupe_key,
            version=1,
        )
        self.records[(kind, record_id)] = record
        if dedupe_key is not None:
            self.dedupe[(kind, dedupe_key)] = record_id
        self.audit.append(_receipt("created", record, "record_created", now))
        return deepcopy(record)

    def enqueue(
        self,
        *,
        message_id: str,
        event_type: str,
        aggregate_kind: EntityKind,
        aggregate_id: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> OutboxMessage:
        _validate_payload(payload)
        existing_id = self.outbox_dedupe.get(idempotency_key)
        if existing_id is not None:
            return deepcopy(self.outbox[existing_id])
        if message_id in self.outbox:
            raise VersionConflict(f"outbox message {message_id} already exists")
        if (aggregate_kind, aggregate_id) not in self.records:
            raise RecordNotFound(f"{aggregate_kind}:{aggregate_id}")
        message = OutboxMessage(
            message_id=message_id,
            event_type=event_type,
            aggregate_kind=aggregate_kind,
            aggregate_id=aggregate_id,
            payload=deepcopy(dict(payload)),
            idempotency_key=idempotency_key,
            created_at=self._clock(),
            delivered_at=None,
            attempts=0,
        )
        self.outbox[message_id] = message
        self.outbox_dedupe[idempotency_key] = message_id
        return deepcopy(message)

    def correct(
        self,
        *,
        kind: EntityKind,
        record_id: str,
        payload: Mapping[str, Any],
        expected_version: int,
        reason: str,
    ) -> StoredRecord:
        _validate_payload(payload)
        try:
            current = self.records[(kind, record_id)]
        except KeyError as exc:
            raise RecordNotFound(record_id) from exc
        if current.version != expected_version:
            raise VersionConflict(
                f"{kind}:{record_id} expected version {expected_version}, "
                f"found {current.version}"
            )
        now = self._clock()
        corrected = StoredRecord(
            kind=kind,
            record_id=record_id,
            payload=deepcopy(dict(payload)),
            created_at=current.created_at,
            updated_at=now,
            expires_at=current.expires_at,
            dedupe_key=current.dedupe_key,
            version=current.version + 1,
        )
        self.records[(kind, record_id)] = corrected
        self.audit.append(_receipt("corrected", corrected, reason, now))
        return deepcopy(corrected)

    def delete(
        self,
        *,
        kind: EntityKind,
        record_id: str,
        reason: str,
    ) -> AuditReceipt:
        try:
            record = self.records.pop((kind, record_id))
        except KeyError as exc:
            raise RecordNotFound(record_id) from exc
        if record.dedupe_key is not None:
            self.dedupe.pop((kind, record.dedupe_key), None)
        receipt = _receipt("deleted", record, reason, self._clock())
        self.audit.append(receipt)
        return receipt


def _validate_payload(value: object, *, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS:
                raise PrivacyBoundaryError(f"{path}.{key} is forbidden")
            _validate_payload(nested, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _validate_payload(nested, path=f"{path}[{index}]")


def _receipt(
    action: str,
    record: StoredRecord,
    reason: str,
    occurred_at: datetime,
) -> AuditReceipt:
    identity = f"{action}:{record.kind}:{record.record_id}:{record.version}:{reason}"
    suffix = hashlib.sha256(identity.encode()).hexdigest()[:24]
    return AuditReceipt(
        receipt_id=f"audit_{suffix}",
        action=action,
        kind=record.kind,
        record_id=record.record_id,
        occurred_at=occurred_at,
        reason=reason,
        version=record.version,
    )
