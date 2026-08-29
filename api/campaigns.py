"""Vercel WSGI entrypoint for public, aggregate campaign reads."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(_SOURCE_ROOT))

from callersignal.http_api import application as _http_application  # noqa: E402


def app(environ, start_response):
    """Map list and detail function requests to canonical HTTP routes."""
    request = dict(environ)
    query = parse_qs(str(request.get("QUERY_STRING", "")), keep_blank_values=True)
    campaign_id = query.get("campaign_id", [None])[0]
    request["PATH_INFO"] = (
        f"/v1/campaigns/{campaign_id}" if campaign_id else "/v1/campaigns"
    )
    return _http_application(request, start_response)
