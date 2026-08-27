"""Framework-independent, read-only WSGI adapter for CallerSignal lookups."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import parse_qs

from callersignal.lookup import LookupService
from callersignal.numbering import OriginRegionRequiredError

StartResponse = Callable[[str, list[tuple[str, str]]], Any]
RequestGate = Callable[[], bool]
_REGION = re.compile(r"^[A-Z]{2}$")
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
    ) -> None:
        self._lookup_service = lookup_service
        self._telemetry = telemetry
        self._request_gate = request_gate

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
) -> LookupHTTPApplication:
    """Create the WSGI app with optional privacy-safe operational ports."""
    return LookupHTTPApplication(
        lookup_service=lookup_service or LookupService(),
        telemetry=telemetry,
        request_gate=request_gate or (lambda: True),
    )


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
