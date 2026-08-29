from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_NAMES = (
    "phone-number.schema.json",
    "source-evidence.schema.json",
    "lookup-result.schema.json",
    "call-report.schema.json",
)


def load_schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schemas() -> dict[str, dict]:
    return {name: load_schema(name) for name in SCHEMA_NAMES}


@pytest.fixture(scope="module")
def registry(schemas: dict[str, dict]) -> Registry:
    return Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )


def validator(name: str, schemas: dict[str, dict], registry: Registry) -> Draft202012Validator:
    return Draft202012Validator(
        schemas[name],
        registry=registry,
        format_checker=FormatChecker(),
    )


def fictional_e164() -> str:
    return "+1" + "202" + "555" + "0147"


def phone_number() -> dict:
    return {
        "schema_version": "1.0.0",
        "kind": "phone_number",
        "raw_input": "202-555-0147",
        "origin_region": "US",
        "interpretation": {
            "input_mode": "national",
            "region_source": "explicit_origin_region",
            "status": "valid",
            "reason_codes": ["parsed_with_explicit_region"],
        },
        "canonical": {
            "e164": fictional_e164(),
            "country_calling_code": "1",
            "region": "US",
            "national_significant_number": "202" + "555" + "0147",
            "number_type": "fixed_or_mobile",
        },
        "presentation": {
            "international": "+1 " + "202-555-0147",
            "national": "(202) 555-0147",
        },
    }


def evidence_id() -> str:
    return "ev_" + "reserved-example-range"


def source_evidence() -> dict:
    return {
        "schema_version": "1.0.0",
        "kind": "source_evidence",
        "evidence_id": evidence_id(),
        "source": {
            "source_id": "nanpa",
            "name": "North American Numbering Plan Administrator",
            "authority_type": "numbering_administrator",
            "jurisdiction": "US",
            "locator": "https://www.nationalnanpa.com/",
            "reuse_basis": "Public numbering-plan reference under documented source terms.",
            "license": "Source-specific public reuse terms",
        },
        "subject": {
            "kind": "phone_number",
            "canonical_e164": fictional_e164(),
            "range_prefix": "+1" + "202" + "555" + "01",
        },
        "observation": {
            "evidence_class": "number_plan_fact",
            "claim_type": "reserved_status",
            "value": "fictional_use",
            "publication_status": "public",
            "verification_status": "verified",
            "confidence": 1,
            "reason_codes": ["reserved_example_range"],
            "limitations": [
                "Numbering-plan status does not identify a subscriber or the originator of a call."
            ],
        },
        "freshness": {
            "retrieved_at": "2026-08-26T12:00:00Z",
            "source_published_at": None,
            "valid_until": None,
            "status": "current",
            "max_age_seconds": 2592000,
        },
        "provenance": {
            "source_document_id": "nanpa-reserved-numbers",
            "source_record_id": "fictional-use-range",
            "transformation_version": "1.0.0",
            "content_digest": "sha256:" + ("ab" * 32),
        },
    }


def reputation_evidence() -> dict:
    instance = source_evidence()
    instance["evidence_id"] = "ev_licensed-reputation-example"
    instance["source"].update(
        {
            "source_id": "licensed_reputation",
            "name": "Licensed reputation fixture",
            "authority_type": "licensed_data_provider",
            "jurisdiction": "global",
            "locator": "https://example.invalid/reputation",
            "reuse_basis": "Licensed aggregate status fields for public contract conformance.",
            "license": "Contract fixture",
        }
    )
    instance["subject"]["range_prefix"] = None
    instance["observation"].update(
        {
            "evidence_class": "licensed_reputation_observation",
            "claim_type": "reputation_status",
            "value": "phishing",
            "verification_status": "verified",
            "confidence": 0.9,
            "reason_codes": ["aggregate_status_phishing"],
            "reputation": {
                "category": "phishing",
                "source_native_value": "provider-phishing",
                "sample_basis": "licensed_provider_aggregate",
            },
            "limitations": [
                "The status describes aggregate evidence about a displayed number and does not "
                "identify a caller."
            ],
        }
    )
    return instance


