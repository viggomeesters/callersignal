from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from callersignal.adapters.base import AdapterStatus
from callersignal.adapters.us import (
    FCCUnwantedCallAggregateAdapter,
    UnitedStatesNumberingAdapter,
)
from callersignal.fcc_catalog import build_fcc_catalog
from callersignal.numbering import normalize_phone_number

ROOT = Path(__file__).resolve().parents[2]
CHECKED_AT = datetime(2026, 8, 27, 9, 0, tzinfo=UTC)


def reserved_example() -> dict:
    return normalize_phone_number("202-555-0147", origin_region="US")


def test_declaration_records_nanpa_authority_rights_freshness_and_limits() -> None:
    declared = UnitedStatesNumberingAdapter().declaration

    assert declared.country_codes == ("US",)
    assert declared.source_id == "nanpa_public_numbering"
    assert declared.authority_type == "numbering_administrator"
    assert declared.license == "Public factual extract with source attribution"
    assert set(declared.permitted_claim_types) == {"regulatory_status", "reserved_status"}
    assert declared.freshness_max_age_seconds == 2_592_000
    assert declared.failure_behavior == "typed_gap"
    assert any("exact number" in item for item in declared.portability_limitations)
    assert any("caller" in item for item in declared.portability_limitations)


def test_reserved_example_resolves_with_area_code_and_line_level_context() -> None:
    result = UnitedStatesNumberingAdapter().lookup(reserved_example(), checked_at=CHECKED_AT)

    assert result.status is AdapterStatus.MATCHED
    by_claim = {item["observation"]["claim_type"]: item for item in result.evidence}
    assert by_claim["regulatory_status"]["observation"]["value"] == [
        "npa_assignable",
        "npa_assigned",
        "npa_in_service",
    ]
    assert by_claim["regulatory_status"]["subject"]["kind"] == "numbering_plan"
    assert by_claim["reserved_status"]["observation"]["value"] == "fictional_use"
    assert by_claim["reserved_status"]["subject"]["kind"] == "number_range"


def test_area_code_assignment_never_becomes_exact_number_assignment_or_identity() -> None:
    result = UnitedStatesNumberingAdapter().lookup(reserved_example(), checked_at=CHECKED_AT)
    serialized = json.dumps(result.evidence)

    assert "npa_assigned" in serialized
    assert "exact_number_assigned" not in serialized
    assert "subscriber_identity_claim" not in serialized
    assert "current_provider_claim" not in serialized
    for item in result.evidence:
        limitations = " ".join(item["observation"]["limitations"])
        assert "exact number" in limitations
        assert "caller" in limitations


def test_evidence_is_schema_valid_and_retains_each_pinned_source_digest() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "source-evidence.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    result = UnitedStatesNumberingAdapter().lookup(reserved_example(), checked_at=CHECKED_AT)

    assert {item["provenance"]["source_record_id"] for item in result.evidence} == {
        "npa-202",
        "555-fictional-line-range",
    }
    assert {item["provenance"]["content_digest"] for item in result.evidence} == {
        "sha256:4c1611c09388c2c9a032fccc7d5ac553e1e9d2e939232c94b6b025d1b15b085f",
        "sha256:1f059eb55910da3304fe5e027d55dec4d5c99d9d4d0c70400c03e38518736a59",
    }
    for item in result.evidence:
        validator.validate(item)


def test_stale_us_context_remains_evidence_but_not_a_current_conclusion() -> None:
    result = UnitedStatesNumberingAdapter().lookup(
        reserved_example(),
        checked_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
    )

    assert result.status is AdapterStatus.STALE
    assert {item.code for item in result.gaps} == {"source_stale"}
    assert all(item["freshness"]["status"] == "stale" for item in result.evidence)
    assert not hasattr(result, "assessment")
    assert not hasattr(result, "safe")


def test_unpinned_us_area_code_remains_explicitly_unknown() -> None:
    another_reserved_example = normalize_phone_number(
        "212-" + "555-" + "0147",
        origin_region="US",
    )
    result = UnitedStatesNumberingAdapter().lookup(
        another_reserved_example,
        checked_at=CHECKED_AT,
    )

    assert result.status is AdapterStatus.NO_MATCH
    assert result.evidence == ()
    assert {item.code for item in result.gaps} == {"no_authoritative_data"}


def test_non_us_number_is_unsupported_instead_of_inferred() -> None:
    gb_drama = normalize_phone_number("07700 " + "900" + "185", origin_region="GB")
    result = UnitedStatesNumberingAdapter().lookup(gb_drama, checked_at=CHECKED_AT)

    assert result.status is AdapterStatus.UNSUPPORTED
    assert result.evidence == ()
    assert {item.code for item in result.gaps} == {"unsupported_country"}


def _fcc_catalog(tmp_path: Path) -> tuple[Path, bytes]:
    lookup_key = b"test-only-fcc-lookup-key-32-bytes"
    payload = json.loads(
        (ROOT / "tests/fixtures/fcc_unwanted_calls_sample.json").read_text(
            encoding="utf-8"
        )
    )
    payload["metadata"]["rowsUpdatedAt"] = int(
        datetime.fromisoformat(
            payload.pop("source_updated_at").replace("Z", "+00:00")
        ).timestamp()
    )

    def fetch_json(url: str, params: dict[str, str]) -> Any:
        if not params:
            return payload["metadata"]
        offset = int(params["$offset"])
        limit = int(params["$limit"])
        return payload["rows"][offset : offset + limit]

    output = tmp_path / "fcc.sqlite3"
    build_fcc_catalog(
        ROOT / "sources/fcc-complaints-manifest.json",
        output,
        lookup_key=lookup_key,
        generated_at=datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        fetch_json=fetch_json,
    )
    return output, lookup_key


