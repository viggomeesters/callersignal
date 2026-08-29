from __future__ import annotations

import json
import sqlite3
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


def write_catalog(
    path: Path,
    *,
    retrieved_at: str = "2026-08-27T08:30:00Z",
    register_status: str = "Geblokkeerd",
) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA user_version = 1;
            CREATE TABLE catalog_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE number_ranges (
                source_record_id TEXT PRIMARY KEY,
                national_from TEXT NOT NULL,
                national_to TEXT NOT NULL,
                e164_from INTEGER,
                e164_to INTEGER,
                destination TEXT NOT NULL,
                number_type TEXT NOT NULL,
                register_status TEXT NOT NULL,
                source_changed_at TEXT,
                source_row_sha256 TEXT NOT NULL
            ) WITHOUT ROWID;
            """
        )
        connection.executemany(
            "INSERT INTO catalog_metadata (key, value) VALUES (?, ?)",
            {
                "schema_version": "1.0.0",
                "source_id": "acm_number_register",
                "source_url": "https://www.acm.nl/nl/telefoonnummers-zoeken",
                "dataset_url": "https://data.overheid.nl/dataset/register-van-toegekende-telefoonnummers",
                "download_url": "https://www.acm.nl/sites/default/files/registers/nummers_csv.zip",
                "license": "CC0 1.0",
                "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                "retrieved_at": retrieved_at,
                "source_sha256": "a" * 64,
                "row_count": "1",
                "matchable_row_count": "1",
                "status_counts": '{"Geblokkeerd":1}',
                "destination_counts": '{"premium fixture":1}',
                "newest_mutation": "",
            }.items(),
        )
        connection.execute(
            """
            INSERT INTO number_ranges VALUES (
                'catalog-record', '09068844', '09068844', 319068844, 319068844,
                'premium fixture', 'premium_rate', ?, NULL,
                'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
            )
            """,
            (register_status,),
        )


def test_declaration_captures_acm_rights_freshness_and_portability_limits() -> None:
    declared = NetherlandsNumberRegisterAdapter().declaration

    assert declared.country_codes == ("NL",)
    assert declared.source_id == "acm_number_register"
    assert declared.authority_type == "official_regulator"
    assert declared.license == "CC0 1.0"
    assert "number_type" in declared.permitted_claim_types
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


def test_generated_catalog_is_preferred_and_emits_only_minimized_claims(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "acm.sqlite3"
    write_catalog(catalog_path)

    result = NetherlandsNumberRegisterAdapter(catalog_path=catalog_path).lookup(
        blocked_acm_number(),
        checked_at=CHECKED_AT,
    )

    assert result.status is AdapterStatus.MATCHED
    observations = {item["observation"]["claim_type"]: item for item in result.evidence}
    assert set(observations) == {"number_type", "regulatory_status"}
    assert observations["number_type"]["observation"]["value"] == "premium_rate"
    assert observations["regulatory_status"]["observation"]["value"] == "blocked"
    assert all(
        item["provenance"]["source_record_id"] == "catalog-record"
        for item in result.evidence
    )
    assert all(item["freshness"]["status"] == "current" for item in result.evidence)
    schema = json.loads(
        (ROOT / "schemas" / "source-evidence.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for item in result.evidence:
        validator.validate(item)
    assert "range_holder" not in json.dumps(result.evidence)
    assert "subscriber_identity_claim" not in json.dumps(result.evidence)
    assert "current_provider_claim" not in json.dumps(result.evidence)


def test_invalid_catalog_row_fails_closed_to_the_public_safe_fixture(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "acm.sqlite3"
    write_catalog(catalog_path, register_status="Unexpected")

    result = NetherlandsNumberRegisterAdapter(catalog_path=catalog_path).lookup(
        blocked_acm_number(),
        checked_at=CHECKED_AT,
    )

    assert result.status is AdapterStatus.MATCHED
    assert {item["observation"]["claim_type"] for item in result.evidence} == {
        "range_holder",
        "regulatory_status",
    }
    assert all(
        item["provenance"]["source_record_id"] == "74716" for item in result.evidence
    )


def test_missing_catalog_uses_fixture_only_for_its_documented_record(
    tmp_path: Path,
) -> None:
    adapter = NetherlandsNumberRegisterAdapter(catalog_path=tmp_path / "missing.sqlite3")

    fallback = adapter.lookup(blocked_acm_number(), checked_at=CHECKED_AT)
    uncovered = adapter.lookup(
        normalize_phone_number("0909-8844", origin_region="NL"),
        checked_at=CHECKED_AT,
    )

    assert fallback.status is AdapterStatus.MATCHED
    assert {item["provenance"]["source_record_id"] for item in fallback.evidence} == {
        "74716"
    }
    assert uncovered.status is AdapterStatus.UNAVAILABLE
    assert uncovered.evidence == ()
    assert {item.code for item in uncovered.gaps} == {"source_unavailable"}


def test_stale_catalog_evidence_remains_visible_but_fails_closed(tmp_path: Path) -> None:
    catalog_path = tmp_path / "acm.sqlite3"
    write_catalog(catalog_path, retrieved_at="2026-06-01T08:30:00Z")

    result = NetherlandsNumberRegisterAdapter(catalog_path=catalog_path).lookup(
        blocked_acm_number(),
        checked_at=CHECKED_AT,
    )

    assert result.status is AdapterStatus.STALE
    assert {item.code for item in result.gaps} == {"source_stale"}
    assert all(item["freshness"]["status"] == "stale" for item in result.evidence)
    assert {item["observation"]["claim_type"] for item in result.evidence} == {
        "number_type",
        "regulatory_status",
    }


def test_current_full_catalog_no_match_is_authoritative_no_data(tmp_path: Path) -> None:
    catalog_path = tmp_path / "acm.sqlite3"
    write_catalog(catalog_path)

    result = NetherlandsNumberRegisterAdapter(catalog_path=catalog_path).lookup(
        normalize_phone_number("0909-8844", origin_region="NL"),
        checked_at=CHECKED_AT,
    )

    assert result.status is AdapterStatus.NO_MATCH
    assert result.evidence == ()
    assert {item.code for item in result.gaps} == {"no_authoritative_data"}


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
