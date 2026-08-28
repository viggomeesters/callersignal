from __future__ import annotations

from datetime import UTC, datetime

import pytest

from callersignal.assessment import assess_risk

NOW = datetime(2026, 8, 28, 8, 0, tzinfo=UTC)


def numbering_evidence() -> dict:
    return {
        "evidence_id": "ev_numbering-context",
        "source": {
            "source_id": "official_numbering",
            "authority_type": "numbering_administrator",
        },
        "observation": {
            "evidence_class": "number_plan_fact",
            "claim_type": "regulatory_status",
            "publication_status": "public",
            "verification_status": "verified",
            "confidence": 1,
            "reason_codes": ["numbering_context_available"],
        },
        "freshness": {
            "status": "current",
            "retrieved_at": "2026-08-28T07:00:00Z",
        },
    }


def risk_evidence(
    *,
    evidence_id: str,
    source_id: str,
    evidence_class: str,
    authority_type: str,
    verification_status: str = "verified",
    freshness_status: str = "current",
    reason_codes: list[str] | None = None,
) -> dict:
    return {
        "evidence_id": evidence_id,
        "source": {
            "source_id": source_id,
            "authority_type": authority_type,
        },
        "observation": {
            "evidence_class": evidence_class,
            "claim_type": "reported_activity_summary",
            "publication_status": "public",
            "verification_status": verification_status,
            "confidence": 0.95,
            "reason_codes": reason_codes or ["corroborated_harmful_activity"],
        },
        "freshness": {
            "status": freshness_status,
            "retrieved_at": "2026-08-28T07:00:00Z",
        },
    }


def test_numbering_context_alone_is_insufficient_risk_evidence() -> None:
    risk = assess_risk(
        evidence=[numbering_evidence()],
        gaps=[],
        sources_checked=[
            {
                "source_id": "official_numbering",
                "status": "matched",
                "risk_capable": False,
            }
        ],
        checked_at=NOW,
    )

    assert risk["state"] == "insufficient_evidence"
    assert risk["reason_codes"] == ["no_risk_capable_source_checked"]
    assert risk["evidence_ids"] == []
    assert risk["recommended_action"]["code"] == "treat_as_unknown"


def test_current_official_warning_leads_the_risk_state() -> None:
    warning = risk_evidence(
        evidence_id="ev_official-warning",
        source_id="official_warning_feed",
        evidence_class="regulatory_notice",
        authority_type="official_regulator",
        reason_codes=["official_fraud_warning"],
    )

    risk = assess_risk(
        evidence=[warning],
        gaps=[],
        sources_checked=[
            {
                "source_id": "official_warning_feed",
                "status": "matched",
                "risk_capable": True,
            }
        ],
        checked_at=NOW,
    )

    assert risk["state"] == "official_warning"
    assert risk["reason_codes"] == ["official_fraud_warning"]
    assert risk["evidence_ids"] == ["ev_official-warning"]
    assert risk["source_ids"] == ["official_warning_feed"]
    assert risk["recommended_action"]["code"] == "avoid_and_verify"


def test_warning_evidence_from_a_non_risk_capable_check_cannot_raise_risk() -> None:
    warning = risk_evidence(
        evidence_id="ev_unqualified-warning",
        source_id="official_numbering",
        evidence_class="regulatory_notice",
        authority_type="official_regulator",
        reason_codes=["official_fraud_warning"],
    )

    risk = assess_risk(
        evidence=[warning],
        gaps=[],
        sources_checked=[
            {
                "source_id": "official_numbering",
                "status": "matched",
                "risk_capable": False,
            }
        ],
        checked_at=NOW,
    )

    assert risk["state"] == "insufficient_evidence"
    assert risk["reason_codes"] == ["no_risk_capable_source_checked"]


def test_two_independent_verified_sources_produce_elevated_signals() -> None:
    first = risk_evidence(
        evidence_id="ev_licensed-signal",
        source_id="licensed_reputation",
        evidence_class="licensed_reputation_observation",
        authority_type="licensed_data_provider",
        reason_codes=["credential_theft_pattern"],
    )
    second = risk_evidence(
        evidence_id="ev_moderated-signal",
        source_id="moderated_reports",
        evidence_class="community_report_aggregate",
        authority_type="moderated_community_aggregate",
        reason_codes=["credential_theft_pattern"],
    )

    risk = assess_risk(
        evidence=[first, second],
        gaps=[],
        sources_checked=[
            {"source_id": "licensed_reputation", "status": "matched", "risk_capable": True},
            {"source_id": "moderated_reports", "status": "matched", "risk_capable": True},
        ],
        checked_at=NOW,
    )

    assert risk["state"] == "elevated_signals"
    assert risk["reason_codes"] == ["credential_theft_pattern"]
    assert risk["evidence_ids"] == ["ev_licensed-signal", "ev_moderated-signal"]
    assert risk["source_ids"] == ["licensed_reputation", "moderated_reports"]
    assert risk["recommended_action"]["code"] == "avoid_sensitive_actions"


