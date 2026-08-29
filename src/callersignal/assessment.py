"""Calibrated phone-number risk states derived from eligible evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

_OFFICIAL_WARNING_REASONS = {
    "official_abuse_warning",
    "official_fraud_warning",
    "official_scam_warning",
}
_ELEVATED_EVIDENCE_CLASSES = {
    "community_report_aggregate",
    "licensed_reputation_observation",
}
_ELEVATED_PATTERN_REASONS = {
    "aggregate_status_nuisance",
    "aggregate_status_phishing",
    "aggregate_status_robocall",
    "aggregate_status_scam",
    "aggregate_status_spam",
    "aggregate_status_telemarketing",
    "corroborated_harmful_activity",
    "credential_theft_pattern",
    "impersonation_pattern",
    "payment_request_pattern",
}
_BLOCKING_RISK_GAPS = {
    "conflicting_evidence",
    "reuse_restricted",
    "source_error",
    "source_stale",
    "source_unavailable",
    "unsupported_country",
}


def assess_risk(
    *,
    evidence: Sequence[Mapping[str, Any]],
    gaps: Sequence[Mapping[str, Any]],
    sources_checked: Sequence[Mapping[str, Any]],
    checked_at: datetime,
) -> dict[str, Any]:
    """Return one uncertainty-honest risk state for the displayed number."""
    risk_checks = [item for item in sources_checked if item.get("risk_capable") is True]
    risk_source_ids = {str(item.get("source_id")) for item in risk_checks}
    risk_evidence = [
        item
        for item in evidence
        if str(item.get("source", {}).get("source_id")) in risk_source_ids
    ]
    official_warnings = [
        item
        for item in evidence
        if _is_current_public_risk_evidence(item)
        and str(item.get("source", {}).get("source_id")) in risk_source_ids
        and item.get("source", {}).get("authority_type") == "official_regulator"
        and item.get("observation", {}).get("evidence_class") == "regulatory_notice"
        and _OFFICIAL_WARNING_REASONS.intersection(
            item.get("observation", {}).get("reason_codes", [])
        )
    ]
    if official_warnings:
        return _explain(
            _risk_result(
                state="official_warning",
                headline="Official warning found",
                summary=(
                    "A current official source warns about activity associated with this "
                    "displayed number."
                ),
                reason_codes=_reason_codes(official_warnings),
                evidence=official_warnings,
                action_code="avoid_and_verify",
                action_message=(
                    "Do not act on the call; contact the claimed organisation through a trusted "
                    "channel."
                ),
            ),
            evidence=official_warnings,
            gaps=gaps,
            supporting_sources=risk_checks,
            checked_at=checked_at,
        )
    blocking_gaps = [
        item
        for item in gaps
        if item.get("source_id") in risk_source_ids
        and item.get("code") in _BLOCKING_RISK_GAPS
    ]
    if blocking_gaps:
        return _explain(
            _insufficient_result(sorted({str(item["code"]) for item in blocking_gaps})),
            evidence=risk_evidence,
            gaps=blocking_gaps,
            supporting_sources=risk_checks,
            checked_at=checked_at,
        )
    current_status_evidence = [
        item
        for item in risk_evidence
        if _is_current_public_risk_evidence(item)
        and item.get("observation", {}).get("claim_type") == "reputation_status"
    ]
    no_match_evidence = [
        item
        for item in current_status_evidence
        if item.get("observation", {}).get("reputation", {}).get("category")
        == "no_current_risk_match"
    ]
    harmful_status_evidence = [
        item for item in current_status_evidence if item not in no_match_evidence
    ]
    if no_match_evidence and harmful_status_evidence:
        return _explain(
            _insufficient_result(["conflicting_evidence"]),
            evidence=current_status_evidence,
            gaps=gaps,
            supporting_sources=risk_checks,
            checked_at=checked_at,
        )
    eligible_signals = [
        item
        for item in evidence
        if _is_current_public_risk_evidence(item)
        and str(item.get("source", {}).get("source_id")) in risk_source_ids
        and item.get("observation", {}).get("verification_status") == "verified"
        and item.get("observation", {}).get("evidence_class")
        in _ELEVATED_EVIDENCE_CLASSES
    ]
    corroborated_reason = _corroborated_reason(eligible_signals)
    if corroborated_reason is not None:
        corroborating_evidence = [
            item
            for item in eligible_signals
            if corroborated_reason
            in item.get("observation", {}).get("reason_codes", [])
        ]
        return _explain(
            _risk_result(
                state="elevated_signals",
                headline="Elevated risk signals",
                summary=(
                    "Multiple independent eligible sources report a consistent harmful-activity "
                    "pattern."
                ),
                reason_codes=[corroborated_reason],
                evidence=corroborating_evidence,
                action_code="avoid_sensitive_actions",
                action_message=(
                    "Do not share data, money, or device access; verify the caller independently."
                ),
            ),
            evidence=corroborating_evidence,
            gaps=gaps,
            supporting_sources=risk_checks,
            checked_at=checked_at,
        )
    covered_no_match_sources = {
        str(item.get("source_id"))
        for item in risk_checks
        if item.get("status") == "no_match"
    } | {
        str(item.get("source", {}).get("source_id")) for item in no_match_evidence
    }
    if risk_checks and all(
        str(item.get("source_id")) in covered_no_match_sources for item in risk_checks
    ):
        return _explain(
            {
                "state": "no_risk_evidence",
                "headline": "No risk evidence found",
                "summary": (
                    "Current eligible risk sources returned no match; this is not proof that the "
                    "number is safe."
                ),
                "reason_codes": ["eligible_risk_sources_no_match"],
                "evidence_ids": sorted(
                    str(item["evidence_id"]) for item in no_match_evidence
                ),
                "source_ids": sorted(str(item["source_id"]) for item in risk_checks),
                "recommended_action": {
                    "code": "stay_cautious",
                    "message": (
                        "Stay cautious and verify unexpected requests through a trusted channel."
                    ),
                },
            },
            evidence=no_match_evidence,
            gaps=gaps,
            supporting_sources=risk_checks,
            checked_at=checked_at,
        )
    insufficient_reasons = sorted(
        {
            str(item["code"])
            for item in gaps
            if item.get("source_id")
            in {check.get("source_id") for check in risk_checks}
        }
    )
    if not insufficient_reasons:
        insufficient_reasons = [
            "risk_source_gap" if risk_checks else "no_risk_capable_source_checked"
        ]
    return _explain(
        _insufficient_result(insufficient_reasons),
        evidence=risk_evidence,
        gaps=gaps,
        supporting_sources=risk_checks,
        checked_at=checked_at,
    )


def _insufficient_result(reason_codes: list[str]) -> dict[str, Any]:
    return {
        "state": "insufficient_evidence",
        "headline": "Not enough risk evidence",
        "summary": (
            "Numbering context does not show whether calls displaying this number are harmful."
        ),
        "reason_codes": reason_codes,
        "evidence_ids": [],
        "source_ids": [],
        "recommended_action": {
            "code": "treat_as_unknown",
            "message": (
                "Treat this result as unknown and verify unexpected requests through a trusted "
                "channel."
            ),
        },
    }


def _is_current_public_risk_evidence(item: Mapping[str, Any]) -> bool:
    observation = item.get("observation", {})
    return (
        item.get("freshness", {}).get("status") == "current"
        and observation.get("publication_status") == "public"
        and observation.get("verification_status") in {"observed", "verified"}
    )


def _reason_codes(evidence: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted(
        {
            str(reason)
            for item in evidence
            for reason in item.get("observation", {}).get("reason_codes", [])
        }
    )


def _corroborated_reason(evidence: Sequence[Mapping[str, Any]]) -> str | None:
    sources_by_reason: dict[str, set[str]] = {}
    for item in evidence:
        source_id = str(item.get("source", {}).get("source_id", ""))
        for reason in item.get("observation", {}).get("reason_codes", []):
            if reason in _ELEVATED_PATTERN_REASONS:
                sources_by_reason.setdefault(str(reason), set()).add(source_id)
    return next(
        (
            reason
            for reason, source_ids in sorted(sources_by_reason.items())
            if len(source_ids) >= 2
        ),
        None,
    )


def _risk_result(
    *,
    state: str,
    headline: str,
    summary: str,
    reason_codes: list[str],
    evidence: Sequence[Mapping[str, Any]],
    action_code: str,
    action_message: str,
) -> dict[str, Any]:
    return {
        "state": state,
        "headline": headline,
        "summary": summary,
        "reason_codes": reason_codes,
        "evidence_ids": sorted(str(item["evidence_id"]) for item in evidence),
        "source_ids": sorted(
            {str(item["source"]["source_id"]) for item in evidence}
        ),
        "recommended_action": {
            "code": action_code,
            "message": action_message,
        },
    }


def _explain(
    result: dict[str, Any],
    *,
    evidence: Sequence[Mapping[str, Any]],
    gaps: Sequence[Mapping[str, Any]],
    supporting_sources: Sequence[Mapping[str, Any]],
    checked_at: datetime,
) -> dict[str, Any]:
    state = str(result["state"])
    confidence = {
        "official_warning": {"level": "high", "score": 0.95},
        "elevated_signals": {"level": "medium", "score": 0.7},
        "no_risk_evidence": {"level": "medium", "score": 0.6},
        "insufficient_evidence": {"level": "none", "score": 0},
    }[state]
    source_ids = sorted(
        {
            str(item.get("source", {}).get("source_id"))
            for item in evidence
            if item.get("source", {}).get("source_id")
        }
        or {
            str(item.get("source_id"))
            for item in supporting_sources
            if item.get("source_id")
        }
    )
    result.update(
        {
            "confidence": confidence,
            "evidence_diversity": {
                "evidence_count": len(evidence),
                "source_count": len(source_ids),
                "source_ids": source_ids,
            },
            "freshness": {
                "as_of": checked_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                "status": _risk_freshness(evidence, gaps, supporting_sources),
            },
            "residual_uncertainty": (
                "Caller ID can be spoofed; this risk label describes eligible evidence about a "
                "displayed number and does not prove who placed a call or whether responding is "
                "safe."
            ),
        }
    )
    return result


def _risk_freshness(
    evidence: Sequence[Mapping[str, Any]],
    gaps: Sequence[Mapping[str, Any]],
    supporting_sources: Sequence[Mapping[str, Any]],
) -> str:
    evidence_statuses = {
        str(item.get("freshness", {}).get("status", "unknown")) for item in evidence
    }
    gap_codes = {str(item.get("code")) for item in gaps}
    if evidence_statuses == {"current"} and not gap_codes:
        return "current"
    if "current" in evidence_statuses:
        return "mixed"
    if "stale" in evidence_statuses or "source_stale" in gap_codes:
        return "stale"
    if any(item.get("status") == "no_match" for item in supporting_sources):
        return "current"
    if gap_codes.intersection({"source_unavailable", "source_error"}):
        return "unavailable"
    return "no_evidence"
