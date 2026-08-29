"""Build honest public corpus metrics without lookup-demand or raw-report totals."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
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
_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PUBLIC_SNAPSHOT = _ROOT / "web/assets/transparency.json"
_ACM_STATUS = {
    "Toegekend": "assigned",
    "Afkoelen": "cooling_off",
    "Geblokkeerd": "blocked",
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
    acm_manifest: Mapping[str, Any] | None = None,
    caller_report_index: Mapping[str, Any] | None = None,
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
    number_catalog = _number_catalog_coverage(
        acm_manifest,
        sources=sources,
        generated_at=generated_at,
    )
    reputation_sources = _reputation_source_coverage(
        caller_report_index,
        sources=sources,
    )
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
            "number_catalog": number_catalog,
            "reputation_sources": reputation_sources,
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


def load_public_coverage_snapshot(
    path: Path = _DEFAULT_PUBLIC_SNAPSHOT,
) -> dict[str, Any]:
    """Load the committed privacy-safe projection shared by every public surface."""
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Public source coverage is unavailable") from error
    coverage = snapshot.get("coverage")
    if (
        snapshot.get("schema_version") != "1.0.0"
        or snapshot.get("kind") != "corpus_transparency"
        or not isinstance(coverage, Mapping)
        or not isinstance(coverage.get("number_catalog"), Mapping)
        or not isinstance(coverage.get("reputation_sources"), Mapping)
    ):
        raise ValueError("Public source coverage has an unsupported contract")
    return deepcopy(snapshot)


def _number_catalog_coverage(
    manifest: Mapping[str, Any] | None,
    *,
    sources: Sequence[Mapping[str, Any]],
    generated_at: datetime,
) -> dict[str, Any]:
    unavailable = {
        "source_id": "acm_number_register",
        "status": "unavailable",
        "imported_range_count": None,
        "matchable_range_count": None,
        "register_statuses": [],
        "destination_category_count": None,
        "source_sha256": None,
        "retrieved_at": None,
        "source_newest_mutation_at": None,
        "freshness": "unavailable",
        "gaps": ["catalog_manifest_unavailable"],
        "limitations": [
            "Catalogue counts describe official number ranges, not callers or call safety."
        ],
    }
    if not isinstance(manifest, Mapping):
        return unavailable
    source = manifest.get("source")
    artifact = manifest.get("artifact")
    expected = manifest.get("catalog_expectations")
    if not all(isinstance(item, Mapping) for item in (source, artifact, expected)):
        return unavailable
    if source.get("source_id") != "acm_number_register":
        return unavailable
    digest = artifact.get("sha256")
    retrieved_at = _parse_timestamp(artifact.get("retrieved_at"))
    row_count = expected.get("row_count")
    matchable_count = expected.get("matchable_row_count")
    destination_count = expected.get("destination_category_count")
    statuses = expected.get("status_counts")
    newest_mutation = _parse_acm_mutation(expected.get("newest_mutation"))
    if (
        not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        or retrieved_at is None
        or isinstance(row_count, bool)
        or not isinstance(row_count, int)
        or row_count <= 0
        or isinstance(matchable_count, bool)
        or not isinstance(matchable_count, int)
        or not 0 <= matchable_count <= row_count
        or isinstance(destination_count, bool)
        or not isinstance(destination_count, int)
        or destination_count <= 0
        or not isinstance(statuses, Mapping)
        or set(statuses) != set(_ACM_STATUS)
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in statuses.values()
        )
        or sum(statuses.values()) != row_count
        or newest_mutation is None
    ):
        return unavailable
    registry_source = next(
        (item for item in sources if item.get("source_id") == "acm_number_register"),
        {},
    )
    maximum_age = registry_source.get("intake", {}).get("freshness_max_age_seconds")
    freshness = (
        "current"
        if isinstance(maximum_age, int)
        and maximum_age > 0
        and (generated_at - retrieved_at).total_seconds() <= maximum_age
        else "stale"
    )
    gaps = [] if freshness == "current" else ["catalog_manifest_stale"]
    return {
        "source_id": "acm_number_register",
        "status": "available",
        "imported_range_count": row_count,
        "matchable_range_count": matchable_count,
        "register_statuses": [
            {
                "status": normalized,
                "source_status": native,
                "range_count": statuses[native],
            }
            for native, normalized in _ACM_STATUS.items()
        ],
        "destination_category_count": destination_count,
        "source_sha256": f"sha256:{digest}",
        "retrieved_at": _timestamp(retrieved_at),
        "source_newest_mutation_at": _timestamp(newest_mutation),
        "freshness": freshness,
        "gaps": gaps,
        "limitations": [
            "Counts describe official number ranges, not subscribers, callers, or providers.",
            "A catalogue match does not prove call origin, reputation, or safety.",
        ],
    }


def _reputation_source_coverage(
    service_index: Mapping[str, Any] | None,
    *,
    sources: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(service_index, Mapping):
        return {
            "index_reviewed_at": None,
            "indexed_service_count": 0,
            "licensable_service_count": 0,
            "enabled_source_count": 0,
            "unavailable_service_count": 0,
            "unavailable_reasons": [],
            "services": [],
            "gaps": ["caller_report_index_unavailable"],
            "notice": "Source coverage is unavailable and cannot support a safety claim.",
        }
    services = [
        item for item in service_index.get("services", ()) if isinstance(item, Mapping)
    ]
    registered = {
        str(item.get("source_id")): item
        for item in sources
        if isinstance(item.get("source_id"), str)
    }
    rows = []
    reason_counts: dict[str, int] = {}
    licensable = 0
    enabled = 0
    for service in services:
        service_id = str(service.get("service_id") or "")
        rights = service.get("rights", {})
        integration = service.get("integration", {})
        activation = service.get("activation", {})
        reuse_status = rights.get("reuse_status")
        if reuse_status in {"licensed_access_available", "enabled"}:
            licensable += 1
        registry_source = registered.get(service_id, {})
        is_enabled = (
            reuse_status in {"enabled", "public_domain"}
            and integration.get("status") == "enabled"
            and activation.get("decision") == "enabled"
            and not activation.get("blocking_gates")
            and _source_is_enabled(registry_source)
            and registry_source.get("risk_capable") is True
        )
        if is_enabled:
            status = "enabled"
            reason = "all_activation_gates_passed"
            enabled += 1
        elif reuse_status == "licensed_access_available":
            status = "unavailable"
            reason = "commercial_agreement_and_credentials_required"
        elif reuse_status == "permission_required":
            status = "unavailable"
            reason = "publisher_permission_required"
        elif reuse_status == "prohibited":
            status = "unavailable"
            reason = "reuse_prohibited"
        else:
            status = "unavailable"
            reason = "activation_requirements_incomplete"
        if status == "unavailable":
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        jurisdictions = service.get("jurisdictions", [])
        rows.append(
            {
                "service_id": service_id,
                "name": service.get("name", service_id),
                "jurisdictions": sorted(
                    item for item in jurisdictions if isinstance(item, str)
                ),
                "integration_channel": integration.get("channel", "none"),
                "status": status,
                "reason": reason,
                "blocking_gates": sorted(
                    item
                    for item in activation.get("blocking_gates", [])
                    if isinstance(item, str)
                ),
            }
        )
    rows.sort(key=lambda item: item["service_id"])
    return {
        "index_reviewed_at": service_index.get("reviewed_at"),
        "indexed_service_count": len(rows),
        "licensable_service_count": licensable,
        "enabled_source_count": enabled,
        "unavailable_service_count": len(rows) - enabled,
        "unavailable_reasons": [
            {"reason": reason, "service_count": count}
            for reason, count in sorted(reason_counts.items())
        ],
        "services": rows,
        "gaps": [] if rows else ["caller_report_index_empty"],
        "notice": (
            "Source counts describe coverage only; they are not trust, popularity, "
            "reputation, or safety scores."
        ),
    }


def _parse_acm_mutation(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


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