def official_complaint_evidence() -> dict:
    instance = reputation_evidence()
    instance["evidence_id"] = "ev_fcc-unverified-aggregate"
    instance["source"].update(
        {
            "source_id": "fcc_unwanted_call_complaints",
            "name": "FCC unwanted-call complaints",
            "authority_type": "official_regulator",
            "locator": "https://opendata.fcc.gov/example",
            "reuse_basis": "Public-domain United States government dataset fixture.",
            "license": "Public Domain U.S. Government",
        }
    )
    instance["observation"].update(
        {
            "evidence_class": "official_complaint_aggregate",
            "value": "robocall",
            "verification_status": "unverified",
            "confidence": 0.35,
            "reason_codes": ["aggregate_status_robocall"],
            "reputation": {
                "category": "robocall",
                "source_native_value": "Prerecorded Voice",
                "sample_basis": "official_consumer_complaint_aggregate",
                "aggregate": {
                    "observation_count": 3,
                    "first_observed_at": "2026-08-20T00:00:00Z",
                    "last_observed_at": "2026-08-25T23:59:59Z",
                },
            },
        }
    )
    return instance


def lookup_result() -> dict:
    return {
        "schema_version": "1.0.0",
        "kind": "lookup_result",
        "lookup_id": "lkp_contract_example",
        "generated_at": "2026-08-26T12:00:01Z",
        "phone_number": phone_number(),
        "sources_checked": [
            {
                "source_id": "nanpa",
                "jurisdiction": "US",
                "status": "matched",
                "risk_capable": False,
                "checked_at": "2026-08-26T12:00:00Z",
                "evidence_ids": [evidence_id()],
                "gap_ids": [],
            }
        ],
        "evidence": [source_evidence()],
        "gaps": [],
        "assessment": {
            "state": "numbering_context_only",
            "confidence": {"level": "high", "score": 1},
            "reason_codes": ["reserved_example_range"],
            "provenance": {
                "policy_version": "1.0.0",
                "computed_at": "2026-08-26T12:00:01Z",
                "evidence_ids": [evidence_id()],
                "gap_ids": [],
            },
            "freshness": {
                "as_of": "2026-08-26T12:00:01Z",
                "oldest_evidence_at": "2026-08-26T12:00:00Z",
                "status": "current",
            },
            "conclusions": [
                {
                    "type": "regulatory_status",
                    "value": "fictional_use",
                    "confidence": 1,
                    "evidence_ids": [evidence_id()],
                    "wording": "This number belongs to a range reserved for fictional examples.",
                }
            ],
            "residual_risk": (
                "Caller ID can be spoofed; numbering context does not prove who placed a call."
            ),
            "risk": {
                "state": "insufficient_evidence",
                "headline": "Not enough risk evidence",
                "summary": (
                    "Numbering context alone cannot show whether calls displaying "
                    "this number are harmful."
                ),
                "reason_codes": ["no_risk_capable_source_checked"],
                "evidence_ids": [],
                "source_ids": [],
                "confidence": {"level": "none", "score": 0},
                "evidence_diversity": {
                    "evidence_count": 0,
                    "source_count": 0,
                    "source_ids": [],
                },
                "freshness": {
                    "as_of": "2026-08-26T12:00:01Z",
                    "status": "no_evidence",
                },
                "residual_uncertainty": (
                    "Caller ID can be spoofed; this label does not prove who placed a call."
                ),
                "recommended_action": {
                    "code": "treat_as_unknown",
                    "message": (
                        "Treat this result as unknown and verify unexpected requests independently."
                    ),
                },
            },
        },
    }


def call_report() -> dict:
    return {
        "schema_version": "1.0.0",
        "kind": "call_report",
        "report_id": "rpt_contract_example",
        "reported_at": "2026-08-26T12:05:00Z",
        "subject_semantics": "call_displayed_number",
        "displayed_number": phone_number(),
        "observation": {
            "direction": "inbound",
            "occurred_at": None,
            "channel": "voice",
            "contact_outcome": "unanswered",
            "categories": ["unwanted"],
        },
        "attestations": {
            "direct_observation": True,
            "understands_displayed_number_not_identity": True,
            "contains_no_sensitive_narrative": True,
        },
        "moderation": {
            "workflow_status": "pending",
            "verification_status": "unverified_observation",
            "reason_codes": [],
        },
        "privacy": {
            "policy_version": "1.0.0",
            "retention_policy_id": "community_report_default",
            "retention_until": "2027-02-26T12:05:00Z",
            "contains_free_text": False,
        },
        "submission": {
            "channel": "web",
            "receipt_id": "rcpt_contract_example",
        },
        "reporter_context": {"region": "US"},
    }


