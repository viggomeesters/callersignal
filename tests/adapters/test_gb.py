from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from callersignal.adapters.base import AdapterStatus
from callersignal.adapters.gb import UnitedKingdomProtectedNumbersAdapter
from callersignal.numbering import normalize_phone_number

ROOT = Path(__file__).resolve().parents[2]
CHECKED_AT = datetime(2026, 8, 27, 9, 0, tzinfo=UTC)


def drama_mobile() -> dict:
    return normalize_phone_number("07700 " + "900" + "185", origin_region="GB")


def test_declaration_records_ofcom_authority_reuse_freshness_and_limits() -> None:
    declared = UnitedKingdomProtectedNumbersAdapter().declaration

    assert declared.country_codes == ("GB",)
    assert declared.source_id == "ofcom_protected_numbers"
    assert declared.authority_type == "official_regulator"
    assert declared.license == "Ofcom copyright and information re-use terms"
    assert declared.permitted_claim_types == ("reserved_status",)
    assert declared.freshness_max_age_seconds == 2_592_000
    assert declared.failure_behavior == "typed_gap"
    assert any("allocation" in item for item in declared.portability_limitations)
    assert any("caller" in item for item in declared.portability_limitations)


def test_official_drama_range_resolves_as_long_term_protected() -> None:
    result = UnitedKingdomProtectedNumbersAdapter().lookup(
        drama_mobile(),
        checked_at=CHECKED_AT,
    )

    assert result.status is AdapterStatus.MATCHED
    assert len(result.evidence) == 1
    observation = result.evidence[0]["observation"]
    assert observation["evidence_class"] == "number_plan_fact"
    assert observation["claim_type"] == "reserved_status"
    assert observation["value"] == "protected_for_drama"
    assert observation["publication_status"] == "public"
    assert "provider_claim" not in json.dumps(result.evidence)
    assert "identity_claim" not in json.dumps(result.evidence)


def test_evidence_is_schema_valid_with_pinned_ofcom_provenance() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "source-evidence.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    result = UnitedKingdomProtectedNumbersAdapter().lookup(
        drama_mobile(),
        checked_at=CHECKED_AT,
    )

    validator.validate(result.evidence[0])
    assert result.evidence[0]["provenance"]["source_record_id"] == "protected-mobile-drama"
    assert result.evidence[0]["provenance"]["content_digest"] == (
        "sha256:ee5244e03884a65e93189a730acc00f1c7f3ca62efb2f5c20ff7432b0dfbedc4"
    )


def test_stale_protected_range_remains_visible_but_unknown() -> None:
    result = UnitedKingdomProtectedNumbersAdapter().lookup(
        drama_mobile(),
        checked_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
    )

    assert result.status is AdapterStatus.STALE
    assert {item.code for item in result.gaps} == {"source_stale"}
    assert result.evidence[0]["freshness"]["status"] == "stale"
    assert not hasattr(result, "assessment")
    assert not hasattr(result, "safe")


def test_non_covered_gb_number_returns_no_authoritative_data() -> None:
    london_drama = normalize_phone_number("020 " + "7946 " + "0454", origin_region="GB")
    result = UnitedKingdomProtectedNumbersAdapter().lookup(
        london_drama,
        checked_at=CHECKED_AT,
    )

    assert result.status is AdapterStatus.NO_MATCH
    assert result.evidence == ()
    assert {item.code for item in result.gaps} == {"no_authoritative_data"}


def test_non_gb_number_is_unsupported_instead_of_inferred() -> None:
    us_example = normalize_phone_number("202-555-0147", origin_region="US")
    result = UnitedKingdomProtectedNumbersAdapter().lookup(
        us_example,
        checked_at=CHECKED_AT,
    )

    assert result.status is AdapterStatus.UNSUPPORTED
    assert result.evidence == ()
    assert {item.code for item in result.gaps} == {"unsupported_country"}
