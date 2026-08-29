from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from callersignal.transparency import build_transparency_snapshot

ROOT = Path(__file__).resolve().parents[2]
GENERATED_AT = datetime(2026, 8, 29, 8, 30, tzinfo=UTC)


def source(
    source_id: str,
    jurisdiction: str,
    *,
    enabled: bool = True,
    risk_capable: bool = False,
) -> dict:
    gate_status = "passed" if enabled else "required"
    return {
        "source_id": source_id,
        "name": source_id.replace("_", " ").title(),
        "status": "enabled" if enabled else "permission_required",
        "adapter_enabled": enabled,
        "jurisdictions": [jurisdiction],
        "risk_capable": risk_capable if enabled else False,
        "intake": {"freshness_max_age_seconds": 86_400 if enabled else None},
        "gates": {
            name: {"status": gate_status}
            for name in (
                "robots_access",
                "reuse_permission",
                "copyright",
                "database_rights",
                "privacy",
                "takedown",
                "provenance",
            )
        },
    }


def campaign(
    campaign_id: str,
    source_ids: list[str],
    *,
    status: str = "active",
    risk_state: str = "elevated_signals",
    correction: str = "none",
) -> dict:
    return {
        "campaign_id": campaign_id,
        "status": status,
        "risk_state": risk_state,
        "evidence": {
            "source_ids": source_ids,
            "eligible_evidence_ids": [
                f"ev_{campaign_id}_{index}" for index, _ in enumerate(source_ids)
            ],
            "source_diversity": len(set(source_ids)),
        },
        "correction": {"status": correction},
    }


def portfolio(organization_id: str, *, status: str = "verified") -> dict:
    return {
        "organization_id": organization_id,
        "status": status,
        "verification": {"valid_until": "2026-09-29T08:30:00Z"},
        "correction": {"status": "none"},
    }


def test_snapshot_counts_only_enabled_eligible_and_thresholded_records() -> None:
    registry = {
        "reviewed_at": "2026-08-29",
        "sources": [
            source("risk_alpha", "NL", risk_capable=True),
            source("risk_beta", "NL", risk_capable=True),
            source("blocked_reports", "NL", enabled=False, risk_capable=True),
        ],
    }
    snapshot = build_transparency_snapshot(
        source_registry=registry,
        ingest_status={
            "risk_alpha": {
                "status": "success",
                "last_successful_ingest": "2026-08-29T08:00:00Z",
            },
            "risk_beta": {
                "status": "success",
                "last_successful_ingest": "2026-08-29T08:05:00Z",
            },
        },
        campaigns=[
            campaign("cmp_eligible_one", ["risk_alpha", "risk_beta"], correction="corrected"),
            campaign("cmp_monitoring_one", ["risk_alpha", "risk_beta"], status="monitoring"),
            campaign("cmp_blocked_source", ["risk_alpha", "blocked_reports"]),
        ],
        verified_portfolios=[
            portfolio("org_eligible"),
            portfolio("org_suspended", status="suspended"),
        ],
        community_aggregates=[
            {
                "source_id": "risk_alpha",
                "publication_status": "public",
                "verification_status": "verified",
                "privacy": {"threshold_met": True, "cohort_size": 5},
            },
            {
                "source_id": "blocked_reports",
                "publication_status": "public",
                "verification_status": "verified",
                "privacy": {"threshold_met": True, "cohort_size": 99},
            },
            {
                "source_id": "risk_alpha",
                "publication_status": "public",
                "verification_status": "verified",
                "privacy": {"threshold_met": False, "cohort_size": 4},
            },
        ],
        moderation={
            "status": "approved",
            "public_aggregate_minimum": 5,
            "independent_observer_minimum": 2,
        },
        methodology_version="1.0.0",
        generated_at=GENERATED_AT,
    )

    assert snapshot["corpus"] == {
        "eligible_campaigns": 1,
        "verified_organization_portfolios": 1,
        "privacy_thresholded_aggregates": 1,
        "corrections": {"campaigns": 1, "organization_portfolios": 0},
    }
    assert snapshot["coverage"]["enabled_source_count"] == 2
    assert snapshot["coverage"]["risk_capable_source_count"] == 2
    assert snapshot["coverage"]["jurisdictions"][0]["jurisdiction"] == "NL"
    serialized = json.dumps(snapshot)
    assert "lookup_count" not in serialized
    assert "lookup_volume" not in serialized
    assert "raw_report_count" not in serialized
    assert "raw_reports" in snapshot["interpretation"]["excluded_public_totals"]


def test_coverage_names_freshness_ingest_and_unavailable_gaps() -> None:
    registry = {
        "reviewed_at": "2026-08-29",
        "sources": [
            source("current_numbering", "GB"),
            source("stale_risk", "GB", risk_capable=True),
            source("unavailable_risk", "US", risk_capable=True),
            source("permission_gap", "NL", enabled=False),
        ],
    }
    snapshot = build_transparency_snapshot(
        source_registry=registry,
        ingest_status={
            "current_numbering": {
                "status": "success",
                "last_successful_ingest": "2026-08-29T08:00:00Z",
            },
            "stale_risk": {
                "status": "success",
                "last_successful_ingest": "2026-08-20T08:00:00Z",
            },
            "unavailable_risk": {"status": "unavailable", "last_successful_ingest": None},
        },
        campaigns=[],
        verified_portfolios=[],
        community_aggregates=[],
        moderation={"status": "not_approved", "public_aggregate_minimum": None},
        methodology_version="1.0.0",
        generated_at=GENERATED_AT,
    )

    by_source = {item["source_id"]: item for item in snapshot["coverage"]["sources"]}
    assert by_source["current_numbering"]["freshness"] == "current"
    assert by_source["stale_risk"]["freshness"] == "stale"
    assert by_source["unavailable_risk"]["freshness"] == "unavailable"
    assert by_source["unavailable_risk"]["gaps"] == [
        "last_successful_ingest_unavailable",
        "source_currently_unavailable",
    ]
    gaps = snapshot["coverage"]["unavailable_sources"]
    assert {item["source_id"] for item in gaps} == {
        "permission_gap",
        "unavailable_risk",
    }
    assert snapshot["moderation"]["public_aggregate_minimum"] is None
    assert snapshot["moderation"]["status"] == "not_approved"


def test_committed_public_snapshot_is_a_reproducible_zero_honest_projection() -> None:
    committed = json.loads(
        (ROOT / "web/assets/transparency.json").read_text(encoding="utf-8")
    )
    registry = json.loads((ROOT / "sources/registry.json").read_text(encoding="utf-8"))
    ingest_status = {}
    for fixture_path in sorted((ROOT / "fixtures").glob("*/*.json")):
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        ingest_status[fixture["source"]["source_id"]] = {
            "status": "success",
            "last_successful_ingest": fixture["source"]["retrieved_at"],
        }

    rebuilt = build_transparency_snapshot(
        source_registry=registry,
        ingest_status=ingest_status,
        campaigns=[],
        verified_portfolios=[],
        community_aggregates=[],
        moderation={
            "status": "not_approved",
            "public_aggregate_minimum": None,
            "independent_observer_minimum": 2,
        },
        methodology_version="1.0.0",
        generated_at=datetime.fromisoformat(committed["generated_at"].replace("Z", "+00:00")),
    )

    assert committed == rebuilt
    assert committed["coverage"]["risk_capable_source_count"] == 0
    assert committed["corpus"]["eligible_campaigns"] == 0
    assert committed["interpretation"]["no_matching_evidence"].startswith(
        "No matching evidence"
    )
