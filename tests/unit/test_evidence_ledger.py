import json
from datetime import UTC, datetime

import pytest

from callersignal.evidence.ledger import EvidenceLedger, EvidenceLedgerCorruptError


def evidence() -> dict:
    return {
        "schema_version": "1.0.0",
        "kind": "source_evidence",
        "evidence_id": "ev_reserved-example-range",
        "source": {"source_id": "nanpa", "name": "Numbering administrator"},
        "subject": {"canonical_e164": "+1" + "202" + "555" + "0147"},
        "observation": {"claim_type": "reserved_status", "value": "fictional_use"},
        "freshness": {"retrieved_at": "2026-08-27T08:00:00Z"},
        "provenance": {"content_digest": "sha256:" + ("ab" * 32)},
    }


def test_append_persists_a_timestamped_content_addressed_record(tmp_path) -> None:
    ledger_path = tmp_path / "evidence.jsonl"
    now = datetime(2026, 8, 27, 8, 30, tzinfo=UTC)
    ledger = EvidenceLedger(ledger_path, clock=lambda: now)

    record = ledger.append(evidence())

    assert record.record_id.startswith("sha256:")
    assert len(record.record_id) == len("sha256:") + 64
    assert record.recorded_at == "2026-08-27T08:30:00Z"
    assert record.source_id == "nanpa"
    assert list(EvidenceLedger(ledger_path).records()) == [record]


def test_appending_identical_evidence_is_idempotent(tmp_path) -> None:
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")

    first = ledger.append(evidence())
    second = ledger.append(evidence())

    assert second.record_id == first.record_id
    assert len(list(ledger.records())) == 1


def test_records_do_not_change_when_input_or_returned_views_are_mutated(tmp_path) -> None:
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    original = evidence()

    record = ledger.append(original)
    original["observation"]["value"] = "changed_after_append"
    returned_view = record.evidence
    returned_view["observation"]["value"] = "changed_returned_view"

    assert record.evidence["observation"]["value"] == "fictional_use"
    assert list(ledger.records())[0].evidence["observation"]["value"] == "fictional_use"


def test_replay_rejects_tampered_evidence(tmp_path) -> None:
    ledger_path = tmp_path / "evidence.jsonl"
    ledger = EvidenceLedger(ledger_path)
    ledger.append(evidence())
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    payload["evidence"]["observation"]["value"] = "tampered"
    ledger_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(EvidenceLedgerCorruptError, match="content address"):
        list(ledger.records())


def test_rebuild_derives_state_without_changing_observations(tmp_path) -> None:
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    first = evidence()
    second = evidence()
    second["evidence_id"] = "ev_second-source-record"
    second["source"] = {"source_id": "fcc", "name": "Public regulator"}
    ledger.append(first)
    ledger.append(second)
    original_records = list(ledger.records())

    counts = ledger.rebuild(
        {},
        lambda state, item: {**state, item.source_id: state.get(item.source_id, 0) + 1},
    )

    assert counts == {"nanpa": 1, "fcc": 1}
    assert list(ledger.records()) == original_records
