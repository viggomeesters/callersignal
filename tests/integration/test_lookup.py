from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from callersignal.adapters.base import (
    AdapterResult,
    AdapterStatus,
    EvidenceGap,
    SourceDeclaration,
)
from callersignal.adapters.us import FCCUnwantedCallAggregateAdapter
from callersignal.evidence.ledger import EvidenceLedger
from callersignal.fcc_catalog import build_fcc_catalog
from callersignal.lookup import LookupService

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 27, 9, 0, tzinfo=UTC)


def service(*, adapters=None, ledger=None, now: datetime = NOW) -> LookupService:
    return LookupService(
        adapters=adapters,
        ledger=ledger,
        clock=lambda: now,
        lookup_id_factory=lambda: "lkp_integration-example",
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


def test_nl_lookup_records_interpretation_source_evidence_reasons_and_conclusions() -> None:
    result = service().lookup("0906-8844", origin_region="NL")

    assert result["lookup_id"] == "lkp_integration-example"
    assert result["generated_at"] == "2026-08-27T09:00:00Z"
    assert result["phone_number"]["origin_region"] == "NL"
    assert result["phone_number"]["interpretation"]["reason_codes"] == [
        "parsed_with_explicit_region"
    ]
    assert result["sources_checked"][0]["source_id"] == "acm_number_register"
    assert result["sources_checked"][0]["status"] == "matched"
    assert len(result["evidence"]) == 2
    assert result["gaps"] == []
    assert result["assessment"]["state"] == "numbering_context_only"
    assert "official_register_range_holder" in result["assessment"]["reason_codes"]
    assert {item["type"] for item in result["assessment"]["conclusions"]} == {
        "range_holder",
        "regulatory_status",
    }
    lookup_validator().validate(result)


def test_reserved_gb_range_routes_by_country_code_even_without_assigned_region() -> None:
    result = service().lookup("07700 " + "900" + "185", origin_region="GB")

    assert result["phone_number"]["canonical"]["region"] is None
    assert result["phone_number"]["canonical"]["country_calling_code"] == "44"
    assert result["sources_checked"][0]["source_id"] == "ofcom_protected_numbers"
    assert result["assessment"]["state"] == "numbering_context_only"
    assert result["assessment"]["conclusions"][0]["value"] == "protected_for_drama"
    lookup_validator().validate(result)


def test_us_lookup_preserves_plan_scope_and_reserved_line_scope() -> None:
    result = service().lookup("202-555-0147", origin_region="US")

    assert result["sources_checked"][0]["source_id"] == "nanpa_public_numbering"
    assert result["sources_checked"][0]["risk_capable"] is False
    assert len(result["evidence"]) == 2
    assert {item["subject"]["kind"] for item in result["evidence"]} == {
        "numbering_plan",
        "number_range",
    }
    assert {item["value"] for item in result["assessment"]["conclusions"]} == {
        "npa_assignable, npa_assigned, npa_in_service",
        "fictional_use",
    }
    assert result["assessment"]["risk"]["state"] == "insufficient_evidence"
    assert result["assessment"]["risk"]["reason_codes"] == [
        "source_unavailable"
    ]
    assert result["sources_checked"][1]["source_id"] == (
        "fcc_unwanted_call_complaints"
    )
    assert result["sources_checked"][1]["risk_capable"] is True
    assert result["sources_checked"][1]["status"] == "unavailable"
    assert result["assessment"]["risk"]["recommended_action"]["code"] == (
        "treat_as_unknown"
    )
    lookup_validator().validate(result)


def _fcc_adapter(tmp_path: Path) -> FCCUnwantedCallAggregateAdapter:
    lookup_key = b"test-only-fcc-lookup-key-32-bytes"
    payload = json.loads(
        (ROOT / "tests/fixtures/fcc_unwanted_calls_sample.json").read_text(
            encoding="utf-8"
        )
    )
    payload["metadata"]["rowsUpdatedAt"] = int(
        datetime.fromisoformat(
            payload.pop("source_updated_at").replace("Z", "+00:00")
        ).timestamp()
    )

    def fetch_json(url: str, params: dict[str, str]) -> Any:
        if not params:
            return payload["metadata"]
        offset = int(params["$offset"])
        limit = int(params["$limit"])
        return payload["rows"][offset : offset + limit]

    output = tmp_path / "fcc.sqlite3"
    build_fcc_catalog(
        ROOT / "sources/fcc-complaints-manifest.json",
        output,
        lookup_key=lookup_key,
        generated_at=datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        fetch_json=fetch_json,
    )
    return FCCUnwantedCallAggregateAdapter(
        catalog_path=output,
        lookup_key=lookup_key,
    )


def test_one_fcc_source_reports_activity_but_cannot_elevate_risk(
    tmp_path: Path,
) -> None:
    result = service(
        adapters=(_fcc_adapter(tmp_path),),
        now=datetime(2026, 8, 29, 13, 0, tzinfo=UTC),
    ).lookup("202-555-0100", origin_region="US")

    assert result["sources_checked"] == [
        {
            "source_id": "fcc_unwanted_call_complaints",
            "jurisdiction": "US",
            "status": "matched",
            "risk_capable": True,
            "checked_at": "2026-08-29T13:00:00Z",
            "evidence_ids": [item["evidence_id"] for item in result["evidence"]],
            "gap_ids": [],
        }
    ]
    assert result["assessment"]["state"] == "reported_activity"
    assert {item["value"] for item in result["assessment"]["conclusions"]} == {
        "nuisance",
        "robocall",
    }
    assert result["assessment"]["risk"]["state"] == "insufficient_evidence"
    assert result["assessment"]["risk"]["reason_codes"] == ["risk_source_gap"]
    assert result["assessment"]["risk"]["evidence_diversity"] == {
        "evidence_count": 2,
        "source_count": 1,
        "source_ids": ["fcc_unwanted_call_complaints"],
    }
    assert result["assessment"]["risk"]["state"] not in {
        "elevated_signals",
        "official_warning",
    }
    lookup_validator().validate(result)


def test_fcc_current_no_match_is_not_a_safe_verdict(tmp_path: Path) -> None:
    result = service(
        adapters=(_fcc_adapter(tmp_path),),
        now=datetime(2026, 8, 29, 13, 0, tzinfo=UTC),
    ).lookup("202-555-0147", origin_region="US")

    risk = result["assessment"]["risk"]
    assert risk["state"] == "no_risk_evidence"
    assert risk["reason_codes"] == ["eligible_risk_sources_no_match"]
    assert "not proof" in risk["summary"].lower()
    assert result["evidence"] == []
    lookup_validator().validate(result)


def test_no_match_is_unknown_with_a_source_specific_gap() -> None:
    result = service().lookup("0909-8844", origin_region="NL")

    assert result["sources_checked"][0]["status"] == "no_match"
    assert result["evidence"] == []
    assert result["gaps"][0]["source_id"] == "acm_number_register"
    assert result["gaps"][0]["code"] == "no_authoritative_data"
    assert result["assessment"]["state"] == "unknown"
    assert result["assessment"]["confidence"] == {"level": "none", "score": 0}
    assert result["assessment"]["conclusions"] == []
    lookup_validator().validate(result)


def test_eligible_risk_source_no_match_is_explicitly_not_a_safety_claim() -> None:
    class NoMatchRiskAdapter:
        declaration = SourceDeclaration(
            adapter_id="licensed_risk_example",
            country_codes=("NL",),
            source_id="licensed_risk_example",
            source_name="Licensed risk example",
            authority_type="licensed_data_provider",
            source_url="https://example.invalid/licensed-risk",
            reuse_basis="Licensed aggregate observations for contract conformance testing.",
            license="Contract fixture",
            permitted_claim_types=("reported_activity_summary",),
            freshness_max_age_seconds=3600,
            failure_behavior="typed_gap",
            portability_limitations=(
                "A displayed number does not prove the caller identity.",
            ),
        )

        def lookup(self, phone_number: dict, *, checked_at: datetime) -> AdapterResult:
            del phone_number
            return AdapterResult(
                declaration=self.declaration,
                jurisdiction="NL",
                status=AdapterStatus.NO_MATCH,
                checked_at=checked_at,
                gaps=(
                    EvidenceGap(
                        gap_id="gap_risk-no-match",
                        source_id=self.declaration.source_id,
                        code="no_authoritative_data",
                        message="The eligible risk source returned no matching observation.",
                        retryable=False,
                    ),
                ),
            )

    result = service(adapters=(NoMatchRiskAdapter(),)).lookup(
        "0906-8844", origin_region="NL"
    )

    assert result["sources_checked"][0]["risk_capable"] is True
    assert result["assessment"]["risk"]["state"] == "no_risk_evidence"
    assert "not proof" in result["assessment"]["risk"]["summary"].lower()
    lookup_validator().validate(result)


def test_licensed_reputation_status_is_neutral_public_evidence() -> None:
    class LicensedStatusAdapter:
        declaration = SourceDeclaration(
            adapter_id="licensed_status_example",
            country_codes=("NL",),
            source_id="licensed_status_example",
            source_name="Licensed status example",
            authority_type="licensed_data_provider",
            source_url="https://example.invalid/licensed-status",
            reuse_basis="Licensed aggregate status fields for contract conformance testing.",
            license="Contract fixture",
            permitted_claim_types=("reputation_status",),
            freshness_max_age_seconds=3600,
            failure_behavior="typed_gap",
            portability_limitations=(
                "A status about a displayed number does not identify the caller.",
            ),
        )

        def lookup(self, phone_number: dict, *, checked_at: datetime) -> AdapterResult:
            canonical = phone_number["canonical"]
            return AdapterResult(
                declaration=self.declaration,
                jurisdiction="NL",
                status=AdapterStatus.MATCHED,
                checked_at=checked_at,
                evidence=(
                    {
                        "schema_version": "1.0.0",
                        "kind": "source_evidence",
                        "evidence_id": "ev_licensed-status-phishing",
                        "source": {
                            "source_id": self.declaration.source_id,
                            "name": self.declaration.source_name,
                            "authority_type": self.declaration.authority_type,
                            "jurisdiction": "global",
                            "locator": self.declaration.source_url,
                            "reuse_basis": self.declaration.reuse_basis,
                            "license": self.declaration.license,
                        },
                        "subject": {
                            "kind": "phone_number",
                            "canonical_e164": canonical["e164"],
                            "range_prefix": None,
                        },
                        "observation": {
                            "evidence_class": "licensed_reputation_observation",
                            "claim_type": "reputation_status",
                            "value": "phishing",
                            "publication_status": "public",
                            "verification_status": "verified",
                            "confidence": 0.9,
                            "reason_codes": ["aggregate_status_phishing"],
                            "limitations": [
                                "This aggregate status does not identify the caller or subscriber."
                            ],
                            "reputation": {
                                "category": "phishing",
                                "source_native_value": "provider-phishing",
                                "sample_basis": "licensed_provider_aggregate",
                            },
                        },
                        "freshness": {
                            "retrieved_at": "2026-08-27T08:55:00Z",
                            "source_published_at": None,
                            "valid_until": "2026-08-27T09:55:00Z",
                            "status": "current",
                            "max_age_seconds": 3600,
                        },
                        "provenance": {
                            "source_document_id": "licensed-status-fixture",
                            "source_record_id": "aggregate-fixture",
                            "transformation_version": "1.0.0",
                            "content_digest": "sha256:" + ("cd" * 32),
                        },
                    },
                ),
            )

    result = service(adapters=(LicensedStatusAdapter(),)).lookup(
        "0906-8844", origin_region="NL"
    )

    assert result["sources_checked"][0]["risk_capable"] is True
    assert result["assessment"]["state"] == "reported_activity"
    assert result["assessment"]["conclusions"][0]["type"] == "reputation_status"
    assert result["assessment"]["conclusions"][0]["value"] == "phishing"
    assert "does not identify" in result["assessment"]["conclusions"][0]["wording"]
    assert result["assessment"]["risk"]["state"] == "insufficient_evidence"
    lookup_validator().validate(result)


def test_adapter_exception_becomes_a_gap_without_leaking_or_fabricating() -> None:
    class FailingAdapter:
        declaration = SourceDeclaration(
            adapter_id="failing_adapter",
            country_codes=("NL",),
            source_id="failing_source",
            source_name="Failing official example source",
            authority_type="official_regulator",
            source_url="https://example.invalid/source",
            reuse_basis="Public facts with attribution for conformance testing.",
            license="Example public terms",
            permitted_claim_types=("number_type",),
            freshness_max_age_seconds=3600,
            failure_behavior="typed_gap",
            portability_limitations=(
                "Number type does not establish provider, subscriber, or caller identity.",
            ),
        )

        def lookup(self, phone_number: dict, *, checked_at: datetime):
            raise RuntimeError("private upstream detail must not escape")

    result = service(adapters=(FailingAdapter(),)).lookup("0906-8844", origin_region="NL")
    serialized = json.dumps(result)

    assert result["sources_checked"][0]["status"] == "error"
    assert result["gaps"][0]["source_id"] == "failing_source"
    assert result["gaps"][0]["code"] == "source_error"
    assert result["assessment"]["state"] == "unavailable"
    assert "private upstream detail" not in serialized
    assert "identity_claim" not in serialized
    assert "reachability_claim" not in serialized
    assert '"safe"' not in serialized
    lookup_validator().validate(result)


def test_explicit_ledger_records_only_returned_source_observations(tmp_path) -> None:
    ledger = EvidenceLedger(tmp_path / "public-evidence.jsonl", clock=lambda: NOW)
    result = service(ledger=ledger).lookup("0906-8844", origin_region="NL")

    records = list(ledger.records())
    assert len(records) == len(result["evidence"]) == 2
    assert {record.evidence["evidence_id"] for record in records} == {
        item["evidence_id"] for item in result["evidence"]
    }
    assert all(record.source_id == "acm_number_register" for record in records)
