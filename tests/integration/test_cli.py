from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from callersignal.cli import main
from callersignal.lookup import LookupService

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 27, 9, 0, tzinfo=UTC)


def deterministic_service() -> LookupService:
    return LookupService(
        clock=lambda: NOW,
        lookup_id_factory=lambda: "lkp_cli-integration",
    )


def lookup_validator() -> Draft202012Validator:
    schemas = {
        name: json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        for name in (
            "phone-number.schema.json",
            "source-evidence.schema.json",
            "lookup-result.schema.json",
        )
    }
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )
    return Draft202012Validator(
        schemas["lookup-result.schema.json"],
        registry=registry,
        format_checker=FormatChecker(),
    )


def test_national_lookup_with_region_renders_agent_friendly_context(capsys) -> None:
    exit_code = main(
        ["lookup", "0906-8844", "--region", "NL"],
        lookup_service=deterministic_service(),
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Checking from Netherlands (NL)" in output
    assert "Local: 0906 8844" in output
    assert "International: " + "+31 " + "906 " + "8844" in output
    assert "Assessment: numbering context only" in output
    assert "Unknowns: none reported by the checked source" in output
    assert "Caller ID spoofing remains possible" in output


def test_international_input_needs_no_region_and_json_matches_shared_schema(capsys) -> None:
    international = "+1" + "202" + "555" + "0147"
    exit_code = main(
        ["lookup", international, "--json"],
        lookup_service=deterministic_service(),
    )
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert result["phone_number"]["origin_region"] is None
    assert result["phone_number"]["canonical"]["e164"] == international
    assert result["sources_checked"][0]["source_id"] == "nanpa_public_numbering"
    lookup_validator().validate(result)


def test_json_national_lookup_uses_the_same_lookup_service_result(capsys) -> None:
    expected = deterministic_service().lookup("0906-8844", origin_region="NL")
    exit_code = main(
        ["lookup", "0906-8844", "--region", "NL", "--json"],
        lookup_service=deterministic_service(),
    )
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert result == expected


def test_national_input_without_region_fails_with_actionable_guidance(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["lookup", "0906-8844"], lookup_service=deterministic_service())

    assert exc_info.value.code == 2
    assert "requires an origin region" in capsys.readouterr().err


def test_coverage_json_is_the_committed_projection(capsys) -> None:
    exit_code = main(["coverage", "--json"])
    result = json.loads(capsys.readouterr().out)
    committed = json.loads(
        (ROOT / "web/assets/transparency.json").read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert result == committed


def test_coverage_human_output_separates_available_context_from_missing_reputation(
    capsys,
) -> None:
    exit_code = main(["coverage"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Official NL number catalogue: available" in output
    assert "74,984 imported ranges" in output
    assert "73,409 lookup-compatible ranges" in output
    assert "16 caller-report services indexed" in output
    assert "4 advertised licensing routes" in output
    assert "1 reputation feed enabled" in output
    assert "Official US complaint aggregate: available · unverified" in output
    assert "238,327 keyed displayed numbers" in output
    assert "260,504 indexed observations" in output
    assert "2021-08-29 through 2026-08-29" in output
    assert "nuisance 144,783, robocall 115,721" in output
    assert "counts are not corroboration" in output
    assert "Coverage counts are not trust or safety scores." in output
