"""Local same-origin server used only for browser and screenshot verification."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from wsgiref.simple_server import make_server

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT / "src"))

from callersignal.http_api import application as lookup_application  # noqa: E402

STATIC_FILES = {
    "/": (WEB / "index.html", "text/html; charset=utf-8"),
    "/index.html": (WEB / "index.html", "text/html; charset=utf-8"),
    "/assets/app.js": (WEB / "assets" / "app.js", "text/javascript; charset=utf-8"),
    "/assets/styles.css": (WEB / "assets" / "styles.css", "text/css; charset=utf-8"),
}


def app(environ, start_response):
    request_path = str(environ.get("PATH_INFO", "/"))
    if request_path == "/v1/lookup" or request_path.startswith("/v1/campaigns"):
        return lookup_application(environ, start_response)
    if request_path == "/campaigns" or request_path.startswith("/campaigns/"):
        request_path = "/"
    item = STATIC_FILES.get(request_path)
    if item is None:
        body = b"Not found"
        start_response(
            "404 Not Found",
            [("Content-Type", "text/plain"), ("Content-Length", str(len(body)))],
        )
        return [body]
    path, content_type = item
    body = path.read_bytes()
    start_response(
        "200 OK",
        [("Content-Type", content_type), ("Content-Length", str(len(body)))],
    )
    return [body]


if __name__ == "__main__":
    port = int(os.environ.get("CALLERSIGNAL_TEST_PORT", "8765"))
    print(f"Serving CallerSignal browser proof on http://127.0.0.1:{port}", flush=True)
    make_server("127.0.0.1", port, app).serve_forever()
