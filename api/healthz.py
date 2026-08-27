"""Vercel WSGI entrypoint for CallerSignal's privacy-safe readiness probe."""

from __future__ import annotations

import sys
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(_SOURCE_ROOT))

from callersignal.http_api import application as _http_application  # noqa: E402


def app(environ, start_response):
    """Map the platform function route to the canonical health endpoint."""
    request = dict(environ)
    request["PATH_INFO"] = "/healthz"
    return _http_application(request, start_response)
