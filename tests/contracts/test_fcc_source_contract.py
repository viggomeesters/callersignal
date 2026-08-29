from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from callersignal.adapters.us import FCCUnwantedCallAggregateAdapter

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "sources/fcc-complaints-manifest.json"
SCHEMA_PATH = ROOT / "schemas/fcc-complaints-manifest.schema.json"
REGISTRY_PATH = ROOT / "sources/registry.json"
INDEX_PATH = ROOT / "sources/caller-report-services.json"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_manifest_is_schema_valid(manifest: dict, validator: Draft202012Validator) -> None:
    validator.validate(manifest)


def test_manifest_identity_and_rights_match_enabled_records(manifest: dict) -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    source = next(
        item for item in registry["sources"] if item["source_id"] == manifest["source_id"]
    )
    service = next(
        item for item in index["services"] if item["service_id"] == manifest["source_id"]
    )

    assert manifest["dataset_id"] == "vakf-fz8e"
    assert manifest["publisher"] == "Federal Communications Commission"
    assert manifest["license"]["name"] == "Public Domain U.S. Government"
    assert source["status"] == "enabled"
    assert source["source_type"] == "official_complaint_aggregate"
    assert source["authority"]["name"] == manifest["publisher"]
    assert source["reuse"]["license"] == manifest["license"]["name"]
    assert service["rights"]["reuse_status"] == "public_domain"
    assert service["integration"]["status"] == "enabled"
    assert service["integration"]["requires_contract"] is False
    assert service["integration"]["requires_credentials"] is False

    declaration = FCCUnwantedCallAggregateAdapter.declaration
    assert source["adapter_id"] == declaration.adapter_id
    assert source["adapter_enabled"] is True
    assert source["stable_url"] == declaration.source_url
    assert source["reuse"]["basis"] == declaration.reuse_basis
    assert source["reuse"]["license"] == declaration.license
    assert declaration.permitted_claim_types == ("reputation_status",)


def test_manifest_allows_only_minimized_input_fields(manifest: dict) -> None:
    assert manifest["fields"]["permitted"] == [
        "caller_id_number",
        "issue_date",
        "type_of_call_or_messge",
    ]
    assert set(manifest["fields"]["forbidden"]) == {
        "id",
        "issue_time",
        "issue_type",
        "method",
        "issue",
        "advertiser_business_phone_number",
        "state",
        "zip",
        "location_1",
    }
    assert manifest["storage"]["plaintext_phone_numbers"] == "forbidden"
    assert manifest["storage"]["raw_rows"] == "forbidden"
    assert manifest["storage"]["free_text"] == "forbidden"


def test_manifest_keeps_complaints_unverified_and_neutral(manifest: dict) -> None:
    semantics = manifest["semantics"]
    assert semantics["verification_status"] == "consumer_selected_unverified"
    assert semantics["official_warning_allowed"] is False
    assert semantics["caller_identity_allowed"] is False
    assert semantics["safe_verdict_allowed"] is False
    assert semantics["single_source_elevation_allowed"] is False
    assert semantics["spoofing_warning_required"] is True
    assert set(manifest["category_map"].values()) == {"nuisance", "robocall"}


def test_schema_rejects_a_forbidden_field_and_unsafe_semantic(
    manifest: dict, validator: Draft202012Validator
) -> None:
    unsafe = copy.deepcopy(manifest)
    unsafe["fields"]["permitted"].append("issue")
    unsafe["semantics"]["official_warning_allowed"] = True

    with pytest.raises(ValidationError):
        validator.validate(unsafe)
