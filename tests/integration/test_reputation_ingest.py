from __future__ import annotations

import copy
import json
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from callersignal.adapters.base import AdapterStatus
from callersignal.numbering import normalize_phone_number
from callersignal.reputation.feed import FeedHttpResponse
from callersignal.reputation.ingest import (
    ReputationRefreshScheduler,
    activate_reputation_feeds,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)
PHONE = normalize_phone_number("202-555-0147", origin_region="US")


class RecordingTransport:
    def __init__(self, *responses: FeedHttpResponse | Exception) -> None:
        self.responses = deque(responses)
        self.calls: list[dict] = []

    def post_json(self, **request: object) -> FeedHttpResponse:
        self.calls.append(request)
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


def load_documents() -> tuple[dict, dict]:
    registry = json.loads((ROOT / "sources/registry.json").read_text(encoding="utf-8"))
    index = json.loads(
        (ROOT / "sources/caller-report-services.json").read_text(encoding="utf-8")
    )
    return registry, index


def authorized_documents() -> tuple[dict, dict]:
    registry, index = load_documents()
    service = next(item for item in index["services"] if item["service_id"] == "tellows")
    service["rights"].update(
        {
            "reuse_status": "enabled",
            "evidence": (
                "A fixture agreement explicitly permits bounded aggregate status ingestion "
                "and public republication for this conformance test."
            ),
            "permission_reference": "https://www.tellows.com/s/about-en/tellows-api-partnership-program",
        }
    )
    service["integration"].update(
        {
            "status": "enabled",
            "permitted_fields": [
                "category_label",
                "last_reported_at",
                "reputation_score",
            ],
        }
    )
    service["activation"].update(
        {
            "decision": "enabled",
            "blocking_gates": [],
            "next_action": (
                "Operate the licensed aggregate feed under the reviewed runtime controls."
            ),
        }
    )

    source = copy.deepcopy(
        next(
            item
            for item in registry["sources"]
            if item["source_id"] == "wieheeftmijgebeld_nl"
        )
    )
    source.update(
        {
            "source_id": "tellows",
            "name": "tellows licensed reputation fixture",
            "source_type": "licensed_reputation",
            "status": "enabled",
            "adapter_id": "tellows_licensed_feed",
            "adapter_enabled": True,
            "jurisdictions": ["US"],
            "authority": {
                "type": "licensed_data_provider",
                "name": "tellows",
            },
            "stable_url": "https://www.tellows.com/",
            "evidence_classes": ["licensed_reputation_observation"],
            "risk_capable": True,
            "reuse": {
                "basis": (
                    "A fixture agreement permits aggregate reputation ingestion and "
                    "public republication for this conformance test."
                ),
                "license": "Fixture partner agreement",
                "license_url": None,
                "permission_reference": "https://www.tellows.com/s/about-en/tellows-api-partnership-program",
            },
            "intake": {
                "permitted_fields": [
                    "reputation_status",
                    "source_native_value",
                    "sample_basis",
                    "confidence",
                    "observed_at",
                    "source_record_id",
                ],
                "personal_data_allowed": False,
                "free_text_allowed": False,
                "freshness_max_age_seconds": 86400,
                "outage_behavior": "typed_gap",
            },
            "feed": {
                "transport": "licensed_https_json_api",
                "endpoint": "https://api.tellows.example/v1/reputation",
                "credential_env": "CALLERSIGNAL_TELLOWS_TOKEN",
                "requests_per_window": 2,
                "window_seconds": 60,
                "request_timeout_seconds": 5,
                "max_response_bytes": 65536,
                "schedule_seconds": 3600,
                "native_category_map": {
                    "junk": "spam",
                    "phish": "phishing",
                    "clear": "no_current_risk_match",
                },
            },
        }
    )
    for gate in source["gates"].values():
        gate.update(
            {
                "status": "passed",
                "evidence": (
                    "The fixture partner agreement and runbook satisfy this activation gate."
                ),
                "reference": "docs/source-rights.md",
            }
        )
    source["review"] = {
        "reviewed_at": "2026-08-29",
        "owner": "CallerSignal maintainers",
        "decision": (
            "Enabled only as a synthetic conformance fixture with bounded aggregate fields."
        ),
    }
    registry["sources"].append(source)
    registry["reviewed_at"] = "2026-08-29"
    return registry, index