def test_fcc_aggregate_emits_unverified_count_bounded_neutral_evidence(
    tmp_path: Path,
) -> None:
    catalog, key = _fcc_catalog(tmp_path)
    adapter = FCCUnwantedCallAggregateAdapter(catalog_path=catalog, lookup_key=key)
    number = normalize_phone_number("202-555-0100", origin_region="US")

    result = adapter.lookup(number, checked_at=datetime(2026, 8, 29, 13, 0, tzinfo=UTC))

    assert result.status is AdapterStatus.MATCHED
    assert {item["observation"]["value"] for item in result.evidence} == {
        "nuisance",
        "robocall",
    }
    assert {item["observation"]["verification_status"] for item in result.evidence} == {
        "unverified"
    }
    assert {item["observation"]["evidence_class"] for item in result.evidence} == {
        "official_complaint_aggregate"
    }
    samples = {
        item["observation"]["reputation"]["category"]: item["observation"][
            "reputation"
        ]["aggregate"]
        for item in result.evidence
    }
    assert samples == {
        "nuisance": {
            "observation_count": 3,
            "first_observed_at": "2026-08-01T00:00:00Z",
            "last_observed_at": "2026-08-12T23:59:59Z",
        },
        "robocall": {
            "observation_count": 2,
            "first_observed_at": "2026-08-01T00:00:00Z",
            "last_observed_at": "2026-08-12T23:59:59Z",
        },
    }
    assert all(item["observation"]["confidence"] == 0.35 for item in result.evidence)
    assert all(
        "unverified" in " ".join(item["observation"]["limitations"]).lower()
        for item in result.evidence
    )
    schema = json.loads(
        (ROOT / "schemas/source-evidence.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for item in result.evidence:
        validator.validate(item)


def test_fcc_current_no_match_is_explicit_and_never_safe(tmp_path: Path) -> None:
    catalog, key = _fcc_catalog(tmp_path)
    adapter = FCCUnwantedCallAggregateAdapter(catalog_path=catalog, lookup_key=key)

    result = adapter.lookup(
        reserved_example(), checked_at=datetime(2026, 8, 29, 13, 0, tzinfo=UTC)
    )

    assert result.status is AdapterStatus.NO_MATCH
    assert result.evidence == ()
    assert {item.code for item in result.gaps} == {"no_authoritative_data"}
    assert "safe" not in " ".join(item.message for item in result.gaps).lower()


def test_fcc_missing_key_catalog_and_wrong_key_fail_with_typed_coverage(
    tmp_path: Path,
) -> None:
    catalog, key = _fcc_catalog(tmp_path)
    number = normalize_phone_number("202-555-0100", origin_region="US")
    checked_at = datetime(2026, 8, 29, 13, 0, tzinfo=UTC)

    missing_key = FCCUnwantedCallAggregateAdapter(catalog_path=catalog, lookup_key=None)
    missing_catalog = FCCUnwantedCallAggregateAdapter(
        catalog_path=tmp_path / "missing.sqlite3", lookup_key=key
    )
    wrong_key = FCCUnwantedCallAggregateAdapter(
        catalog_path=catalog, lookup_key=b"different-test-only-lookup-key-32b"
    )

    assert missing_key.lookup(number, checked_at=checked_at).status is AdapterStatus.UNAVAILABLE
    assert (
        missing_catalog.lookup(number, checked_at=checked_at).status
        is AdapterStatus.UNAVAILABLE
    )
    wrong_result = wrong_key.lookup(number, checked_at=checked_at)
    assert wrong_result.status is AdapterStatus.ERROR
    assert {item.code for item in wrong_result.gaps} == {"source_error"}


def test_fcc_default_adapter_reads_only_declared_environment_configuration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    catalog, key = _fcc_catalog(tmp_path)
    monkeypatch.setenv("CALLERSIGNAL_FCC_CATALOG_PATH", str(catalog))
    monkeypatch.setenv("CALLERSIGNAL_REPUTATION_INDEX_KEY", key.decode("utf-8"))

    result = FCCUnwantedCallAggregateAdapter().lookup(
        normalize_phone_number("202-555-0100", origin_region="US"),
        checked_at=datetime(2026, 8, 29, 13, 0, tzinfo=UTC),
    )

    assert result.status is AdapterStatus.MATCHED
    assert os.environ["CALLERSIGNAL_REPUTATION_INDEX_KEY"] not in json.dumps(
        result.evidence
    )


def test_fcc_stale_catalogue_returns_stale_evidence_and_typed_gap(tmp_path: Path) -> None:
    catalog, key = _fcc_catalog(tmp_path)

    result = FCCUnwantedCallAggregateAdapter(
        catalog_path=catalog,
        lookup_key=key,
    ).lookup(
        normalize_phone_number("202-555-0100", origin_region="US"),
        checked_at=datetime(2026, 9, 30, 13, 0, tzinfo=UTC),
    )

    assert result.status is AdapterStatus.STALE
    assert {item.code for item in result.gaps} == {"source_stale"}
    assert all(item["freshness"]["status"] == "stale" for item in result.evidence)
