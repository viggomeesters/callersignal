"""Framework-independent, read-only WSGI adapter for CallerSignal lookups."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import parse_qs

from callersignal.lookup import LookupService
from callersignal.numbering import OriginRegionRequiredError

StartResponse = Callable[[str, list[tuple[str, str]]], Any]
RequestGate = Callable[[], bool]
_REGION = re.compile(r"^[A-Z]{2}$")
_CAMPAIGN_ID = re.compile(r"^cmp_[A-Za-z0-9_-]{8,64}$")
_STATUS_TEXT = {
    200: "200 OK",
    400: "400 Bad Request",
    404: "404 Not Found",
    405: "405 Method Not Allowed",
    429: "429 Too Many Requests",
    500: "500 Internal Server Error",
    503: "503 Service Unavailable",
}


@dataclass(frozen=True, slots=True)
class LookupMetric:
    """Minimal aggregate event; deliberately excludes request and result data."""

    schema_version: str
    route: str
    outcome: str
    http_status: int


class TelemetrySink(Protocol):
    """Optional destination for non-identifying HTTP outcome metrics."""

    def record(self, event: LookupMetric) -> None:
        """Record an aggregate event without receiving lookup data."""


@dataclass(frozen=True, slots=True)
class _Response:
    status: int
    body: bytes
    headers: tuple[tuple[str, str], ...] = ()


class LookupHTTPApplication:
    """WSGI application that delegates all product logic to LookupService."""

    def __init__(
        self,
        *,
        lookup_service: LookupService,
        telemetry: TelemetrySink | None,
        request_gate: RequestGate,
        public_campaigns: Iterable[Mapping[str, Any]],
    ) -> None:
        self._lookup_service = lookup_service
        self._telemetry = telemetry
        self._request_gate = request_gate
        self._public_campaigns = _project_public_campaigns(public_campaigns)

    def __call__(
        self,
        environ: Mapping[str, Any],
        start_response: StartResponse,
    ) -> Iterable[bytes]:
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        if path == "/healthz":
            if method != "GET":
                return self._send(
                    start_response,
                    _error_response(
                        405,
                        "method_not_allowed",
                        "Only GET is supported.",
                        headers=(("Allow", "GET"),),
                    ),
                )
            return self._send(
                start_response,
                _json_response(
                    200,
                    {
                        "schema_version": "1.0.0",
                        "service": "callersignal",
                        "status": "ok",
                    },
                ),
            )
        if path == "/v1/campaigns" or path.startswith("/v1/campaigns/"):
            return self._campaign_response(method, path, start_response)
        if path != "/v1/lookup":
            return self._send(
                start_response,
                _error_response(404, "not_found", "The requested route does not exist."),
            )
        if method != "GET":
            return self._finish_lookup(
                start_response,
                _error_response(
                    405,
                    "method_not_allowed",
                    "Only GET is supported.",
                    headers=(("Allow", "GET"),),
                ),
                "method_not_allowed",
            )
        try:
            allowed = self._request_gate()
        except Exception:
            return self._finish_lookup(
                start_response,
                _error_response(503, "gate_unavailable", "Request admission is unavailable."),
                "gate_unavailable",
            )
        if not allowed:
            return self._finish_lookup(
                start_response,
                _error_response(
                    429,
                    "rate_limited",
                    "Too many lookup requests; retry later.",
                    headers=(("Retry-After", "60"),),
                ),
                "rate_limited",
            )

        parsed = _parse_lookup_query(str(environ.get("QUERY_STRING", "")))
        if isinstance(parsed, _Response):
            return self._finish_lookup(start_response, parsed, "invalid_request")
        number, origin_region = parsed
        try:
            result = self._lookup_service.lookup(number, origin_region=origin_region)
        except OriginRegionRequiredError:
            return self._finish_lookup(
                start_response,
                _error_response(
                    400,
                    "origin_region_required",
                    "National phone-number input requires origin_region.",
                ),
                "invalid_request",
            )
        except Exception:
            return self._finish_lookup(
                start_response,
                _error_response(500, "internal_error", "The lookup could not be completed."),
                "internal_error",
            )
        return self._finish_lookup(
            start_response,
            _json_response(200, result),
            "success",
        )

    def _campaign_response(
        self,
        method: str,
        path: str,
        start_response: StartResponse,
    ) -> Iterable[bytes]:
        if method != "GET":
            return self._send(
                start_response,
                _error_response(
                    405,
                    "method_not_allowed",
                    "Only GET is supported.",
                    headers=(("Allow", "GET"),),
                ),
            )
        if path == "/v1/campaigns":
            summaries = [_campaign_summary(record) for record in self._public_campaigns]
            as_of_values = [
                str(item["timeline"]["updated_at"])
                for item in summaries
                if item["timeline"].get("updated_at")
            ]
            return self._send(
                start_response,
                _json_response(
                    200,
                    {
                        "schema_version": "1.0.0",
                        "kind": "public_campaign_catalogue",
                        "as_of": max(as_of_values, default=None),
                        "campaigns": summaries,
                        "notice": (
                            "Only rights-approved aggregate campaigns are published; "
                            "an empty list means no campaign currently meets that bar."
                        ),
                    },
                ),
            )
        campaign_id = path.removeprefix("/v1/campaigns/")
        if not _CAMPAIGN_ID.fullmatch(campaign_id):
            return self._send(
                start_response,
                _error_response(
                    404,
                    "campaign_not_found",
                    "No eligible public campaign matches this identifier.",
                ),
            )
        for record in self._public_campaigns:
            if record["campaign"]["campaign_id"] == campaign_id:
                return self._send(start_response, _json_response(200, record))
        return self._send(
            start_response,
            _error_response(
                404,
                "campaign_not_found",
                "No eligible public campaign matches this identifier.",
            ),
        )

    def _finish_lookup(
        self,
        start_response: StartResponse,
        response: _Response,
        outcome: str,
    ) -> Iterable[bytes]:
        body = self._send(start_response, response)
        if self._telemetry is not None:
            event = LookupMetric(
                schema_version="1.0.0",
                route="lookup",
                outcome=outcome,
                http_status=response.status,
            )
            try:
                self._telemetry.record(event)
            except Exception:
                pass
        return body

    @staticmethod
    def _send(start_response: StartResponse, response: _Response) -> Iterable[bytes]:
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(response.body))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
            *response.headers,
        ]
        start_response(_STATUS_TEXT[response.status], headers)
        return [response.body]


def create_app(
    *,
    lookup_service: LookupService | None = None,
    telemetry: TelemetrySink | None = None,
    request_gate: RequestGate | None = None,
    public_campaigns: Iterable[Mapping[str, Any]] = (),
) -> LookupHTTPApplication:
    """Create the WSGI app with optional privacy-safe operational ports."""
    return LookupHTTPApplication(
        lookup_service=lookup_service or LookupService(),
        telemetry=telemetry,
        request_gate=request_gate or (lambda: True),
        public_campaigns=public_campaigns,
    )


_CAMPAIGN_FIELDS = (
    "schema_version",
    "kind",
    "campaign_id",
    "title",
    "status",
    "risk_state",
    "subject_semantics",
    "categories",
    "jurisdictions",
    "membership",
    "timeline",
    "evidence",
    "confidence",
    "freshness",
    "recommended_actions",
    "correction",
    "limitations",
)
_ORGANIZATION_FIELDS = (
    "display_name",
    "verification_status",
    "declaration_scope",
    "official_contact_url",
)
_COVERAGE_FIELDS = ("source_id", "status", "checked_at", "jurisdiction", "scope")


def _project_public_campaigns(
    records: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Fail closed and copy only explicitly public campaign fields."""
    projected: list[dict[str, Any]] = []
    for record in records:
        campaign_value = record.get("campaign")
        if not isinstance(campaign_value, Mapping):
            continue
        campaign = {
            field: deepcopy(campaign_value[field])
            for field in _CAMPAIGN_FIELDS
            if field in campaign_value
        }
        if not _campaign_is_publishable(campaign):
            continue
        evidence = campaign["evidence"]
        expected_sources = set(evidence["source_ids"])
        coverage_value = record.get("source_coverage", ())
        coverage = []
        if isinstance(coverage_value, Iterable) and not isinstance(
            coverage_value, (str, bytes, Mapping)
        ):
            for item in coverage_value:
                if not isinstance(item, Mapping):
                    continue
                public_item = {
                    field: deepcopy(item[field])
                    for field in _COVERAGE_FIELDS
                    if field in item
                }
                if (
                    {"source_id", "status", "checked_at"} <= public_item.keys()
                    and isinstance(public_item["source_id"], str)
                    and public_item["source_id"] in expected_sources
                ):
                    coverage.append(public_item)
        if {item["source_id"] for item in coverage} != expected_sources:
            continue
        organization = None
        organization_value = record.get("verified_organization")
        if (
            isinstance(organization_value, Mapping)
            and organization_value.get("verification_status") == "verified"
        ):
            organization = {
                field: deepcopy(organization_value[field])
                for field in _ORGANIZATION_FIELDS
                if field in organization_value
            }
        projected.append(
            {
                "schema_version": "1.0.0",
                "kind": "public_campaign",
                "campaign": campaign,
                "verified_organization": organization,
                "source_coverage": sorted(coverage, key=lambda item: item["source_id"]),
            }
        )
    return tuple(
        sorted(projected, key=lambda item: item["campaign"]["campaign_id"])
    )


