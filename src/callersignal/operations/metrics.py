"""Bounded-cardinality service and evidence-coverage metrics."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Set
from typing import Any


class MetricBoundaryError(ValueError):
    """A metric attempted to introduce unbounded or sensitive dimensions."""


class HealthMetrics:
    """Aggregate health only; the API has no phone-number or requester fields."""

    _OUTCOMES = {
        "success",
        "invalid_request",
        "rate_limited",
        "source_gap",
        "source_unavailable",
        "internal_error",
        "not_found",
    }
    _STATUSES = {200, 400, 404, 405, 429, 500, 503}

    def __init__(
        self,
        *,
        allowed_routes: Set[str],
        allowed_sources: Set[str],
    ) -> None:
        if not allowed_routes:
            raise ValueError("at least one route must be declared")
        self._routes = frozenset(allowed_routes)
        self._sources = frozenset(allowed_sources)
        self._requests: Counter[str] = Counter()
        self._latency: Counter[str] = Counter()
        self._gaps: Counter[str] = Counter()

    def record_request(
        self,
        *,
        route: str,
        outcome: str,
        http_status: int,
        duration_ms: int,
        jurisdiction: str,
        source_id: str | None = None,
        gap_code: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if route not in self._routes:
            raise MetricBoundaryError("route is not in the bounded registry")
        if outcome not in self._OUTCOMES:
            raise MetricBoundaryError("outcome is not in the bounded registry")
        if http_status not in self._STATUSES:
            raise MetricBoundaryError("http_status is not in the bounded registry")
        if duration_ms < 0 or duration_ms > 600_000:
            raise MetricBoundaryError("duration is outside the bounded range")
        if jurisdiction != "global" and re.fullmatch(r"[A-Z]{2}", jurisdiction) is None:
            raise MetricBoundaryError("jurisdiction must be ISO alpha-2 or global")
        if metadata:
            raise MetricBoundaryError("metadata is not accepted by privacy-safe metrics")
        if (source_id is None) != (gap_code is None):
            raise MetricBoundaryError("source_id and gap_code must be supplied together")
        if source_id is not None:
            if source_id not in self._sources:
                raise MetricBoundaryError("source_id is not in the bounded registry")
            if re.fullmatch(r"[a-z0-9]+(?:[_-][a-z0-9]+)*", str(gap_code)) is None:
                raise MetricBoundaryError("gap_code must be a bounded token")
            self._gaps[f"{jurisdiction}:{source_id}:{gap_code}"] += 1
        self._requests[f"{route}:{outcome}:{http_status}"] += 1
        self._latency[_duration_bucket(duration_ms)] += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "service_status": "degraded" if self._gaps else "ok",
            "request_totals": dict(sorted(self._requests.items())),
            "latency_buckets_ms": dict(sorted(self._latency.items())),
            "coverage_gaps": dict(sorted(self._gaps.items())),
            "privacy": {
                "raw_numbers": False,
                "requester_identifiers": False,
                "lookup_trails": False,
                "cardinality": "bounded_declared_dimensions",
            },
        }


def _duration_bucket(duration_ms: int) -> str:
    for boundary in (100, 250, 1_000):
        if duration_ms <= boundary:
            return f"le_{boundary}"
    return "gt_1000"
