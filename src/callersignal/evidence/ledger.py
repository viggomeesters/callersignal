"""An append-only, content-addressed JSONL evidence ledger."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

State = TypeVar("State")


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """One immutable view of a persisted source observation."""

    record_id: str
    recorded_at: str
    source_id: str
    _canonical_evidence: str

    @property
    def evidence(self) -> dict[str, Any]:
        """Return a detached view so callers cannot mutate persisted state."""
        return json.loads(self._canonical_evidence)


class EvidenceLedgerCorruptError(ValueError):
    """Raised when persisted evidence no longer matches its content address."""


class EvidenceLedger:
    """Persist source observations without update or delete operations."""

    def __init__(
        self,
        path: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = path
        self._clock = clock or (lambda: datetime.now(UTC))

    def append(self, evidence: Mapping[str, Any]) -> EvidenceRecord:
        """Append an observation and return its content-addressed record."""
        canonical = json.dumps(
            evidence,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        record_id = f"sha256:{digest}"
        for existing in self.records():
            if existing.record_id == record_id:
                return existing
        recorded_at = self._clock().astimezone(UTC).isoformat().replace("+00:00", "Z")
        source_id = str(evidence["source"]["source_id"])
        payload = {
            "schema_version": "1.0.0",
            "event": "evidence_recorded",
            "record_id": record_id,
            "recorded_at": recorded_at,
            "source_id": source_id,
            "evidence": json.loads(canonical),
        }

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return _record_from_payload(payload)

    def records(self) -> Iterator[EvidenceRecord]:
        """Replay persisted observations in append order."""
        if not self._path.exists():
            return
        with self._path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield _record_from_payload(json.loads(line))

    def rebuild(
        self,
        initial: State,
        reducer: Callable[[State, EvidenceRecord], State],
    ) -> State:
        """Replay immutable records into newly derived state."""
        state = copy.deepcopy(initial)
        for record in self.records():
            state = reducer(state, record)
        return state


def _record_from_payload(payload: Mapping[str, Any]) -> EvidenceRecord:
    canonical_evidence = json.dumps(
        payload["evidence"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    expected_id = "sha256:" + hashlib.sha256(canonical_evidence.encode("utf-8")).hexdigest()
    if payload.get("record_id") != expected_id:
        raise EvidenceLedgerCorruptError("Evidence no longer matches its content address.")
    evidence_source_id = payload["evidence"]["source"]["source_id"]
    if payload.get("source_id") != evidence_source_id:
        raise EvidenceLedgerCorruptError("Ledger source attribution does not match evidence.")
    return EvidenceRecord(
        record_id=str(payload["record_id"]),
        recorded_at=str(payload["recorded_at"]),
        source_id=str(payload["source_id"]),
        _canonical_evidence=canonical_evidence,
    )
