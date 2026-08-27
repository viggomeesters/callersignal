from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from callersignal.adapters.base import AdapterStatus
from callersignal.adapters.us import UnitedStatesNumberingAdapter
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