def test_current_risk_source_no_match_produces_no_risk_evidence_not_safe() -> None:
    risk = assess_risk(
        evidence=[],
        gaps=[
            {
                "gap_id": "gap_risk-no-match",
                "source_id": "licensed_reputation",
                "code": "no_authoritative_data",
                "message": "The eligible risk source returned no matching public observation.",
                "retryable": False,
            }
        ],
        sources_checked=[
            {
                "source_id": "licensed_reputation",
                "status": "no_match",
                "risk_capable": True,
            }
        ],
        checked_at=NOW,
    )

    assert risk["state"] == "no_risk_evidence"
    assert risk["reason_codes"] == ["eligible_risk_sources_no_match"]
    assert risk["source_ids"] == ["licensed_reputation"]
    assert "not proof" in risk["summary"].lower()
    assert risk["recommended_action"]["code"] == "stay_cautious"


def test_unverified_or_single_source_reports_cannot_elevate_risk() -> None:
    unverified = risk_evidence(
        evidence_id="ev_unverified-report",
        source_id="moderated_reports",
        evidence_class="community_report_aggregate",
        authority_type="moderated_community_aggregate",
        verification_status="unverified",
    )
    same_source = [
        risk_evidence(
            evidence_id=f"ev_same-source-{suffix}",
            source_id="licensed_reputation",
            evidence_class="licensed_reputation_observation",
            authority_type="licensed_data_provider",
        )
        for suffix in ("one", "two")
    ]
    sources = [
        {"source_id": "moderated_reports", "status": "matched", "risk_capable": True},
        {"source_id": "licensed_reputation", "status": "matched", "risk_capable": True},
    ]

    unverified_risk = assess_risk(
        evidence=[unverified], gaps=[], sources_checked=sources, checked_at=NOW
    )
    same_source_risk = assess_risk(
        evidence=same_source, gaps=[], sources_checked=sources, checked_at=NOW
    )

    assert unverified_risk["state"] == "insufficient_evidence"
    assert same_source_risk["state"] == "insufficient_evidence"


def test_stale_or_conflicting_risk_coverage_is_insufficient() -> None:
    stale = risk_evidence(
        evidence_id="ev_stale-report",
        source_id="licensed_reputation",
        evidence_class="licensed_reputation_observation",
        authority_type="licensed_data_provider",
        freshness_status="stale",
    )
    first = risk_evidence(
        evidence_id="ev_conflict-one",
        source_id="licensed_reputation",
        evidence_class="licensed_reputation_observation",
        authority_type="licensed_data_provider",
    )
    second = risk_evidence(
        evidence_id="ev_conflict-two",
        source_id="moderated_reports",
        evidence_class="community_report_aggregate",
        authority_type="moderated_community_aggregate",
    )
    stale_risk = assess_risk(
        evidence=[stale],
        gaps=[
            {
                "source_id": "licensed_reputation",
                "code": "source_stale",
            }
        ],
        sources_checked=[
            {"source_id": "licensed_reputation", "status": "stale", "risk_capable": True}
        ],
        checked_at=NOW,
    )
    conflicting_risk = assess_risk(
        evidence=[first, second],
        gaps=[
            {
                "source_id": "moderated_reports",
                "code": "conflicting_evidence",
            }
        ],
        sources_checked=[
            {"source_id": "licensed_reputation", "status": "matched", "risk_capable": True},
            {"source_id": "moderated_reports", "status": "matched", "risk_capable": True},
        ],
        checked_at=NOW,
    )

    assert stale_risk["state"] == "insufficient_evidence"
    assert stale_risk["reason_codes"] == ["source_stale"]
    assert conflicting_risk["state"] == "insufficient_evidence"
    assert conflicting_risk["reason_codes"] == ["conflicting_evidence"]


@pytest.mark.parametrize(
    "gap_code",
    [
        "source_unavailable",
        "source_error",
        "unsupported_country",
        "reuse_restricted",
    ],
)
def test_blocked_risk_coverage_cannot_produce_a_confident_state(
    gap_code: str,
) -> None:
    risk = assess_risk(
        evidence=[],
        gaps=[{"source_id": "licensed_reputation", "code": gap_code}],
        sources_checked=[
            {
                "source_id": "licensed_reputation",
                "status": "unavailable",
                "risk_capable": True,
            }
        ],
        checked_at=NOW,
    )

    assert risk["state"] == "insufficient_evidence"
    assert risk["reason_codes"] == [gap_code]
