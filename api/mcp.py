"""Vercel WSGI entrypoint for the stateless CallerSignal MCP endpoint."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(_SOURCE_ROOT))

from callersignal.remote_mcp import PROTECTED_RESOURCE_PATH  # noqa: E402
from callersignal.remote_mcp.application import application  # noqa: E402


def app(environ, start_response):
    """Map Vercel rewrites to the canonical MCP or protected-resource path."""
    request = dict(environ)
    query = parse_qs(str(request.get("QUERY_STRING", "")), keep_blank_values=True)
    request["PATH_INFO"] = (
        PROTECTED_RESOURCE_PATH
        if query.get("route", [None])[0] == "oauth-protected-resource"
        else "/mcp"
    )
    return application(request, start_response)
