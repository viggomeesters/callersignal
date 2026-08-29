"""Build honest public corpus metrics without lookup-demand or raw-report totals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

_PASSED_GATES = {"passed", "not_applicable"}
_REQUIRED_GATES = {
    "robots_access",
    "reuse_permission",
    "copyright",
    "database_rights",
    "privacy",
    "takedown",
    "provenance",
}


def build_transparency_snapshot(
    *,
    source_registry: Mapping[str, Any],
    ingest_status: Mapping[str, Mapping[str, Any]],
    campaigns: Sequence[Mapping[str, Any]],
    verified_portfolios: Sequence[Mapping[str, Any]],
    community_aggregates: Sequence[Mapping[str, Any]],
    moderation: Mapping[str, Any],
    methodology_version: str,
    generated_at: datetime,
) -> dict[str, Any]:
    """Return a deterministic, public-safe transparency projection.

    The input intentionally has no lookup-demand parameter. Counts can come only
    from rights-enabled sources and records that pass their publication gate.
    """
    generated_at = _aware_utc(generated_at)
    sources = [item for item in source_registry.get("sources", []) if isinstance(item, Mapping)]
    enabled_sources = [item for item in sources if _source_is_enabled(item)]
    enabled_ids = {str(item["source_id"]) for item in enabled_sources}
    risk_ids = {
        str(item["source_id"])
        for item in enabled_sources
        if item.get("risk_capable") is True
    }
    source_coverage = [
        _source_coverage(item, ingest_status.get(str(item["source_id"])), generated_at)
        for item in enabled_sources
    ]
    source_coverage.sort(key=lambda item: item["source_id"])

    eligible_campaigns = [
        item for item in campaigns if _campaign_is_eligible(item, risk_ids)
    ]
    public_portfolios = [
        item for item in verified_portfolios if _portfolio_is_public(item, generated_at)
    ]
    public_aggregates = [
        item
        for item in community_aggregates
        if _aggregate_is_public(item, enabled_ids, risk_ids, moderation)
    ]

    unavailable_sources = _unavailable_sources(sources, source_coverage)
    jurisdictions = _jurisdiction_coverage(sources, source_coverage)
    campaign_corrections = sum(
        item.get("correction", {}).get("status") in {"corrected", "retracted"}
        for item in eligible_campaigns
    )
    portfolio_corrections = sum(
        item.get("correction", {}).get("status") in {"corrected", "appeal_resolved"}
        for item in public_portfolios
    )

    minimum = moderation.get("public_aggregate_minimum")
    minimum = minimum if isinstance(minimum, int) and minimum >= 2 else None
    independent_minimum = moderation.get("independent_observer_minimum")
    independent_minimum = (
        independent_minimum
        if isinstance(independent_minimum, int) and independent_minimum >= 2
        else None
    )
    moderation_status = str(moderation.get("status", "not_approved"))
    if moderation_status != "approved" or minimum is None:
        moderation_status = "not_approved"
        minimum = None

    return {
        "schema_version": "1.0.0",
        "kind": "corpus_transparency",
        "generated_at": _timestamp(generated_at),
        "methodology_version": methodology_version,
        "registry_reviewed_at": source_registry.get("reviewed_at"),
        "coverage": {
            "enabled_source_count": len(enabled_sources),
            "risk_capable_source_count": len(risk_ids),
            "sources": source_coverage,
            "jurisdictions": jurisdictions,
            "unavailable_sources": unavailable_sources,
        },
        "corpus": {
            "eligible_campaigns": len(eligible_campaigns),
            "verified_organization_portfolios": len(public_portfolios),
            "privacy_thresholded_aggregates": len(public_aggregates),
            "corrections": {
                "campaigns": campaign_corrections,
                "organization_portfolios": portfolio_corrections,
            },
        },
        "moderation": {
            "status": moderation_status,
            "public_aggregate_minimum": minimum,
            "independent_observer_minimum": independent_minimum,
            "public_free_text_allowed": False,
        },
        "interpretation": {
            "no_matching_evidence": (
                "No matching evidence means only that eligible sources returned no "
                "publishable match; it does not mean a displayed number is safe."
            ),
            "lookup_popularity_used_for_reputation": False,
            "excluded_public_totals": [
                "lookup_demand",
                "raw_reports",
                "reporter_identities",
                "watch_subscribers",
            ],
        },
    }


def _source_is_enabled(source: Mapping[str, Any]) -> bool:
    if source.get("status") != "enabled" or source.get("adapter_enabled") is not True:
        return False
    source_id = source.get("source_id")
    jurisdictions = source.get("jurisdictions")
    if not isinstance(source_id, str) or not isinstance(jurisdictions, list):
        return False
    if not jurisdictions or any(not isinstance(item, str) for item in jurisdictions):
        return False
    gates = source.get("gates")
    if not isinstance(gates, Mapping) or not _REQUIRED_GATES <= set(gates):
        return False
    return all(
        isinstance(gates[name], Mapping)
        and gates[name].get("status") in _PASSED_GATES
        for name in _REQUIRED_GATES
    )


def _source_coverage(
    source: Mapping[str, Any],
    runtime: Mapping[str, Any] | None,
    generated_at: datetime,
) -> dict[str, Any]:
    runtime = runtime if isinstance(runtime, Mapping) else {}
    runtime_status = str(runtime.get("status", "unavailable"))
    last_ingest = _parse_timestamp(runtime.get("last_successful_ingest"))
    maximum_age = source.get("intake", {}).get("freshness_max_age_seconds")
    gaps: list[str] = []
    if last_ingest is None:
        freshness = "unavailable"
        gaps.append("last_successful_ingest_unavailable")
    elif not isinstance(maximum_age, int) or maximum_age < 1:
        freshness = "unavailable"
        gaps.append("freshness_policy_unavailable")
    elif (generated_at - last_ingest).total_seconds() > maximum_age:
        freshness = "stale"
        gaps.append("source_stale")
    else:
        freshness = "current"
    if runtime_status != "success":
        gaps.append("source_currently_unavailable")
    return {
        "source_id": source["source_id"],
        "name": source.get("name", source["source_id"]),
        "jurisdictions": sorted(source["jurisdictions"]),
        "risk_capable": source.get("risk_capable") is True,
        "runtime_status": runtime_status,
        "last_successful_ingest": _timestamp(last_ingest) if last_ingest else None,
        "freshness": freshness,
        "freshness_max_age_seconds": maximum_age,
        "gaps": gaps,
    }


def _campaign_is_eligible(campaign: Mapping[str, Any], risk_ids: set[str]) -> bool:
    if campaign.get("status") not in {"active", "resolved", "retracted"}:
        return False
    if campaign.get("correction", {}).get("status") == "under_review":
        return False
    evidence = campaign.get("evidence")
    if not isinstance(evidence, Mapping):
        return False
    source_ids = evidence.get("source_ids")
    evidence_ids = evidence.get("eligible_evidence_ids")
    diversity = evidence.get("source_diversity")
    if not isinstance(source_ids, list) or any(not isinstance(item, str) for item in source_ids):
        return False
    if not isinstance(evidence_ids, list) or any(
        not isinstance(item, str) for item in evidence_ids
    ):
        return False
    if not isinstance(diversity, int) or diversity != len(set(source_ids)):
        return False
    if not set(source_ids) <= risk_ids:
        return False
    if campaign.get("risk_state") == "official_warning":
        return diversity >= 1 and len(evidence_ids) >= 1
    return (
        campaign.get("risk_state") == "elevated_signals"
        and diversity >= 2
        and len(evidence_ids) >= 2
    )


def _portfolio_is_public(portfolio: Mapping[str, Any], generated_at: datetime) -> bool:
    if portfolio.get("status") != "verified":
        return False
    if portfolio.get("correction", {}).get("status") == "under_review":
        return False
    valid_until = _parse_timestamp(portfolio.get("verification", {}).get("valid_until"))
    return valid_until is not None and valid_until >= generated_at


def _aggregate_is_public(
    aggregate: Mapping[str, Any],
    enabled_ids: set[str],
    risk_ids: set[str],
    moderation: Mapping[str, Any],
) -> bool:
    minimum = moderation.get("public_aggregate_minimum")
    if moderation.get("status") != "approved" or not isinstance(minimum, int) or minimum < 2:
        return False
    privacy = aggregate.get("privacy")
    if not isinstance(privacy, Mapping):
        return False
    return (
        aggregate.get("source_id") in enabled_ids
        and aggregate.get("source_id") in risk_ids
        and aggregate.get("publication_status") == "public"
        and aggregate.get("verification_status") == "verified"
        and privacy.get("threshold_met") is True
        and isinstance(privacy.get("cohort_size"), int)
        and privacy["cohort_size"] >= minimum
    )


def _unavailable_sources(
    sources: Sequence[Mapping[str, Any]],
    coverage: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    unavailable = []
    covered_ids = {str(item["source_id"]) for item in coverage}
    for source in sources:
        source_id = source.get("source_id")
        if not isinstance(source_id, str):
            continue
        if source_id not in covered_ids:
            unavailable.append(
                {
                    "source_id": source_id,
                    "jurisdictions": sorted(source.get("jurisdictions", [])),
                    "status": source.get("status", "disabled"),
                    "gap": (
                        "reuse_permission_required"
                        if source.get("status") == "permission_required"
                        else "source_disabled"
                    ),
                }
            )
    for item in coverage:
        if "source_currently_unavailable" in item["gaps"]:
            unavailable.append(
                {
                    "source_id": item["source_id"],
                    "jurisdictions": item["jurisdictions"],
                    "status": item["runtime_status"],
                    "gap": "source_currently_unavailable",
                }
            )
    return sorted(unavailable, key=lambda item: item["source_id"])


def _jurisdiction_coverage(
    sources: Sequence[Mapping[str, Any]],
    coverage: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    jurisdictions = sorted(
        {
            jurisdiction
            for source in sources
            for jurisdiction in source.get("jurisdictions", [])
            if isinstance(jurisdiction, str)
        }
    )
    rows = []
    for jurisdiction in jurisdictions:
        members = [item for item in coverage if jurisdiction in item["jurisdictions"]]
        enabled = [str(item["source_id"]) for item in members]
        risk = [str(item["source_id"]) for item in members if item["risk_capable"]]
        successful = [
            _parse_timestamp(item["last_successful_ingest"])
            for item in members
            if item["last_successful_ingest"]
        ]
        successful = [item for item in successful if item is not None]
        freshness_values = {str(item["freshness"]) for item in members}
        if not members or freshness_values == {"unavailable"}:
            freshness = "unavailable"
        elif len(freshness_values) == 1:
            freshness = next(iter(freshness_values))
        else:
            freshness = "mixed"
        gaps = []
        if not enabled:
            gaps.append("no_enabled_source")
        if not risk:
            gaps.append("no_risk_capable_source")
        if any("source_currently_unavailable" in item["gaps"] for item in members):
            gaps.append("source_currently_unavailable")
        if any(item["freshness"] == "stale" for item in members):
            gaps.append("source_stale")
        rows.append(
            {
                "jurisdiction": jurisdiction,
                "enabled_sources": sorted(enabled),
                "risk_capable_sources": sorted(risk),
                "last_successful_ingest": _timestamp(max(successful)) if successful else None,
                "freshness": freshness,
                "gaps": gaps,
            }
        )
    return rows


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
