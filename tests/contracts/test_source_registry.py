from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from callersignal.adapters.gb import UnitedKingdomProtectedNumbersAdapter
from callersignal.adapters.nl import NetherlandsNumberRegisterAdapter
from callersignal.adapters.us import UnitedStatesNumberingAdapter

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas/source-registry.schema.json"
REGISTRY_PATH = ROOT / "sources/registry.json"


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator(schema: dict) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _sources_by_id(registry: dict) -> dict[str, dict]:
    return {source["source_id"]: source for source in registry["sources"]}


def test_source_registry_schema_and_document_validate(
    schema: dict, registry: dict, validator: Draft202012Validator
) -> None:
    Draft202012Validator.check_schema(schema)
    validator.validate(registry)


def test_source_ids_are_unique(registry: dict) -> None:
    source_ids = [source["source_id"] for source in registry["sources"]]
    assert len(source_ids) == len(set(source_ids))


def test_enabled_sources_match_runtime_adapter_declarations(registry: dict) -> None:
    declarations = (
        NetherlandsNumberRegisterAdapter.declaration,
        UnitedKingdomProtectedNumbersAdapter.declaration,
        UnitedStatesNumberingAdapter.declaration,
    )
    enabled = {
        source["source_id"]: source
        for source in registry["sources"]
        if source["status"] == "enabled"
    }

    assert set(enabled) == {declaration.source_id for declaration in declarations}
    for declaration in declarations:
        source = enabled[declaration.source_id]
        assert source["adapter_id"] == declaration.adapter_id
        assert source["adapter_enabled"] is True
        assert source["jurisdictions"] == list(declaration.country_codes)
        assert source["authority"]["type"] == declaration.authority_type
        assert source["stable_url"] == declaration.source_url
        assert source["reuse"]["basis"] == declaration.reuse_basis
        assert source["reuse"]["license"] == declaration.license
        assert set(source["intake"]["permitted_fields"]) == set(
            declaration.permitted_claim_types
        )
        assert (
            source["intake"]["freshness_max_age_seconds"]
            == declaration.freshness_max_age_seconds
        )
        assert source["intake"]["outage_behavior"] == declaration.failure_behavior


def test_every_enabled_source_has_complete_machine_readable_intake_controls(
    registry: dict,
) -> None:
    required_gates = {
        "robots_access",
        "reuse_permission",
        "copyright",
        "database_rights",
        "privacy",
        "takedown",
        "provenance",
    }
    enabled = [source for source in registry["sources"] if source["status"] == "enabled"]

    assert enabled
    for source in enabled:
        assert source["authority"]["name"]
        assert source["stable_url"].startswith("https://")
        assert source["evidence_classes"]
        assert source["reuse"]["basis"]
        assert source["reuse"]["license"]
        assert source["intake"]["permitted_fields"]
        assert source["intake"]["freshness_max_age_seconds"] > 0
        assert source["intake"]["outage_behavior"] == "typed_gap"
        assert source["intake"]["personal_data_allowed"] is False
        assert source["intake"]["free_text_allowed"] is False
        assert set(source["gates"]) == required_gates
        assert all(
            gate["status"] in {"passed", "not_applicable"}
            for gate in source["gates"].values()
        )


def test_unlicensed_caller_report_site_is_permission_required_and_copies_nothing(
    registry: dict,
) -> None:
    candidate = _sources_by_id(registry)["wieheeftmijgebeld_nl"]

    assert candidate["source_type"] == "third_party_caller_reports"
    assert candidate["status"] == "permission_required"
    assert candidate["adapter_enabled"] is False
    assert candidate["adapter_id"] is None
    assert candidate["evidence_classes"] == []
    assert candidate["intake"]["permitted_fields"] == []
    assert candidate["intake"]["personal_data_allowed"] is False
    assert candidate["intake"]["free_text_allowed"] is False
    assert candidate["intake"]["freshness_max_age_seconds"] is None
    assert candidate["intake"]["outage_behavior"] == "disabled"
    assert candidate["gates"]["reuse_permission"]["status"] == "required"
    assert candidate["gates"]["copyright"]["status"] == "required"
    assert candidate["gates"]["database_rights"]["status"] == "required"
    assert candidate["gates"]["privacy"]["status"] == "required"
    assert candidate["gates"]["takedown"]["status"] == "required"
    assert candidate["gates"]["provenance"]["status"] == "required"


def test_robots_access_never_substitutes_for_reuse_permission(
    registry: dict,
) -> None:
    candidate = _sources_by_id(registry)["wieheeftmijgebeld_nl"]

    assert candidate["gates"]["robots_access"]["status"] == "passed"
    assert candidate["gates"]["reuse_permission"]["status"] == "required"
    assert candidate["status"] == "permission_required"


def test_schema_rejects_enabling_a_permission_required_candidate(
    registry: dict, validator: Draft202012Validator
) -> None:
    unsafe_registry = copy.deepcopy(registry)
    candidate = _sources_by_id(unsafe_registry)["wieheeftmijgebeld_nl"]
    candidate["status"] = "enabled"
    candidate["adapter_enabled"] = True

    with pytest.raises(ValidationError):
        validator.validate(unsafe_registry)


def test_schema_rejects_an_executable_disabled_source(
    registry: dict, validator: Draft202012Validator
) -> None:
    unsafe_registry = copy.deepcopy(registry)
    candidate = _sources_by_id(unsafe_registry)["wieheeftmijgebeld_nl"]
    candidate["status"] = "disabled"
    candidate["adapter_enabled"] = True

    with pytest.raises(ValidationError):
        validator.validate(unsafe_registry)


def test_official_numbering_sources_cannot_be_marked_risk_capable(
    registry: dict, validator: Draft202012Validator
) -> None:
    unsafe_registry = copy.deepcopy(registry)
    official_source = _sources_by_id(unsafe_registry)["acm_number_register"]
    official_source["risk_capable"] = True

    with pytest.raises(ValidationError):
        validator.validate(unsafe_registry)


def test_registry_contains_no_copied_reports_or_phone_records(registry: dict) -> None:
    forbidden_keys = {
        "phone_number",
        "numbers",
        "reports",
        "comments",
        "ratings",
        "lookup_count",
        "report_text",
    }

    def walk(value: object) -> None:
        if isinstance(value, dict):
            assert forbidden_keys.isdisjoint(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(registry)
