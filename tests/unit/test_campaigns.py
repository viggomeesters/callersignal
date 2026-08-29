from __future__ import annotations

from datetime import UTC, datetime

from callersignal.campaigns import build_campaign

NOW = datetime(2026, 8, 29, 10, tzinfo=UTC)


def _evidence(
    source_id: str,
    evidence_id: str,
    *,
    evidence_class: str,
    verification_status: str,
) -> dict:
    return {
        "evidence_id": evidence_id,
        "source": {
            "source_id": source_id,
            "authority_type": (
                "moderated_community_aggregate"
                if evidence_class == "community_report_aggregate"
                else "licensed_data_provider"
            ),
        },
        "observation": {
            "evidence_class": evidence_class,
            "publication_status": "public",
            "verification_status": verification_status,
            "reason_codes": ["impersonation_pattern"],
        },
        "freshness": {"status": "current"},
    }


def _campaign(evidence: list[dict]) -> dict:
    return build_campaign(
        campaign_id="cmp_aggregation_example",
        title="Corroborated impersonation reports",
        members=[{"kind": "displayed_number", "value": "+1" + "202" + "555" + "0147"}],
        categories=["impersonation_attempt"],
        jurisdictions=["US"],
        evidence=evidence,
        first_seen=datetime(2026, 8, 20, 10, tzinfo=UTC),
        last_seen=datetime(2026, 8, 28, 10, tzinfo=UTC),
        assessed_at=NOW,
    )


def test_observed_community_aggregate_is_not_a_verified_independent_source() -> None:
    campaign = _campaign(
        [
            _evidence(
                "community_aggregate",
                "ev_community_observed",
                evidence_class="community_report_aggregate",
                verification_status="observed",
            ),
            _evidence(
                "licensed_feed",
                "ev_licensed_verified",
                evidence_class="licensed_reputation_observation",
                verification_status="verified",
            ),
        ]
    )

    assert campaign["status"] == "monitoring"
    assert campaign["risk_state"] == "insufficient_evidence"
    assert campaign["evidence"]["source_diversity"] == 1
    assert "verification_ineligible" in campaign["evidence"]["excluded_reason_codes"]


def test_verified_independent_sources_form_explainable_fresh_campaign() -> None:
    campaign = _campaign(
        [
            _evidence(
                "community_aggregate",
                "ev_community_verified",
                evidence_class="community_report_aggregate",
                verification_status="verified",
            ),
            _evidence(
                "licensed_feed",
                "ev_licensed_verified",
                evidence_class="licensed_reputation_observation",
                verification_status="verified",
            ),
        ]
    )

    assert campaign["status"] == "active"
    assert campaign["risk_state"] == "elevated_signals"
    assert campaign["confidence"] == {"level": "medium", "score": 0.65}
    assert campaign["freshness"] == {
        "as_of": "2026-08-29T10:00:00Z",
        "status": "current",
    }
    assert campaign["evidence"]["reason_codes"] == ["impersonation_pattern"]
    assert "identity" in campaign["limitations"][0].lower()
