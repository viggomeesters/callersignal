"""Dependency-free MCP stdio server for the read-only lookup tool."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO

from callersignal.lookup import LookupService
from callersignal.numbering import OriginRegionRequiredError
from callersignal.transparency import load_public_coverage_snapshot

PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = {PROTOCOL_VERSION, "2025-06-18"}
_ROOT = Path(__file__).resolve().parents[2]
_REGION = re.compile(r"^[A-Z]{2}$")


def tool_definition() -> dict[str, Any]:
    """Return the complete MCP contract advertised during tools/list."""
    return {
        "name": "lookup_phone_number",
        "title": "Look up public phone-number evidence",
        "description": (
            "Read-only international phone-number lookup. Before calling, tell the user which "
            "origin country is being checked. National-format input requires origin_region; "
            "+prefixed international input determines its country independently. Returns public "
            "source observations, explicit gaps, confidence, and spoofing-aware residual risk; "
            "it never proves caller identity or safety."
        ),
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["number"],
            "properties": {
                "number": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 64,
                    "description": "National-format or +prefixed international phone number.",
                },
                "origin_region": {
                    "oneOf": [
                        {"type": "string", "pattern": "^[A-Z]{2}$"},
                        {"type": "null"},
                    ],
                    "default": None,
                    "description": (
                        "Uppercase ISO alpha-2 origin region; required for national-format input "
                        "and omitted for +prefixed international input."
                    ),
                },
            },
        },
        "outputSchema": _bundled_output_schema(),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    }


def source_coverage_tool_definition() -> dict[str, Any]:
    """Return the read-only cross-surface source coverage contract."""
    return {
        "name": "get_source_coverage",
        "title": "Get public source coverage",
        "description": (
            "Return the same public coverage projection as HTTP, CLI, hosted MCP, and the "
            "website: official ACM catalogue counts and freshness plus indexed, advertised "
            "licensing, enabled, and unavailable reputation-source counts. Source volume is "
            "not a trust or safety score."
        ),
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
        "outputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    }


def call_lookup_tool(
    arguments: Mapping[str, Any],
    *,
    lookup_service: LookupService | None = None,
) -> dict[str, Any]:
    """Validate one tool call and return MCP content plus structuredContent."""
    unexpected = set(arguments) - {"number", "origin_region"}
    if unexpected:
        return _tool_error("Only number and origin_region are accepted.")
    number = arguments.get("number")
    origin_region = arguments.get("origin_region")
    if not isinstance(number, str) or not 1 <= len(number) <= 64:
        return _tool_error("number must be a non-empty string of at most 64 characters.")
    if origin_region is not None and (
        not isinstance(origin_region, str) or not _REGION.fullmatch(origin_region)
    ):
        return _tool_error("origin_region must be an uppercase ISO alpha-2 code or null.")
    if not number.strip().startswith("+") and origin_region is None:
        return _tool_error("origin_region is required for national-format input.")

    service = lookup_service or LookupService()
    try:
        result = service.lookup(number, origin_region=origin_region)
    except OriginRegionRequiredError:
        return _tool_error("origin_region is required for national-format input.")
    serialized = json.dumps(result, sort_keys=True, ensure_ascii=False)
    return {
        "content": [{"type": "text", "text": serialized}],
        "structuredContent": result,
        "isError": False,
    }


def call_source_coverage_tool(
    arguments: Mapping[str, Any],
    *,
    source_coverage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the committed public projection without accepting lookup data."""
    if arguments:
        return _tool_error("Source coverage accepts no arguments.")
    snapshot = (
        dict(source_coverage)
        if source_coverage is not None
        else load_public_coverage_snapshot()
    )
    serialized = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
    return {
        "content": [{"type": "text", "text": serialized}],
        "structuredContent": snapshot,
        "isError": False,
    }