def test_all_domain_schemas_are_valid(schemas: dict[str, dict]) -> None:
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize(
    ("schema_name", "instance_factory"),
    [
        ("phone-number.schema.json", phone_number),
        ("source-evidence.schema.json", source_evidence),
        ("lookup-result.schema.json", lookup_result),
        ("call-report.schema.json", call_report),
    ],
)
def test_public_safe_contract_examples_validate(
    schema_name: str,
    instance_factory,
    schemas: dict[str, dict],
    registry: Registry,
) -> None:
    validator(schema_name, schemas, registry).validate(instance_factory())


def test_national_input_requires_an_explicit_origin_region(
    schemas: dict[str, dict], registry: Registry
) -> None:
    instance = phone_number()
    instance["origin_region"] = None

    with pytest.raises(ValidationError):
        validator("phone-number.schema.json", schemas, registry).validate(instance)


def test_international_input_uses_embedded_country_context(
    schemas: dict[str, dict], registry: Registry
) -> None:
    instance = phone_number()
    instance["raw_input"] = fictional_e164()
    instance["origin_region"] = None
    instance["interpretation"]["input_mode"] = "international"
    instance["interpretation"]["region_source"] = "embedded_country_code"

    validator("phone-number.schema.json", schemas, registry).validate(instance)


def test_source_observation_requires_rights_freshness_and_limitations(
    schemas: dict[str, dict], registry: Registry
) -> None:
    schema_validator = validator("source-evidence.schema.json", schemas, registry)
    for path in (
        ("source", "reuse_basis"),
        ("freshness", "status"),
        ("observation", "limitations"),
        ("provenance", "content_digest"),
    ):
        instance = source_evidence()
        del instance[path[0]][path[1]]
        with pytest.raises(ValidationError):
            schema_validator.validate(instance)


def test_reputation_status_has_a_bounded_neutral_contract(
    schemas: dict[str, dict], registry: Registry
) -> None:
    schema_validator = validator("source-evidence.schema.json", schemas, registry)
    schema_validator.validate(reputation_evidence())

    for mutation in ("safe", "unsupported-category", None):
        instance = reputation_evidence()
        if mutation == "safe":
            instance["observation"]["reputation"]["source_native_value"] = "safe"
        elif mutation == "unsupported-category":
            instance["observation"]["reputation"]["category"] = "dangerous_person"
        else:
            del instance["observation"]["reputation"]
        with pytest.raises(ValidationError):
            schema_validator.validate(instance)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("verification_status", "verified"),
        ("confidence", 0.5),
    ],
)
def test_official_complaint_aggregate_is_always_unverified_and_low_confidence(
    field: str,
    value: object,
    schemas: dict[str, dict],
    registry: Registry,
) -> None:
    schema_validator = validator("source-evidence.schema.json", schemas, registry)
    schema_validator.validate(official_complaint_evidence())
    instance = official_complaint_evidence()
    instance["observation"][field] = value

    with pytest.raises(ValidationError):
        schema_validator.validate(instance)


def test_official_complaint_aggregate_requires_count_dates_and_dedicated_basis(
    schemas: dict[str, dict], registry: Registry
) -> None:
    schema_validator = validator("source-evidence.schema.json", schemas, registry)
    without_aggregate = official_complaint_evidence()
    del without_aggregate["observation"]["reputation"]["aggregate"]
    wrong_basis = official_complaint_evidence()
    wrong_basis["observation"]["reputation"]["sample_basis"] = (
        "licensed_provider_aggregate"
    )

    with pytest.raises(ValidationError):
        schema_validator.validate(without_aggregate)
    with pytest.raises(ValidationError):
        schema_validator.validate(wrong_basis)


