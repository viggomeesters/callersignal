"""Build spoofing-aware caller campaigns from eligible aggregate evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

_ELIGIBLE_CLASSES = {
    "licensed_reputation_observation",
    "community_report_aggregate",
    "regulatory_notice",
}


def build_campaign(
    *,
    campaign_id: str,
    title: str,
    members: Sequence[Mapping[str, str]],
    categories: Sequence[str],
    jurisdictions: Sequence[str],
    evidence: Sequence[Mapping[str, Any]],
    first_seen: datetime,
    last_seen: datetime,
    assessed_at: datetime,
) -> dict[str, Any]:
    """Derive one deterministic campaign without asserting caller identity."""
    _validate_inputs(
        members=members,
        categories=categories,
        jurisdictions=jurisdictions,
        first_seen=first_seen,
        last_seen=last_seen,
        assessed_at=assessed_at,
    )
    eligible = sorted(
        (item for item in evidence if _is_eligible(item)),
        key=lambda item: str(item.get("evidence_id", "")),
    )
    source_ids = sorted(
        {str(item.get("source", {}).get("source_id", "")) for item in eligible}
    )
    observed_reason_codes = sorted(
        {
            str(reason)
            for item in eligible
            for reason in item.get("observation", {}).get("reason_codes", [])
        }
    )
    has_contradiction = any(
        item.get("observation", {}).get("verification_status") == "contradicted"
        for item in evidence
    )
    has_official_warning = any(_is_official_warning(item) for item in eligible)
    corroborated_reasons = _corroborated_reasons(eligible)
    active = (has_official_warning or bool(corroborated_reasons)) and not has_contradiction
    risk_state = (
        "official_warning"
        if active and has_official_warning
        else "elevated_signals"
        if active
        else "insufficient_evidence"
    )
    return {
        "schema_version": "1.0.0",
        "kind": "caller_campaign",
        "campaign_id": campaign_id,
        "title": title,
        "status": "active" if active else "monitoring",
        "risk_state": risk_state,
        "subject_semantics": "calls_displaying_numbers_or_patterns",
        "categories": sorted(set(categories)),
        "jurisdictions": sorted(set(jurisdictions)),
        "membership": [
            _campaign_member(member)
            for member in sorted(members, key=lambda item: (item["kind"], item["value"]))
        ],
        "timeline": {
            "first_seen": _timestamp(first_seen),
            "last_seen": _timestamp(last_seen),
            "published_at": _timestamp(assessed_at),
            "updated_at": _timestamp(assessed_at),
        },
        "evidence": {
            "eligible_evidence_ids": [str(item["evidence_id"]) for item in eligible],
            "source_ids": source_ids,
            "source_diversity": len(source_ids),
            "reason_codes": (
                observed_reason_codes
                if has_official_warning
                else corroborated_reasons
                if corroborated_reasons
                else ["no_corroborated_pattern"]
                if eligible
                else ["insufficient_eligible_evidence"]
            ),
            "excluded_reason_codes": _excluded_reasons(evidence),
        },
        "confidence": {
            "level": "high" if risk_state == "official_warning" else "medium" if active else "none",
            "score": 0.95 if risk_state == "official_warning" else 0.65 if active else 0,
        },
        "freshness": {
            "as_of": _timestamp(assessed_at),
            "status": _freshness_status(evidence, eligible),
        },
        "recommended_actions": [
            "avoid_and_verify"
            if risk_state == "official_warning"
            else "avoid_sensitive_actions"
            if active
            else "treat_as_unknown",
            "verify_through_trusted_channel",
        ],
        "correction": {
            "status": "under_review" if has_contradiction else "none",
            "updated_at": _timestamp(assessed_at) if has_contradiction else None,
            "reason_codes": ["contradictory_evidence"] if has_contradiction else [],
        },
        "limitations": [
            "Caller ID can be spoofed; membership describes displayed values, "
            "not caller or subscriber identity.",
            "Campaign evidence does not prove who placed any individual call.",
        ],
    }


def _is_eligible(item: Mapping[str, Any]) -> bool:
    observation = item.get("observation", {})
    evidence_class = observation.get("evidence_class")
    return (
        item.get("freshness", {}).get("status") == "current"
        and observation.get("publication_status") == "public"
        and _verification_is_eligible(
            evidence_class,
            observation.get("verification_status"),
        )
        and evidence_class in _ELIGIBLE_CLASSES
        and bool(item.get("source", {}).get("source_id"))
        and bool(item.get("evidence_id"))
    )


def _verification_is_eligible(evidence_class: object, status: object) -> bool:
    if status == "verified":
        return True
    return evidence_class == "regulatory_notice" and status == "observed"


def _validate_inputs(
    *,
    members: Sequence[Mapping[str, str]],
    categories: Sequence[str],
    jurisdictions: Sequence[str],
    first_seen: datetime,
    last_seen: datetime,
    assessed_at: datetime,
) -> None:
    if not members or not categories or not jurisdictions:
        raise ValueError("campaign members, categories, and jurisdictions are required")
    if first_seen.tzinfo is None or last_seen.tzinfo is None or assessed_at.tzinfo is None:
        raise ValueError("campaign timestamps must be timezone-aware")
    if first_seen > last_seen:
        raise ValueError("first_seen must not be later than last_seen")
    if last_seen > assessed_at:
        raise ValueError("last_seen must not be later than assessed_at")
    for member in members:
        if member.get("kind") == "bounded_pattern" and not member.get("following_digits"):
            raise ValueError("bounded_pattern requires following_digits")


def _campaign_member(member: Mapping[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "kind": str(member["kind"]),
        "value": str(member["value"]),
        "subject_semantics": "call_displayed_value",
        "identity_scope": "no_caller_or_subscriber_identity_claim",
    }
    if member["kind"] == "bounded_pattern":
        result["following_digits"] = int(member["following_digits"])
    return result


def _is_official_warning(item: Mapping[str, Any]) -> bool:
    source = item.get("source", {})
    observation = item.get("observation", {})
    return (
        source.get("authority_type") == "official_regulator"
        and observation.get("evidence_class") == "regulatory_notice"
        and any(
            str(reason).startswith("official_") and str(reason).endswith("_warning")
            for reason in observation.get("reason_codes", [])
        )
    )


def _corroborated_reasons(evidence: Sequence[Mapping[str, Any]]) -> list[str]:
    sources_by_reason: dict[str, set[str]] = {}
    for item in evidence:
        source_id = str(item.get("source", {}).get("source_id", ""))
        for reason in item.get("observation", {}).get("reason_codes", []):
            sources_by_reason.setdefault(str(reason), set()).add(source_id)
    return sorted(
        reason for reason, source_ids in sources_by_reason.items() if len(source_ids) >= 2
    )


def _excluded_reasons(evidence: Sequence[Mapping[str, Any]]) -> list[str]:
    reasons: set[str] = set()
    for item in evidence:
        if _is_eligible(item):
            continue
        observation = item.get("observation", {})
        if item.get("freshness", {}).get("status") != "current":
            reasons.add("stale_or_unknown_freshness")
        if observation.get("publication_status") != "public":
            reasons.add("publication_restricted")
        if observation.get("verification_status") == "contradicted":
            reasons.add("contradictory_evidence")
        elif not _verification_is_eligible(
            observation.get("evidence_class"),
            observation.get("verification_status"),
        ):
            reasons.add("verification_ineligible")
        if observation.get("evidence_class") not in _ELIGIBLE_CLASSES:
            reasons.add("evidence_class_ineligible")
    return sorted(reasons)


def _freshness_status(
    evidence: Sequence[Mapping[str, Any]],
    eligible: Sequence[Mapping[str, Any]],
) -> str:
    has_non_current = any(
        item.get("freshness", {}).get("status") != "current" for item in evidence
    )
    if eligible and has_non_current:
        return "mixed"
    if eligible:
        return "current"
    if has_non_current:
        return "stale"
    return "no_eligible_evidence"


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