def handle_request(
    message: Mapping[str, Any],
    *,
    lookup_service: LookupService | None = None,
    source_coverage: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Handle one valid JSON-RPC request or notification."""
    if "id" not in message:
        return None
    request_id = message["id"]
    method = message.get("method")
    if method == "initialize":
        params = message.get("params", {})
        requested = params.get("protocolVersion") if isinstance(params, Mapping) else None
        protocol_version = (
            requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
        )
        return _success(
            request_id,
            {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "callersignal",
                    "title": "CallerSignal",
                    "version": "0.3.0",
                    "description": "Evidence-backed read-only phone-number context.",
                    "websiteUrl": "https://github.com/viggomeesters/callersignal",
                },
                "instructions": (
                    "State the interpreted origin country before each lookup and preserve "
                    "unknowns, source limits, and spoofing risk in the answer."
                ),
            },
        )
    if method == "ping":
        return _success(request_id, {})
    if method == "tools/list":
        return _success(
            request_id,
            {"tools": [tool_definition(), source_coverage_tool_definition()]},
        )
    if method == "tools/call":
        params = message.get("params", {})
        if not isinstance(params, Mapping):
            return _success(request_id, _tool_error("Tool parameters must be an object."))
        tool_name = params.get("name")
        if tool_name not in {"lookup_phone_number", "get_source_coverage"}:
            return _success(request_id, _tool_error("Unknown tool name."))
        arguments = params.get("arguments", {})
        if not isinstance(arguments, Mapping):
            return _success(request_id, _tool_error("Tool arguments must be an object."))
        if tool_name == "get_source_coverage":
            return _success(
                request_id,
                call_source_coverage_tool(
                    arguments,
                    source_coverage=source_coverage,
                ),
            )
        return _success(request_id, call_lookup_tool(arguments, lookup_service=lookup_service))
    return _error(request_id, -32601, "Method not found")


def serve_stdio(
    *,
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
    lookup_service: LookupService | None = None,
    source_coverage: Mapping[str, Any] | None = None,
) -> None:
    """Serve newline-delimited MCP JSON-RPC messages until stdin closes."""
    initialized = False
    ready = False
    for line in input_stream:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            _write(output_stream, _error(None, -32700, "Parse error"))
            continue
        if not isinstance(message, Mapping):
            _write(output_stream, _error(None, -32600, "Invalid Request"))
            continue
        if message.get("jsonrpc") != "2.0":
            _write(output_stream, _error(message.get("id"), -32600, "Invalid Request"))
            continue
        method = message.get("method")
        if method == "initialize":
            if initialized:
                _write(output_stream, _error(message.get("id"), -32600, "Already initialized"))
                continue
            initialized = True
        elif method == "notifications/initialized":
            if initialized:
                ready = True
            continue
        elif method not in {"ping"} and not ready:
            if "id" in message:
                _write(output_stream, _error(message["id"], -32002, "Server not initialized"))
            continue
        response = handle_request(
            message,
            lookup_service=lookup_service,
            source_coverage=source_coverage,
        )
        if response is not None:
            _write(output_stream, response)


def main() -> int:
    """Run the MCP stdio transport."""
    serve_stdio()
    return 0


def _bundled_output_schema() -> dict[str, Any]:
    lookup = _load_schema("lookup-result.schema.json")
    lookup.setdefault("$defs", {})["phone_number"] = _load_schema(
        "phone-number.schema.json"
    )
    lookup["$defs"]["source_evidence"] = _load_schema("source-evidence.schema.json")
    return _replace_external_refs(lookup)


def _load_schema(name: str) -> dict[str, Any]:
    return json.loads((_ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _replace_external_refs(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _replace_external_refs(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_external_refs(item) for item in value]
    if value == "phone-number.schema.json":
        return "#/$defs/phone_number"
    if value == "source-evidence.schema.json":
        return "#/$defs/source_evidence"
    return value


def _tool_error(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }


def _success(request_id: Any, result: Mapping[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": dict(result)}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _write(output_stream: TextIO, message: Mapping[str, Any]) -> None:
    output_stream.write(json.dumps(message, separators=(",", ":"), ensure_ascii=False) + "\n")
    output_stream.flush()


if __name__ == "__main__":
    raise SystemExit(main())
