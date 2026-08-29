"""Run the stateless MCP endpoint locally on loopback for protocol smoke tests."""

from __future__ import annotations

import os
from wsgiref.simple_server import make_server

from callersignal.remote_mcp.application import create_app


def main() -> int:
    """Bind only to loopback and serve until interrupted."""
    port = int(os.environ.get("CALLERSIGNAL_MCP_PORT", "8766"))
    app = create_app(
        allowed_origins=frozenset(
            {
                "https://callersignal.vercel.app",
                f"http://127.0.0.1:{port}",
                f"http://localhost:{port}",
            }
        )
    )
    print(f"CallerSignal MCP listening on http://127.0.0.1:{port}/mcp", flush=True)
    try:
        make_server("127.0.0.1", port, app).serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