def _campaign_is_publishable(campaign: Mapping[str, Any]) -> bool:
    required = set(_CAMPAIGN_FIELDS)
    if set(campaign) != required:
        return False
    if not _CAMPAIGN_ID.fullmatch(str(campaign.get("campaign_id", ""))):
        return False
    if campaign.get("status") not in {"active", "resolved", "retracted"}:
        return False
    evidence = campaign.get("evidence")
    if not isinstance(evidence, Mapping):
        return False
    source_ids = evidence.get("source_ids")
    evidence_ids = evidence.get("eligible_evidence_ids")
    diversity = evidence.get("source_diversity")
    if not isinstance(source_ids, list) or not isinstance(evidence_ids, list):
        return False
    if any(not isinstance(source_id, str) for source_id in source_ids):
        return False
    if any(not isinstance(evidence_id, str) for evidence_id in evidence_ids):
        return False
    if not isinstance(diversity, int) or diversity != len(set(source_ids)):
        return False
    correction = campaign.get("correction")
    if not isinstance(correction, Mapping) or correction.get("status") == "under_review":
        return False
    if campaign.get("risk_state") == "official_warning":
        return diversity >= 1 and len(evidence_ids) >= 1
    return (
        campaign.get("risk_state") == "elevated_signals"
        and diversity >= 2
        and len(evidence_ids) >= 2
    )


