from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from callersignal.campaigns import build_campaign

ROOT = Path(__file__).resolve().parents[2]


def _e164() -> str:
    return "+1" + "202" + "555" + "0147"


def _validator() -> Draft202012Validator:
    schema = json.loads(
        (ROOT / "schemas" / "caller-campaign.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _evidence(source_id: str, evidence_id: str) -> dict:
    return {
        "evidence_id": evidence_id,
        "source": {
            "source_id": source_id,
            "authority_type": "licensed_data_provider",
        },
        "observation": {
            "evidence_class": "licensed_reputation_observation",
            "publication_status": "public",
            "verification_status": "verified",
            "reason_codes": ["impersonation_pattern"],
        },
        "freshness": {"status": "current"},
    }


def _member() -> dict:
    return {"kind": "displayed_number", "value": _e164()}


def _build(evidence: list[dict]) -> dict:
    return build_campaign(
        campaign_id="cmp_reserved_example",
        title="Reported impersonation pattern",
        members=[_member()],
        categories=["impersonation_attempt"],
        jurisdictions=["US"],
        evidence=evidence,
        first_seen=datetime(2026, 8, 20, 10, tzinfo=UTC),
        last_seen=datetime(2026, 8, 28, 10, tzinfo=UTC),
        assessed_at=datetime(2026, 8, 29, 10, tzinfo=UTC),
    )


def test_two_independent_current_sources_form_a_schema_valid_campaign() -> None:
    campaign = _build(
        [
            _evidence("licensed_alpha", "ev_campaign_alpha"),
            _evidence("licensed_beta", "ev_campaign_beta"),
        ]
    )

    _validator().validate(campaign)
    assert campaign["status"] == "active"
    assert campaign["risk_state"] == "elevated_signals"
    assert campaign["evidence"]["source_diversity"] == 2
    assert campaign["membership"][0]["subject_semantics"] == "call_displayed_value"
    assert campaign["limitations"][0].lower().find("spoof") >= 0


def test_campaign_build_is_deterministic_across_evidence_order() -> None:
    evidence = [
        _evidence("licensed_alpha", "ev_campaign_alpha"),
        _evidence("licensed_beta", "ev_campaign_beta"),
    ]

    assert _build(deepcopy(evidence)) == _build(list(reversed(deepcopy(evidence))))


def test_stale_evidence_fails_closed_without_publishing_a_campaign() -> None:
    stale = _evidence("licensed_alpha", "ev_campaign_stale")
    stale["freshness"]["status"] = "stale"

    campaign = _build([stale])

    assert campaign["status"] == "monitoring"
    assert campaign["risk_state"] == "insufficient_evidence"
    assert campaign["freshness"]["status"] == "stale"
    assert campaign["evidence"]["eligible_evidence_ids"] == []
    assert "stale_or_unknown_freshness" in campaign["evidence"][
        "excluded_reason_codes"
    ]


def test_contradictory_evidence_opens_correction_review_and_fails_closed() -> None:
    current = _evidence("licensed_alpha", "ev_campaign_current")
    contradicted = _evidence("licensed_beta", "ev_campaign_contradicted")
    contradicted["observation"]["verification_status"] = "contradicted"

    campaign = _build([current, contradicted])

    assert campaign["status"] == "monitoring"
    assert campaign["risk_state"] == "insufficient_evidence"
    assert campaign["correction"] == {
        "status": "under_review",
        "updated_at": "2026-08-29T10:00:00Z",
        "reason_codes": ["contradictory_evidence"],
    }


def test_current_official_warning_can_activate_with_one_authoritative_source() -> None:
    warning = _evidence("regulator_example", "ev_campaign_warning")
    warning["source"]["authority_type"] = "official_regulator"
    warning["observation"].update(
        {
            "evidence_class": "regulatory_notice",
            "verification_status": "observed",
            "reason_codes": ["official_scam_warning"],
        }
    )

    campaign = _build([warning])

    assert campaign["status"] == "active"
    assert campaign["risk_state"] == "official_warning"
    assert campaign["confidence"] == {"level": "high", "score": 0.95}
    assert campaign["recommended_actions"][0] == "avoid_and_verify"


def test_bounded_pattern_requires_an_explicit_digit_bound() -> None:
    evidence = [
        _evidence("licensed_alpha", "ev_campaign_alpha"),
        _evidence("licensed_beta", "ev_campaign_beta"),
    ]

    campaign = build_campaign(
        campaign_id="cmp_reserved_pattern",
        title="Reported rotating display pattern",
        members=[
            {
                "kind": "bounded_pattern",
                "value": "+1" + "202" + "555" + "01",
                "following_digits": 2,
            }
        ],
        categories=["unwanted"],
        jurisdictions=["US"],
        evidence=evidence,
        first_seen=datetime(2026, 8, 20, 10, tzinfo=UTC),
        last_seen=datetime(2026, 8, 28, 10, tzinfo=UTC),
        assessed_at=datetime(2026, 8, 29, 10, tzinfo=UTC),
    )

    _validator().validate(campaign)
    assert campaign["membership"][0]["following_digits"] == 2


def test_invalid_campaign_timeline_is_rejected_before_publication() -> None:
    with pytest.raises(ValueError, match="first_seen"):
        build_campaign(
            campaign_id="cmp_invalid_timeline",
            title="Invalid timeline example",
            members=[_member()],
            categories=["unwanted"],
            jurisdictions=["US"],
            evidence=[],
            first_seen=datetime(2026, 8, 29, 10, tzinfo=UTC),
            last_seen=datetime(2026, 8, 20, 10, tzinfo=UTC),
            assessed_at=datetime(2026, 8, 29, 10, tzinfo=UTC),
        )


def test_independent_sources_without_a_shared_pattern_remain_insufficient() -> None:
    first = _evidence("licensed_alpha", "ev_campaign_alpha")
    second = _evidence("licensed_beta", "ev_campaign_beta")
    second["observation"]["reason_codes"] = ["payment_request_pattern"]

    campaign = _build([first, second])

    assert campaign["status"] == "monitoring"
    assert campaign["risk_state"] == "insufficient_evidence"
    assert "no_corroborated_pattern" in campaign["evidence"]["reason_codes"]
