from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from callersignal.cli import main as cli_main
from callersignal.lookup import LookupService
from callersignal.mcp_server import (
    call_lookup_tool,
    call_source_coverage_tool,
    serve_stdio,
    source_coverage_tool_definition,
    tool_definition,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 27, 9, 0, tzinfo=UTC)


def deterministic_service() -> LookupService:
    return LookupService(
        clock=lambda: NOW,
        lookup_id_factory=lambda: "lkp_mcp-integration",
    )


def test_tool_declares_origin_semantics_versioned_output_and_read_only_hints() -> None:
    tool = tool_definition()

    assert tool["name"] == "lookup_phone_number"
    assert tool["inputSchema"]["required"] == ["number"]
    assert tool["inputSchema"]["additionalProperties"] is False
    origin = tool["inputSchema"]["properties"]["origin_region"]
    assert "required for national-format input" in origin["description"]
    assert tool["outputSchema"]["properties"]["schema_version"]["const"] == "1.0.0"
    assert tool["annotations"] == {
        "readOnlyHint": True,
        "openWorldHint": False,
    }
    coverage = source_coverage_tool_definition()
    assert coverage["name"] == "get_source_coverage"
    assert coverage["inputSchema"]["additionalProperties"] is False
    assert coverage["annotations"] == tool["annotations"]


def test_stdio_coverage_tool_returns_the_committed_projection() -> None:
    result = call_source_coverage_tool({})
    committed = json.loads(
        (ROOT / "web/assets/transparency.json").read_text(encoding="utf-8")
    )

    assert result["isError"] is False
    assert result["structuredContent"] == committed
    assert json.loads(result["content"][0]["text"]) == committed
    assert call_source_coverage_tool({"number": "forbidden"})["isError"] is True


def test_structured_content_and_cli_json_are_the_same_shared_result(capsys) -> None:
    arguments = {"number": "202-555-0147", "origin_region": "US"}
    mcp_result = call_lookup_tool(arguments, lookup_service=deterministic_service())
    cli_main(
        ["lookup", arguments["number"], "--region", "US", "--json"],
        lookup_service=deterministic_service(),
    )
    cli_result = json.loads(capsys.readouterr().out)

    assert mcp_result["isError"] is False
    assert mcp_result["structuredContent"] == cli_result
    assert json.loads(mcp_result["content"][0]["text"]) == cli_result


def test_structured_content_validates_against_declared_output_schema() -> None:
    result = call_lookup_tool(
        {"number": "0906-8844", "origin_region": "NL"},
        lookup_service=deterministic_service(),
    )["structuredContent"]

    Draft202012Validator(
        tool_definition()["outputSchema"],
        format_checker=FormatChecker(),
    ).validate(result)


def test_missing_origin_region_is_a_tool_error_with_no_structured_result() -> None:
    result = call_lookup_tool(
        {"number": "0906-8844"},
        lookup_service=deterministic_service(),
    )

    assert result["isError"] is True
    assert "structuredContent" not in result
    assert "origin_region" in result["content"][0]["text"]


def test_non_object_jsonrpc_message_returns_invalid_request() -> None:
    output = StringIO()

    serve_stdio(input_stream=StringIO("[]\n"), output_stream=output)

    response = json.loads(output.getvalue())
    assert response["id"] is None
    assert response["error"] == {"code": -32600, "message": "Invalid Request"}


def test_stdio_lifecycle_lists_and_calls_the_tool() -> None:
    international = "+1" + "202" + "555" + "0147"
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1.0.0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "lookup_phone_number",
                "arguments": {"number": international},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "get_source_coverage", "arguments": {}},
        },
    ]
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    completed = subprocess.run(
        [sys.executable, "-m", "callersignal.mcp_server"],
        cwd=ROOT,
        env=environment,
        input="".join(json.dumps(item) + "\n" for item in requests),
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    responses = [json.loads(line) for line in completed.stdout.splitlines()]

    assert completed.stderr == ""
    assert [item["id"] for item in responses] == [1, 2, 3, 4]
    assert responses[0]["result"]["protocolVersion"] == "2025-11-25"
    assert responses[0]["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert [item["name"] for item in responses[1]["result"]["tools"]] == [
        "lookup_phone_number",
        "get_source_coverage",
    ]
    structured = responses[2]["result"]["structuredContent"]
    assert structured["phone_number"]["canonical"]["e164"] == international
    Draft202012Validator(
        responses[1]["result"]["tools"][0]["outputSchema"],
        format_checker=FormatChecker(),
    ).validate(structured)
    assert responses[3]["result"]["structuredContent"]["coverage"][
        "number_catalog"
    ]["imported_range_count"] == 74_984
    assert responses[3]["result"]["structuredContent"]["coverage"][
        "reputation_catalog"
    ]["indexed_observation_count"] == 258_137
