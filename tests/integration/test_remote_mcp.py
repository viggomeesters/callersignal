from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode

from callersignal.http_api import create_app as create_http_app
from callersignal.lookup import LookupService
from callersignal.remote_mcp import (
    CURRENT_PROTOCOL_VERSION,
    LEGACY_PROTOCOL_VERSION,
    PROTECTED_RESOURCE_PATH,
    create_app,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)
RESERVED = "+1" + "202" + "555" + "0147"


def deterministic_service() -> LookupService:
    return LookupService(
        clock=lambda: NOW,
        lookup_id_factory=lambda: "lkp_remote-mcp-test",
    )


def rpc(identifier: int, method: str, params: dict | None = None) -> dict:
    message = {"jsonrpc": "2.0", "id": identifier, "method": method}
    if params is not None:
        message["params"] = params
    return message


def wsgi_request(
    app,
    *,
    method: str = "POST",
    path: str = "/mcp",
    message: dict | None = None,
    headers: dict[str, str] | None = None,
    query: str = "",
) -> tuple[str, dict[str, str], dict | None]:
    raw = json.dumps(message).encode("utf-8") if message is not None else b""
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": str(len(raw)),
        "wsgi.input": BytesIO(raw),
        "HTTP_ACCEPT": "application/json, text/event-stream",
        "HTTP_HOST": "callersignal.vercel.app",
        "wsgi.url_scheme": "https",
    }
    for name, value in (headers or {}).items():
        environ[f"HTTP_{name.upper().replace('-', '_')}"] = value
    captured: dict = {}

    def start_response(status, response_headers):
        captured["status"] = status
        captured["headers"] = dict(response_headers)

    body = b"".join(app(environ, start_response))
    payload = json.loads(body) if body else None
    return captured["status"], captured["headers"], payload


