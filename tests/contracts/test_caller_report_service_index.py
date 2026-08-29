from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas/caller-report-service-index.schema.json"
INDEX_PATH = ROOT / "sources/caller-report-services.json"


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def index() -> dict:
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator(schema: dict) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_discovery_index_is_schema_valid_and_international(
    schema: dict, index: dict, validator: Draft202012Validator
) -> None:
    Draft202012Validator.check_schema(schema)
    validator.validate(index)

    assert len(index["services"]) >= 15
    coverage = {service["coverage_scope"] for service in index["services"]}
    assert {"national", "international"} <= coverage
    assert index["discovery"]["queries"]
    assert index["discovery"]["limitations"]


def test_discovery_index_contains_known_nl_and_international_services(index: dict) -> None:
    service_ids = {service["service_id"] for service in index["services"]}
    assert {
        "wieheeftmijgebeld_nl",
        "onbekendnummer_nl",
        "wieheeftgebeld_nl",
        "tellows",
        "should_i_answer",
        "who_called_uk",
        "who_called_us",
        "who_calls_me",
        "robokiller",
        "nomorobo",
        "truecaller",
        "whoscall",
        "suscall",
        "whocall_me",
        "hiya",
    } <= service_ids
    assert len(service_ids) == len(index["services"])
    assert len({service["service_url"] for service in index["services"]}) == len(
        index["services"]
    )


def test_public_visibility_and_robots_never_enable_ingestion(index: dict) -> None:
    assert all(
        service["automation"]["grant_effect"] == "none"
        for service in index["services"]
    )
    assert all(
        service["integration"]["status"] == "disabled"
        for service in index["services"]
    )
    assert all(
        service["integration"]["permitted_fields"] == []
        for service in index["services"]
    )
    assert all(
        service["rights"]["reuse_status"] != "enabled"
        for service in index["services"]
    )


def test_index_distinguishes_available_licensed_routes_from_permission(index: dict) -> None:
    licensed_routes = {
        service["service_id"]
        for service in index["services"]
        if service["rights"]["reuse_status"] == "licensed_access_available"
    }
    assert {"tellows", "nomorobo", "whoscall", "hiya"} <= licensed_routes

    for service in index["services"]:
        if service["rights"]["reuse_status"] == "licensed_access_available":
            assert service["integration"]["channel"] in {"licensed_api", "partner_feed"}
            assert service["integration"]["requires_contract"] is True
            assert service["activation"]["decision"] == "evaluate_license"


def test_schema_rejects_enabling_a_source_without_documented_rights(
    index: dict, validator: Draft202012Validator
) -> None:
    unsafe_index = copy.deepcopy(index)
    service = unsafe_index["services"][0]
    service["integration"]["status"] = "enabled"
    service["integration"]["permitted_fields"] = ["category_label"]

    with pytest.raises(ValidationError):
        validator.validate(unsafe_index)


def test_index_contains_no_phone_records_or_copied_report_content(index: dict) -> None:
    forbidden_keys = {
        "phone_number",
        "numbers",
        "reports",
        "comments",
        "ratings",
        "lookup_count",
        "report_text",
        "report_records",
    }
    phone_like = re.compile(r"(?<![A-Fa-f0-9])(?:\d[ .()-]?){9,14}\d(?![A-Fa-f0-9])")
    date_like = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    def walk(value: object) -> None:
        if isinstance(value, dict):
            assert forbidden_keys.isdisjoint(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str):
            for match in phone_like.finditer(value):
                assert date_like.fullmatch(match.group(0))

    walk(index)
