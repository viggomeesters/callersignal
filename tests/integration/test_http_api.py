from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from callersignal.http_api import LookupMetric, create_app
from callersignal.lookup import LookupService

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 27, 9, 0, tzinfo=UTC)


def deterministic_service() -> LookupService:
    return LookupService(
        clock=lambda: NOW,
        lookup_id_factory=lambda: "lkp_http-integration",
    )


def lookup_validator() -> Draft202012Validator:
    schemas = {
        name: json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        for name in (
            "phone-number.schema.json",
            "source-evidence.schema.json",
            "lookup-result.schema.json",
        )
    }
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )
    return Draft202012Validator(
        schemas["lookup-result.schema.json"],
        registry=registry,
        format_checker=FormatChecker(),
    )


def request(app, *, method: str = "GET", path: str = "/v1/lookup", query=None):
    captured: dict = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(
        app(
            {
                "REQUEST_METHOD": method,
                "PATH_INFO": path,
                "QUERY_STRING": urlencode(query or {}),
            },
            start_response,
        )
    )
    return captured["status"], captured["headers"], json.loads(body or b"{}")


def test_lookup_response_uses_the_shared_result_and_schema() -> None:
    service = deterministic_service()
    app = create_app(lookup_service=service)

    status, headers, result = request(
        app,
        query={"number": "0906-8844", "origin_region": "NL"},
    )

    assert status == "200 OK"
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert headers["Cache-Control"] == "no-store"
    assert result == deterministic_service().lookup("0906-8844", origin_region="NL")
    lookup_validator().validate(result)


def test_international_lookup_does_not_require_an_origin_region() -> None:
    international = "+1" + "202" + "555" + "0147"

    status, _, result = request(
        create_app(lookup_service=deterministic_service()),
        query={"number": international},
    )

    assert status == "200 OK"
    assert result["phone_number"]["canonical"]["e164"] == international
    assert result["phone_number"]["origin_region"] is None
    lookup_validator().validate(result)


def test_national_input_without_origin_is_a_safe_versioned_error() -> None:
    status, _, result = request(
        create_app(lookup_service=deterministic_service()),
        query={"number": "0906-8844"},
    )

    assert status == "400 Bad Request"
    assert result == {
        "schema_version": "1.0.0",
        "kind": "http_error",
        "error": {
            "code": "origin_region_required",
            "message": "National phone-number input requires origin_region.",
        },
    }


def test_telemetry_is_minimal_and_cannot_change_the_lookup_response() -> None:
    class RecordingTelemetry:
        def __init__(self) -> None:
            self.events: list[LookupMetric] = []

        def record(self, event: LookupMetric) -> None:
            self.events.append(event)
            raise RuntimeError("telemetry is deliberately unavailable")

    telemetry = RecordingTelemetry()
    query = {"number": "0906-8844", "origin_region": "NL"}
    expected = request(create_app(lookup_service=deterministic_service()), query=query)

    actual = request(
        create_app(lookup_service=deterministic_service(), telemetry=telemetry),
        query=query,
    )

    assert actual == expected
    assert len(telemetry.events) == 1
    assert asdict(telemetry.events[0]) == {
        "schema_version": "1.0.0",
        "route": "lookup",
        "outcome": "success",
        "http_status": 200,
    }


def test_request_gate_can_rate_limit_without_receiving_lookup_data() -> None:
    gate_calls = 0

    def deny() -> bool:
        nonlocal gate_calls
        gate_calls += 1
        return False

    status, headers, result = request(
        create_app(lookup_service=deterministic_service(), request_gate=deny),
        query={"number": "0906-8844", "origin_region": "NL"},
    )

    assert gate_calls == 1
    assert status == "429 Too Many Requests"
    assert headers["Retry-After"] == "60"
    assert result["error"]["code"] == "rate_limited"


def test_health_method_and_unknown_query_boundaries_are_explicit() -> None:
    app = create_app(lookup_service=deterministic_service())

    health_status, _, health = request(app, path="/healthz")
    method_status, method_headers, method_error = request(app, method="POST")
    query_status, _, query_error = request(
        app,
        query={"number": "0906-8844", "origin_region": "NL", "extra": "no"},
    )

    assert health_status == "200 OK"
    assert health == {
        "schema_version": "1.0.0",
        "service": "callersignal",
        "status": "ok",
    }
    assert method_status == "405 Method Not Allowed"
    assert method_headers["Allow"] == "GET"
    assert method_error["error"]["code"] == "method_not_allowed"
    assert query_status == "400 Bad Request"
    assert query_error["error"]["code"] == "invalid_query"
