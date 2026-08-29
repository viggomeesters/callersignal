"""Vercel WSGI entrypoint for CallerSignal's public source coverage."""

from __future__ import annotations

import sys
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(_SOURCE_ROOT))

from callersignal.http_api import application as _application  # noqa: E402


def app(environ, start_response):
    """Map the platform function route to the canonical coverage endpoint."""
    request = dict(environ)
    request["PATH_INFO"] = "/v1/coverage"
    return _application(request, start_response)