@pytest.mark.parametrize(
    "category",
    [
        "spam",
        "phishing",
        "scam",
        "telemarketing",
        "robocall",
        "nuisance",
        "no_current_risk_match",
    ],
)
def test_every_supported_reputation_category_validates(
    category: str, schemas: dict[str, dict], registry: Registry
) -> None:
    instance = reputation_evidence()
    instance["observation"]["value"] = category
    instance["observation"]["reason_codes"] = [f"aggregate_status_{category}"]
    instance["observation"]["reputation"].update(
        {
            "category": category,
            "source_native_value": f"provider-{category}",
            "sample_basis": (
                "source_no_match"
                if category == "no_current_risk_match"
                else "licensed_provider_aggregate"
            ),
        }
    )

    validator("source-evidence.schema.json", schemas, registry).validate(instance)


def test_assessment_requires_provenance_freshness_confidence_reasons_and_residual_risk(
    schemas: dict[str, dict], registry: Registry
) -> None:
    schema_validator = validator("lookup-result.schema.json", schemas, registry)
    for field in ("provenance", "freshness", "confidence", "reason_codes", "residual_risk"):
        instance = lookup_result()
        del instance["assessment"][field]
        with pytest.raises(ValidationError):
            schema_validator.validate(instance)


def test_lookup_demand_cannot_enter_an_assessment(
    schemas: dict[str, dict], registry: Registry
) -> None:
    instance = lookup_result()
    instance["assessment"]["lookup_count"] = 500

    with pytest.raises(ValidationError):
        validator("lookup-result.schema.json", schemas, registry).validate(instance)


def test_identity_claims_are_restricted_and_cannot_enter_public_results(
    schemas: dict[str, dict], registry: Registry
) -> None:
    restricted = source_evidence()
    restricted["observation"].update(
        {
            "evidence_class": "identity_claim",
            "claim_type": "subscriber_identity_claim",
            "value": "restricted_identity_record",
            "publication_status": "restricted",
            "verification_status": "unverified",
        }
    )
    evidence_validator = validator("source-evidence.schema.json", schemas, registry)
    evidence_validator.validate(restricted)

    unsafe_publication = copy.deepcopy(restricted)
    unsafe_publication["observation"]["publication_status"] = "public"
    with pytest.raises(ValidationError):
        evidence_validator.validate(unsafe_publication)

    public_result = lookup_result()
    public_result["evidence"] = [restricted]
    with pytest.raises(ValidationError):
        validator("lookup-result.schema.json", schemas, registry).validate(public_result)


def test_residual_risk_must_name_spoofing(
    schemas: dict[str, dict], registry: Registry
) -> None:
    instance = lookup_result()
    instance["assessment"]["residual_risk"] = (
        "Numbering context alone does not prove who placed a call or whether it was safe."
    )

    with pytest.raises(ValidationError):
        validator("lookup-result.schema.json", schemas, registry).validate(instance)


def test_report_is_an_unverified_observation_not_a_subscriber_claim(
    schemas: dict[str, dict], registry: Registry
) -> None:
    instance = call_report()
    instance["subscriber_owner"] = "Example Person"

    with pytest.raises(ValidationError):
        validator("call-report.schema.json", schemas, registry).validate(instance)


def test_assessment_references_only_returned_evidence_and_gaps() -> None:
    instance = lookup_result()
    evidence_ids = {item["evidence_id"] for item in instance["evidence"]}
    gap_ids = {item["gap_id"] for item in instance["gaps"]}
    provenance = instance["assessment"]["provenance"]

    assert set(provenance["evidence_ids"]) <= evidence_ids
    assert set(provenance["gap_ids"]) <= gap_ids
    conclusions = instance["assessment"]["conclusions"]
    assert all(set(item["evidence_ids"]) <= evidence_ids for item in conclusions)


def test_evidence_and_reports_cannot_be_mistaken_for_each_other(
    schemas: dict[str, dict], registry: Registry
) -> None:
    evidence_as_report = copy.deepcopy(source_evidence())
    report_as_evidence = copy.deepcopy(call_report())

    with pytest.raises(ValidationError):
        validator("call-report.schema.json", schemas, registry).validate(evidence_as_report)
    with pytest.raises(ValidationError):
        validator("source-evidence.schema.json", schemas, registry).validate(report_as_evidence)