def response(
    *,
    category: str = "junk",
    observed_at: str = "2026-08-29T09:30:00Z",
    confidence: float = 0.82,
) -> FeedHttpResponse:
    return FeedHttpResponse(
        status_code=200,
        content_type="application/json",
        body={
            "record_id": "provider-record-alpha",
            "category": category,
            "observed_at": observed_at,
            "confidence": confidence,
            "name": "must not enter processing",
            "narrative": "must not enter processing",
            "lookup_count": 999,
        },
        body_bytes=240,
    )


def activate(
    registry: dict,
    index: dict,
    transport: RecordingTransport,
    *,
    environment: dict[str, str] | None = None,
):
    return activate_reputation_feeds(
        registry=registry,
        service_index=index,
        environment=environment or {},
        transport_factory=lambda _definition: transport,
    )


def test_current_index_is_inert_and_performs_zero_requests() -> None:
    registry, index = load_documents()
    transport = RecordingTransport(response())

    activation = activate(registry, index, transport)
    scheduler = ReputationRefreshScheduler(activation.adapters)
    results = scheduler.run_due((PHONE,), checked_at=NOW)

    assert activation.indexed_count == 15
    assert activation.licensable_count == 4
    assert activation.enabled_count == 0
    assert activation.adapters == ()
    assert results == ()
    assert transport.calls == []


