from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from callersignal.reputation.ingest import activate_reputation_feeds

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "source-acquisition.schema.json"
ACQUISITION_PATH = ROOT / "sources" / "tellows-nl-acquisition.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_tellows_nl_acquisition_contract_is_schema_valid() -> None:
    schema = load(SCHEMA_PATH)
    acquisition = load(ACQUISITION_PATH)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(
        schema, format_checker=FormatChecker()
    ).validate(acquisition)
    assert acquisition["source_id"] == "tellows"
    assert acquisition["jurisdiction"] == "NL"
    assert acquisition["status"] == "selected_for_contract_review"


def test_selection_records_dutch_fit_and_why_hiya_is_deferred() -> None:
    acquisition = load(ACQUISITION_PATH)
    index = load(ROOT / "sources" / "caller-report-services.json")
    tellows = next(
        service for service in index["services"] if service["service_id"] == "tellows"
    )
    alternatives = {
        alternative["source_id"]: alternative
        for alternative in acquisition["selection"]["alternatives"]
    }

    assert tellows["jurisdictions"] == ["NL"]
    assert tellows["rights"]["reuse_status"] == "licensed_access_available"
    assert tellows["integration"]["status"] == "disabled"
    assert tellows["integration"]["permitted_fields"] == []
    assert alternatives["hiya"]["decision"] == "defer"
    assert "registered business numbers" in alternatives["hiya"]["reason"]


def test_candidate_contract_minimizes_fields_and_rejects_positive_safety() -> None:
    contract = load(ACQUISITION_PATH)["proposed_contract"]

    assert set(contract["permitted_provider_fields"]) == {
        "opaque_source_record_id",
        "reputation_score",
        "category_label",
        "observed_at",
    }
    assert {
        "caller_name",
        "comment_text",
        "comment_author",
        "area",
        "postal_code",
        "lookup_count",
        "raw_phone_inventory",
        "raw_provider_payload",
        "positive_safety_label",
    } == set(contract["prohibited_provider_fields"])
    assert contract["negative_score_floor"] == 7
    assert contract["positive_score_policy"] == "discard_not_safe_evidence"
    assert contract["assessment_limit"] == "unverified_single_source_observation_only"


def test_every_contract_and_operational_gate_remains_explicitly_required() -> None:
    acquisition = load(ACQUISITION_PATH)
    gates = {gate["gate_id"]: gate["status"] for gate in acquisition["activation_gates"]}

    assert gates == {
        "executed_agreement": "required",
        "extraction_right": "required",
        "cache_right": "required",
        "derived_label_right": "required",
        "public_display_right": "required",
        "nl_territory": "required",
        "attribution_terms": "required",
        "privacy_and_dpa": "required",
        "correction_objection_deletion": "required",
        "audit_and_provenance": "required",
        "termination_and_purge": "required",
        "credential_and_endpoint": "required",
        "fields_freshness_and_rate_limits": "required",
    }
    assert acquisition["runtime"] == {
        "enabled": False,
        "registry_entry_present": False,
        "adapter": "generic_authorized_reputation_feed",
        "expected_network_requests": 0,
    }


def test_uncontracted_candidate_cannot_activate_or_construct_a_transport() -> None:
    registry = load(ROOT / "sources" / "registry.json")
    index = load(ROOT / "sources" / "caller-report-services.json")

    def forbidden_transport(_definition: object) -> object:
        raise AssertionError("a disabled candidate must not construct a transport")

    activation = activate_reputation_feeds(
        registry=registry,
        service_index=index,
        environment={},
        transport_factory=forbidden_transport,
    )
    tellows = next(state for state in activation.sources if state.source_id == "tellows")

    assert activation.enabled_count == 0
    assert tellows.status == "disabled"
    assert tellows.reason == "rights_not_enabled"


def test_acquisition_artifact_contains_no_phone_records_or_copied_reports() -> None:
    serialized = ACQUISITION_PATH.read_text(encoding="utf-8")
    phone_like = re.compile(r"(?<![A-Fa-f0-9])(?:\d[ .()-]?){9,14}\d(?![A-Fa-f0-9])")

    assert not phone_like.search(serialized)
    assert "comment_text\"" in serialized
    assert "raw_phone_inventory\"" in serialized
