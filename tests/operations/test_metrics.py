from __future__ import annotations

import json

import pytest

from callersignal.operations import HealthMetrics, MetricBoundaryError


def test_metrics_expose_health_and_coverage_gaps_without_personal_trails() -> None:
    metrics = HealthMetrics(
        allowed_routes={"lookup", "campaigns", "mcp"},
        allowed_sources={"nanpa", "acm_numbering"},
    )

    metrics.record_request(
        route="lookup",
        outcome="success",
        http_status=200,
        duration_ms=42,
        jurisdiction="US",
    )
    metrics.record_request(
        route="lookup",
        outcome="source_gap",
        http_status=200,
        duration_ms=180,
        jurisdiction="US",
        source_id="nanpa",
        gap_code="source_stale",
    )

    snapshot = metrics.snapshot()
    assert snapshot["request_totals"] == {"lookup:source_gap:200": 1, "lookup:success:200": 1}
    assert snapshot["latency_buckets_ms"] == {"le_100": 1, "le_250": 1}
    assert snapshot["coverage_gaps"] == {"US:nanpa:source_stale": 1}
    serialized = json.dumps(snapshot).lower()
    assert "phone" not in serialized
    assert "request_id" not in serialized
    assert "lookup_history" not in serialized
    assert "unique" not in serialized


def test_metric_dimensions_are_bounded_and_reject_sensitive_metadata() -> None:
    metrics = HealthMetrics(
        allowed_routes={"lookup"},
        allowed_sources={"nanpa"},
    )

    with pytest.raises(MetricBoundaryError, match="route"):
        metrics.record_request(
            route="dynamic-number-route",
            outcome="success",
            http_status=200,
            duration_ms=1,
            jurisdiction="US",
        )
    with pytest.raises(MetricBoundaryError, match="metadata"):
        metrics.record_request(
            route="lookup",
            outcome="success",
            http_status=200,
            duration_ms=1,
            jurisdiction="US",
            metadata={"requester_ip": "192.0.2.1"},
        )