def test_authorized_fixture_is_valid_but_safe_mapping_is_not() -> None:
    registry, index = authorized_documents()
    registry_schema = json.loads(
        (ROOT / "schemas/source-registry.schema.json").read_text(encoding="utf-8")
    )
    index_schema = json.loads(
        (ROOT / "schemas/caller-report-service-index.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(registry_schema)
    Draft202012Validator(
        registry_schema, format_checker=FormatChecker()
    ).validate(registry)
    Draft202012Validator(index_schema, format_checker=FormatChecker()).validate(index)

    unsafe = copy.deepcopy(registry)
    unsafe["sources"][-1]["feed"]["native_category_map"] = {
        "safe": "no_current_risk_match"
    }
    with pytest.raises(ValidationError):
        Draft202012Validator(
            registry_schema, format_checker=FormatChecker()
        ).validate(unsafe)


def test_explicitly_authorized_feed_emits_only_schema_valid_aggregate_evidence() -> None:
    registry, index = authorized_documents()
    transport = RecordingTransport(response())
    activation = activate(
        registry,
        index,
        transport,
        environment={"CALLERSIGNAL_TELLOWS_TOKEN": "fixture-credential"},
    )

    assert activation.enabled_count == 1
    adapter = activation.adapters[0]
    result = adapter.lookup(PHONE, checked_at=NOW)

    assert result.status is AdapterStatus.MATCHED
    assert len(transport.calls) == 1
    assert transport.calls[0]["endpoint"] == "https://api.tellows.example/v1/reputation"
    assert transport.calls[0]["payload"] == {
        "phone_number": PHONE["canonical"]["e164"]
    }
    assert transport.calls[0]["credential"] == "fixture-credential"
    evidence = result.evidence[0]
    assert evidence["observation"]["value"] == "spam"
    assert evidence["observation"]["reputation"] == {
        "category": "spam",
        "source_native_value": "junk",
        "sample_basis": "licensed_provider_aggregate",
    }
    serialized = json.dumps(evidence)
    assert "must not enter processing" not in serialized
    assert "lookup_count" not in serialized
    schema = json.loads(
        (ROOT / "schemas/source-evidence.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(evidence)


def test_missing_credentials_keep_an_authorized_source_inert() -> None:
    registry, index = authorized_documents()
    transport = RecordingTransport(response())

    activation = activate(registry, index, transport)
    results = ReputationRefreshScheduler(activation.adapters).run_due(
        (PHONE,), checked_at=NOW
    )

    assert activation.enabled_count == 0
    tellows = next(item for item in activation.sources if item.source_id == "tellows")
    assert tellows.reason == "credentials_unavailable"
    assert results == ()
    assert transport.calls == []


def test_runtime_rejects_incomplete_gate_state_even_without_schema_validation() -> None:
    registry, index = authorized_documents()
    registry["sources"][-1]["gates"]["privacy"]["status"] = "required"
    transport = RecordingTransport(response())

    activation = activate(
        registry,
        index,
        transport,
        environment={"CALLERSIGNAL_TELLOWS_TOKEN": "fixture-credential"},
    )

    tellows = next(item for item in activation.sources if item.source_id == "tellows")
    assert tellows.reason == "registry_contract_invalid"
    assert activation.enabled_count == 0
    assert transport.calls == []


def test_rate_limit_refuses_excess_requests_without_calling_transport() -> None:
    registry, index = authorized_documents()
    source = registry["sources"][-1]
    source["feed"]["requests_per_window"] = 1
    transport = RecordingTransport(response(), response(category="phish"))
    activation = activate(
        registry,
        index,
        transport,
        environment={"CALLERSIGNAL_TELLOWS_TOKEN": "fixture-credential"},
    )
    adapter = activation.adapters[0]

    first = adapter.lookup(PHONE, checked_at=NOW)
    second = adapter.lookup(PHONE, checked_at=NOW + timedelta(seconds=1))

    assert first.status is AdapterStatus.MATCHED
    assert second.status is AdapterStatus.UNAVAILABLE
    assert second.gaps[0].code == "source_unavailable"
    assert len(transport.calls) == 1


def test_transport_outage_and_response_drift_fail_closed() -> None:
    registry, index = authorized_documents()
    outage = RecordingTransport(ConnectionError("fixture outage"))
    unavailable = activate(
        registry,
        index,
        outage,
        environment={"CALLERSIGNAL_TELLOWS_TOKEN": "fixture-credential"},
    ).adapters[0].lookup(PHONE, checked_at=NOW)

    assert unavailable.status is AdapterStatus.UNAVAILABLE
    assert unavailable.evidence == ()
    assert unavailable.gaps[0].code == "source_unavailable"

    drift = RecordingTransport(response(category="unexpected-provider-value"))
    failed = activate(
        registry,
        index,
        drift,
        environment={"CALLERSIGNAL_TELLOWS_TOKEN": "fixture-credential"},
    ).adapters[0].lookup(PHONE, checked_at=NOW)

    assert failed.status is AdapterStatus.ERROR
    assert failed.evidence == ()
    assert failed.gaps[0].code == "source_error"


def test_source_native_safe_claim_is_rejected_not_normalized_to_no_risk() -> None:
    registry, index = authorized_documents()
    transport = RecordingTransport(response(category="safe"))
    result = activate(
        registry,
        index,
        transport,
        environment={"CALLERSIGNAL_TELLOWS_TOKEN": "fixture-credential"},
    ).adapters[0].lookup(PHONE, checked_at=NOW)

    assert result.status is AdapterStatus.ERROR
    assert result.evidence == ()
    assert result.gaps[0].code == "source_error"


def test_stale_provider_observation_remains_stale_evidence() -> None:
    registry, index = authorized_documents()
    transport = RecordingTransport(response(observed_at="2026-08-20T09:30:00Z"))
    result = activate(
        registry,
        index,
        transport,
        environment={"CALLERSIGNAL_TELLOWS_TOKEN": "fixture-credential"},
    ).adapters[0].lookup(PHONE, checked_at=NOW)

    assert result.status is AdapterStatus.STALE
    assert result.evidence[0]["freshness"]["status"] == "stale"
    assert result.gaps[0].code == "source_stale"


def test_scheduler_tracks_only_source_time_and_skips_until_due() -> None:
    registry, index = authorized_documents()
    transport = RecordingTransport(response(), response(category="phish"))
    activation = activate(
        registry,
        index,
        transport,
        environment={"CALLERSIGNAL_TELLOWS_TOKEN": "fixture-credential"},
    )
    scheduler = ReputationRefreshScheduler(activation.adapters)

    first = scheduler.run_due((PHONE,), checked_at=NOW)
    skipped = scheduler.run_due((PHONE,), checked_at=NOW + timedelta(minutes=5))
    refreshed = scheduler.run_due((PHONE,), checked_at=NOW + timedelta(hours=1))

    assert len(first) == 1
    assert skipped == ()
    assert len(refreshed) == 1
    assert scheduler.last_attempts == {"tellows": NOW + timedelta(hours=1)}
    assert len(transport.calls) == 2
