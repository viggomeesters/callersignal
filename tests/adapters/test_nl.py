from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from callersignal.adapters.base import AdapterStatus
from callersignal.adapters.nl import NetherlandsNumberRegisterAdapter
from callersignal.numbering import normalize_phone_number

ROOT = Path(__file__).resolve().parents[2]
CHECKED_AT = datetime(2026, 8, 27, 9, 0, tzinfo=UTC)


def blocked_acm_number() -> dict:
    return normalize_phone_number("0906-8844", origin_region="NL")


def test_declaration_captures_acm_rights_freshness_and_portability_limits() -> None:
    declared = NetherlandsNumberRegisterAdapter().declaration

    assert declared.country_codes == ("NL",)
    assert declared.source_id == "acm_number_register"
    assert declared.authority_type == "official_regulator"
    assert declared.license == "CC0 1.0"
    assert "range_holder" in declared.permitted_claim_types
    assert declared.freshness_max_age_seconds == 2_592_000
    assert declared.failure_behavior == "typed_gap"
    assert any("current provider" in item for item in declared.portability_limitations)
    assert any("caller" in item for item in declared.portability_limitations)


def test_blocked_public_fixture_resolves_range_holder_and_regulatory_status() -> None:
    result = NetherlandsNumberRegisterAdapter().lookup(
        blocked_acm_number(),
        checked_at=CHECKED_AT,
    )

    assert result.status is AdapterStatus.MATCHED
    observations = {item["observation"]["claim_type"]: item for item in result.evidence}
    assert observations["range_holder"]["observation"]["value"] == (
        "Autoriteit Consument en Markt (ACM)"
    )
    assert observations["regulatory_status"]["observation"]["value"] == "blocked"
    assert all(item["observation"]["publication_status"] == "public" for item in result.evidence)
    assert all(item["freshness"]["status"] == "current" for item in result.evidence)


def test_range_holder_is_never_promoted_to_provider_subscriber_or_caller() -> None:
    result = NetherlandsNumberRegisterAdapter().lookup(
        blocked_acm_number(),
        checked_at=CHECKED_AT,
    )

    claim_types = {item["observation"]["claim_type"] for item in result.evidence}
    assert "current_provider_claim" not in claim_types
    assert "subscriber_identity_claim" not in claim_types
    for item in result.evidence:
        limitations = " ".join(item["observation"]["limitations"])
        assert "caller" in limitations
        assert "current provider" in limitations


def test_evidence_is_schema_valid_and_carries_pinned_provenance() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "source-evidence.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    result = NetherlandsNumberRegisterAdapter().lookup(
        blocked_acm_number(),
        checked_at=CHECKED_AT,
    )

    for item in result.evidence:
        validator.validate(item)
        assert item["provenance"]["source_record_id"] == "74716"
        assert item["provenance"]["content_digest"] == (
            "sha256:000fa25e8ce745254d085260f7f81dd4810189afb6620a25cf96e89f445715b4"
        )


def test_fixture_becomes_stale_without_turning_absence_into_safety() -> None:
    result = NetherlandsNumberRegisterAdapter().lookup(
        blocked_acm_number(),
        checked_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
    )

    assert result.status is AdapterStatus.STALE
    assert {item.code for item in result.gaps} == {"source_stale"}
    assert all(item["freshness"]["status"] == "stale" for item in result.evidence)
    assert not hasattr(result, "safe")
    assert not hasattr(result, "assessment")


def test_out_of_coverage_number_returns_an_explicit_unknown_gap() -> None:
    normalized = normalize_phone_number("0909-8844", origin_region="NL")
    result = NetherlandsNumberRegisterAdapter().lookup(normalized, checked_at=CHECKED_AT)

    assert result.status is AdapterStatus.NO_MATCH
    assert result.evidence == ()
    assert {item.code for item in result.gaps} == {"no_authoritative_data"}


def test_other_country_is_unsupported_instead_of_guessed() -> None:
    normalized = normalize_phone_number("202-555-0147", origin_region="US")
    result = NetherlandsNumberRegisterAdapter().lookup(normalized, checked_at=CHECKED_AT)

    assert result.status is AdapterStatus.UNSUPPORTED
    assert result.evidence == ()
    assert {item.code for item in result.gaps} == {"unsupported_country"}