def test_stateless_discovery_and_legacy_initialization_are_supported() -> None:
    app = create_app(lookup_service=deterministic_service())

    status, headers, discovered = wsgi_request(
        app,
        message=rpc(1, "server/discover", {"_meta": {}}),
        headers={"MCP-Protocol-Version": CURRENT_PROTOCOL_VERSION},
    )
    init_status, init_headers, initialized = wsgi_request(
        app,
        message=rpc(
            2,
            "initialize",
            {
                "protocolVersion": LEGACY_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1.0.0"},
            },
        ),
    )

    assert status == "200 OK"
    assert headers["Cache-Control"] == "no-store"
    assert discovered["result"]["supportedVersions"] == [
        CURRENT_PROTOCOL_VERSION,
        LEGACY_PROTOCOL_VERSION,
        "2025-06-18",
    ]
    assert discovered["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert discovered["result"]["serverInfo"]["name"] == "callersignal"
    assert init_status == "200 OK"
    assert init_headers["Cache-Control"] == "no-store"
    assert initialized["result"]["protocolVersion"] == LEGACY_PROTOCOL_VERSION


def test_tool_listing_distinguishes_public_reads_from_locked_protected_writes() -> None:
    app = create_app(lookup_service=deterministic_service())
    status, _, response = wsgi_request(app, message=rpc(3, "tools/list", {}))

    assert status == "200 OK"
    tools = {item["name"]: item for item in response["result"]["tools"]}
    public = {
        "lookup_phone_number",
        "list_public_campaigns",
        "get_public_campaign",
        "get_source_coverage",
        "get_methodology",
    }
    protected = {
        "create_private_watch",
        "delete_private_watch",
        "submit_organization_portfolio",
        "delete_organization_portfolio",
    }
    assert set(tools) == public | protected
    for name in public:
        assert tools[name]["annotations"]["readOnlyHint"] is True
        assert tools[name]["annotations"]["destructiveHint"] is False
    for name in protected:
        auth = tools[name]["_meta"]["callersignal.dev/auth"]
        assert auth["consentRequired"] is True
        assert auth["availability"] == "locked_until_oauth_provider_configured"
        assert auth["requiredScopes"]
        assert tools[name]["annotations"]["readOnlyHint"] is False
    assert tools["create_private_watch"]["annotations"]["destructiveHint"] is False
    assert tools["delete_private_watch"]["annotations"]["destructiveHint"] is True
    assert tools["delete_organization_portfolio"]["annotations"]["destructiveHint"] is True


def test_public_lookup_campaign_coverage_and_methodology_calls_share_canonical_data() -> None:
    service = deterministic_service()
    app = create_app(lookup_service=service)
    http_app = create_http_app(lookup_service=service)

    _, _, lookup = wsgi_request(
        app,
        message=rpc(
            4,
            "tools/call",
            {
                "name": "lookup_phone_number",
                "arguments": {"number": RESERVED},
            },
        ),
    )
    _, _, campaigns = wsgi_request(
        app,
        message=rpc(
            5,
            "tools/call",
            {"name": "list_public_campaigns", "arguments": {}},
        ),
    )
    _, _, coverage = wsgi_request(
        app,
        message=rpc(6, "tools/call", {"name": "get_source_coverage", "arguments": {}}),
    )
    _, _, methodology = wsgi_request(
        app,
        message=rpc(7, "tools/call", {"name": "get_methodology", "arguments": {}}),
    )

    http_status, _, http_campaigns = wsgi_request(
        http_app,
        method="GET",
        path="/v1/campaigns",
        message=None,
    )
    assert lookup["result"]["structuredContent"]["kind"] == "lookup_result"
    assert lookup["result"]["structuredContent"]["phone_number"]["canonical"]["e164"] == RESERVED
    assert http_status == "200 OK"
    assert campaigns["result"]["structuredContent"] == http_campaigns
    assert coverage["result"]["structuredContent"] == json.loads(
        (ROOT / "web/assets/transparency.json").read_text(encoding="utf-8")
    )
    policy = methodology["result"]["structuredContent"]
    assert policy["methodology_version"] == "1.0.0"
    assert [item["state"] for item in policy["risk_states"]] == [
        "official_warning",
        "elevated_signals",
        "no_risk_evidence",
        "insufficient_evidence",
    ]
    assert policy["lookup_popularity_used_for_reputation"] is False


def test_protected_calls_fail_at_http_boundary_with_scope_and_no_private_echo() -> None:
    app = create_app(lookup_service=deterministic_service())
    arguments = {
        "number": RESERVED,
        "contact": "private-person@example.test",
        "consent_receipt": "secret-consent-value",
        "idempotency_key": "private-key-value",
    }

    status, headers, response = wsgi_request(
        app,
        message=rpc(
            8,
            "tools/call",
            {"name": "create_private_watch", "arguments": arguments},
        ),
    )
    bearer_status, _, bearer_response = wsgi_request(
        app,
        message=rpc(
            9,
            "tools/call",
            {"name": "create_private_watch", "arguments": arguments},
        ),
        headers={"Authorization": "Bearer not-a-valid-production-token"},
    )

    assert status == "401 Unauthorized"
    assert headers["Cache-Control"] == "no-store"
    metadata_reference = (
        f'resource_metadata="https://callersignal.vercel.app{PROTECTED_RESOURCE_PATH}"'
    )
    assert metadata_reference in headers["WWW-Authenticate"]
    assert 'scope="callersignal.watch:write"' in headers["WWW-Authenticate"]
    assert response["error"]["code"] == -32001
    assert bearer_status == "401 Unauthorized"
    serialized = json.dumps({"anonymous": response, "bearer": bearer_response})
    assert RESERVED not in serialized
    assert "private-person" not in serialized
    assert "secret-consent-value" not in serialized
    assert "private-key-value" not in serialized


def test_transport_rejects_bad_origin_and_protocol_but_accepts_notifications() -> None:
    app = create_app(lookup_service=deterministic_service())

    origin_status, _, _ = wsgi_request(
        app,
        message=rpc(10, "tools/list", {}),
        headers={"Origin": "https://attacker.example"},
    )
    protocol_status, _, _ = wsgi_request(
        app,
        message=rpc(11, "tools/list", {}),
        headers={"MCP-Protocol-Version": "unsupported-version"},
    )
    get_status, get_headers, get_body = wsgi_request(
        app,
        method="GET",
        message=None,
        headers={"Accept": "text/event-stream"},
    )
    notification_status, notification_headers, notification_body = wsgi_request(
        app,
        message={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )

    assert origin_status == "403 Forbidden"
    assert protocol_status == "400 Bad Request"
    assert get_status == "405 Method Not Allowed"
    assert get_headers["Allow"] == "POST"
    assert get_body["error"]["code"] == -32000
    assert notification_status == "202 Accepted"
    assert notification_headers["Cache-Control"] == "no-store"
    assert notification_body is None


def test_protected_resource_metadata_is_honest_about_disabled_oauth() -> None:
    app = create_app(lookup_service=deterministic_service())
    status, headers, metadata = wsgi_request(
        app,
        method="GET",
        path=PROTECTED_RESOURCE_PATH,
        message=None,
    )

    assert status == "200 OK"
    assert headers["Cache-Control"] == "no-store"
    assert metadata["resource"] == "https://callersignal.vercel.app/mcp"
    assert metadata["scopes_supported"] == [
        "callersignal.organizations:delete",
        "callersignal.organizations:write",
        "callersignal.watch:delete",
        "callersignal.watch:write",
    ]
    assert metadata["authorization_servers"] == []
    assert metadata["callersignal.dev/authorization_status"] == "not_configured"


def test_vercel_entrypoint_and_routes_expose_mcp_and_metadata() -> None:
    entrypoint = ROOT / "api/mcp.py"
    spec = importlib.util.spec_from_file_location("callersignal_remote_mcp", entrypoint)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    status, headers, response = wsgi_request(
        module.app,
        message=rpc(12, "server/discover", {"_meta": {}}),
    )
    metadata_status, _, metadata = wsgi_request(
        module.app,
        method="GET",
        path="/api/mcp",
        query=urlencode({"route": "oauth-protected-resource"}),
        message=None,
    )
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    rewrites = {item["source"]: item["destination"] for item in config["rewrites"]}

    assert status == "200 OK"
    assert headers["Cache-Control"] == "no-store"
    assert response["result"]["serverInfo"]["name"] == "callersignal"
    assert metadata_status == "200 OK"
    assert metadata["resource"] == "https://callersignal.vercel.app/mcp"
    assert rewrites["/mcp"] == "/api/mcp"
    assert rewrites[PROTECTED_RESOURCE_PATH] == "/api/mcp?route=oauth-protected-resource"
    assert rewrites[f"{PROTECTED_RESOURCE_PATH}/mcp"] == (
        "/api/mcp?route=oauth-protected-resource"
    )