def _campaign_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    campaign = record["campaign"]
    organization = record["verified_organization"]
    return {
        "campaign_id": campaign["campaign_id"],
        "title": campaign["title"],
        "status": campaign["status"],
        "risk_state": campaign["risk_state"],
        "categories": campaign["categories"],
        "jurisdictions": campaign["jurisdictions"],
        "membership": campaign["membership"],
        "timeline": campaign["timeline"],
        "freshness": campaign["freshness"],
        "correction": campaign["correction"],
        "source_diversity": campaign["evidence"]["source_diversity"],
        "verified_organization": organization,
    }


def _parse_lookup_query(query_string: str) -> tuple[str, str | None] | _Response:
    if len(query_string) > 512:
        return _error_response(400, "invalid_query", "The query string is too long.")
    try:
        query = parse_qs(
            query_string,
            keep_blank_values=True,
            strict_parsing=False,
            max_num_fields=3,
        )
    except ValueError:
        return _error_response(400, "invalid_query", "The query string is invalid.")
    if set(query) - {"number", "origin_region"}:
        return _error_response(400, "invalid_query", "Only number and origin_region are accepted.")
    numbers = query.get("number", [])
    origins = query.get("origin_region", [])
    if len(numbers) != 1 or not 1 <= len(numbers[0]) <= 64:
        return _error_response(
            400,
            "invalid_query",
            "number must occur once and contain one to 64 characters.",
        )
    if len(origins) > 1:
        return _error_response(400, "invalid_query", "origin_region may occur at most once.")
    origin_region = origins[0] if origins else None
    if origin_region is not None and not _REGION.fullmatch(origin_region):
        return _error_response(
            400,
            "invalid_query",
            "origin_region must be an uppercase ISO alpha-2 code.",
        )
    return numbers[0], origin_region


def _json_response(
    status: int,
    payload: Mapping[str, Any],
    *,
    headers: tuple[tuple[str, str], ...] = (),
) -> _Response:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return _Response(status=status, body=body, headers=headers)


def _error_response(
    status: int,
    code: str,
    message: str,
    *,
    headers: tuple[tuple[str, str], ...] = (),
) -> _Response:
    return _json_response(
        status,
        {
            "schema_version": "1.0.0",
            "kind": "http_error",
            "error": {"code": code, "message": message},
        },
        headers=headers,
    )


application = create_app()
