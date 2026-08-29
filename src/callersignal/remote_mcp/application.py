"""Dependency-free stateless Streamable HTTP application for Vercel."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from callersignal.http_api import create_app as create_http_app
from callersignal.lookup import LookupService
from callersignal.remote_mcp.tools import (
    PROTECTED_TOOL_SCOPES,
    call_public_tool,
    tool_definitions,
)

StartResponse = Callable[[str, list[tuple[str, str]]], Any]
CURRENT_PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = (
    CURRENT_PROTOCOL_VERSION,
    LEGACY_PROTOCOL_VERSION,
    "2025-06-18",
)
PROTECTED_RESOURCE_PATH = "/.well-known/oauth-protected-resource"
CANONICAL_ORIGIN = "https://callersignal.vercel.app"
CANONICAL_RESOURCE = f"{CANONICAL_ORIGIN}/mcp"
_MAX_BODY_BYTES = 65_536
_STATUS = {
    200: "200 OK",
    202: "202 Accepted",
    400: "400 Bad Request",
    401: "401 Unauthorized",
    403: "403 Forbidden",
    404: "404 Not Found",
    405: "405 Method Not Allowed",
    413: "413 Content Too Large",
    415: "415 Unsupported Media Type",
}


@dataclass(frozen=True, slots=True)
class _Response:
    status: int
    payload: Mapping[str, Any] | None
    headers: tuple[tuple[str, str], ...] = ()


class RemoteMCPApplication:
    """Stateless MCP HTTP endpoint with fail-closed protected-tool authorization."""

    def __init__(
        self,
        *,
        lookup_service: LookupService,
        allowed_origins: frozenset[str],
    ) -> None:
        self._lookup_service = lookup_service
        self._http_application = create_http_app(lookup_service=lookup_service)
        self._allowed_origins = allowed_origins

    def __call__(
        self,
        environ: Mapping[str, Any],
        start_response: StartResponse,
    ) -> Iterable[bytes]:
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/mcp"))
        origin = environ.get("HTTP_ORIGIN")
        if origin is not None and str(origin) not in self._allowed_origins:
            return self._send(
                start_response,
                _error_response(403, None, -32000, "Origin is not allowed."),
            )
        if path in {PROTECTED_RESOURCE_PATH, f"{PROTECTED_RESOURCE_PATH}/mcp"}:
            if method != "GET":
                return self._send(
                    start_response,
                    _error_response(
                        405,
                        None,
                        -32000,
                        "Protected resource metadata supports GET only.",
                        headers=(("Allow", "GET"),),
                    ),
                )
            return self._send(start_response, _json_response(200, protected_metadata()))
        if path != "/mcp":
            return self._send(
                start_response,
                _error_response(404, None, -32000, "MCP route not found."),
            )
        if method == "GET":
            return self._send(
                start_response,
                _error_response(
                    405,
                    None,
                    -32000,
                    "This stateless endpoint does not offer a server-sent event stream.",
                    headers=(("Allow", "POST"),),
                ),
            )
        if method != "POST":
            return self._send(
                start_response,
                _error_response(
                    405,
                    None,
                    -32000,
                    "Only POST and metadata GET are supported.",
                    headers=(("Allow", "POST"),),
                ),
            )
        protocol = environ.get("HTTP_MCP_PROTOCOL_VERSION")
        if protocol is not None and str(protocol) not in SUPPORTED_PROTOCOL_VERSIONS:
            return self._send(
                start_response,
                _error_response(400, None, -32600, "Unsupported MCP protocol version."),
            )
        if str(environ.get("CONTENT_TYPE", "")).split(";", 1)[0] != "application/json":
            return self._send(
                start_response,
                _error_response(415, None, -32600, "Content-Type must be application/json."),
            )
        parsed = self._read_message(environ)
        if isinstance(parsed, _Response):
            return self._send(start_response, parsed)
        if not isinstance(parsed, Mapping) or parsed.get("jsonrpc") != "2.0":
            return self._send(
                start_response,
                _error_response(400, None, -32600, "Invalid JSON-RPC request."),
            )
        if "id" not in parsed:
            return self._send(start_response, _Response(202, None))

        request_id = parsed["id"]
        protected_scope = _protected_scope(parsed)
        if protected_scope is not None:
            return self._send(
                start_response,
                _unauthorized_response(request_id, protected_scope),
            )
        return self._send(start_response, self._handle_rpc(parsed))

    def _handle_rpc(self, message: Mapping[str, Any]) -> _Response:
        request_id = message["id"]
        method = message.get("method")
        if method == "server/discover":
            return _rpc_success(request_id, _discovery_result())
        if method == "initialize":
            params = message.get("params")
            requested = params.get("protocolVersion") if isinstance(params, Mapping) else None
            negotiated = (
                str(requested)
                if requested in SUPPORTED_PROTOCOL_VERSIONS
                else LEGACY_PROTOCOL_VERSION
            )
            return _rpc_success(
                request_id,
                {
                    "protocolVersion": negotiated,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": _server_info(),
                    "instructions": _instructions(),
                },
            )
        if method == "ping":
            return _rpc_success(request_id, {})
        if method == "tools/list":
            return _rpc_success(request_id, {"tools": tool_definitions()})
        if method == "tools/call":
            params = message.get("params")
            if not isinstance(params, Mapping):
                return _rpc_success(request_id, _tool_error("Tool parameters must be an object."))
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, Mapping):
                return _rpc_success(
                    request_id,
                    _tool_error("Tool name and arguments are required."),
                )
            result = call_public_tool(
                name,
                arguments,
                lookup_service=self._lookup_service,
                http_application=self._http_application,
            )
            return _rpc_success(request_id, result)
        return _error_response(200, request_id, -32601, "Method not found.")

    @staticmethod
    def _read_message(environ: Mapping[str, Any]) -> Mapping[str, Any] | _Response:
        try:
            length = int(str(environ.get("CONTENT_LENGTH", "0")))
        except ValueError:
            return _error_response(400, None, -32600, "Invalid content length.")
        if length < 1:
            return _error_response(400, None, -32600, "A JSON-RPC body is required.")
        if length > _MAX_BODY_BYTES:
            return _error_response(413, None, -32600, "Request body is too large.")
        stream = environ.get("wsgi.input")
        try:
            raw = stream.read(length) if stream is not None else b""
            value = json.loads(raw)
        except (AttributeError, json.JSONDecodeError, UnicodeDecodeError):
            return _error_response(400, None, -32700, "Parse error.")
        return value

    @staticmethod
    def _send(start_response: StartResponse, response: _Response) -> Iterable[bytes]:
        body = (
            json.dumps(response.payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
            if response.payload is not None
            else b""
        )
        headers = [
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
            *response.headers,
        ]
        if body:
            headers.extend(
                [
                    ("Content-Type", "application/json; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                ]
            )
        else:
            headers.append(("Content-Length", "0"))
        start_response(_STATUS[response.status], headers)
        return [body] if body else []


def create_app(
    *,
    lookup_service: LookupService | None = None,
    allowed_origins: frozenset[str] | None = None,
) -> RemoteMCPApplication:
    """Create the hosted MCP application with a fixed public origin allowlist."""
    return RemoteMCPApplication(
        lookup_service=lookup_service or LookupService(),
        allowed_origins=allowed_origins or frozenset({CANONICAL_ORIGIN}),
    )


def protected_metadata() -> dict[str, Any]:
    """Advertise scopes without pretending that an OAuth issuer exists."""
    return {
        "resource": CANONICAL_RESOURCE,
        "authorization_servers": [],
        "scopes_supported": sorted(set(PROTECTED_TOOL_SCOPES.values())),
        "bearer_methods_supported": ["header"],
        "resource_documentation": (
            "https://github.com/viggomeesters/callersignal/blob/main/docs/mcp.md"
        ),
        "callersignal.dev/authorization_status": "not_configured",
        "callersignal.dev/protected_operations_enabled": False,
    }


def _discovery_result() -> dict[str, Any]:
    return {
        "resultType": "complete",
        "supportedVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": _server_info(),
        "instructions": _instructions(),
    }


def _server_info() -> dict[str, Any]:
    return {
        "name": "callersignal",
        "title": "CallerSignal",
        "version": "0.3.0",
        "description": "Evidence-backed caller-campaign intelligence with explicit unknowns.",
        "websiteUrl": CANONICAL_ORIGIN,
    }


def _instructions() -> str:
    return (
        "Before a phone lookup, state the country interpretation being checked. Preserve "
        "source limits, no-match uncertainty, caller-ID spoofing risk, and recommended action. "
        "Protected writes are disabled until a real OAuth issuer is configured."
    )


def _protected_scope(message: Mapping[str, Any]) -> str | None:
    if message.get("method") != "tools/call":
        return None
    params = message.get("params")
    name = params.get("name") if isinstance(params, Mapping) else None
    return PROTECTED_TOOL_SCOPES.get(str(name))


def _unauthorized_response(request_id: Any, scope: str) -> _Response:
    metadata = f"{CANONICAL_ORIGIN}{PROTECTED_RESOURCE_PATH}"
    challenge = f'Bearer resource_metadata="{metadata}", scope="{scope}"'
    return _error_response(
        401,
        request_id,
        -32001,
        "Authorization is required; protected operations are not enabled on this deployment.",
        headers=(("WWW-Authenticate", challenge),),
    )


def _rpc_success(request_id: Any, result: Mapping[str, Any]) -> _Response:
    return _json_response(200, {"jsonrpc": "2.0", "id": request_id, "result": dict(result)})


def _json_response(status: int, payload: Mapping[str, Any]) -> _Response:
    return _Response(status=status, payload=dict(payload))


def _error_response(
    status: int,
    request_id: Any,
    code: int,
    message: str,
    *,
    headers: tuple[tuple[str, str], ...] = (),
) -> _Response:
    return _Response(
        status=status,
        payload={
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        },
        headers=headers,
    )


def _tool_error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


application = create_app()
