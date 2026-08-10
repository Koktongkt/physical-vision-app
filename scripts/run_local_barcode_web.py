"""Serve the barcode web client on the approved loopback URL only.

Usage (from repository root):
  uvx --from uv==0.11.31 uv run python scripts/run_local_barcode_web.py
"""

from __future__ import annotations

import sys
import webbrowser
from collections.abc import Callable
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "apps" / "web"
WEB_HOST = "127.0.0.1"
WEB_PORT = 5173
WEB_URL = "http://127.0.0.1:5173/"


class Server(Protocol):
    def serve_forever(self) -> None: ...

    def server_close(self) -> None: ...


class LauncherError(RuntimeError):
    """A content-free local launcher failure."""


class LocalWebHandler(SimpleHTTPRequestHandler):
    """Static handler with no request-path logging or directory listing."""

    def log_message(self, format: str, *args: object) -> None:
        return

    def list_directory(self, path: str):
        self.send_error(404)
        return None

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; connect-src http://127.0.0.1:8000; "
            "img-src 'self' blob: data:; media-src 'self' blob:; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.send_header("Permissions-Policy", "camera=(self)")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


def create_server(*, port: int = WEB_PORT) -> ThreadingHTTPServer:
    handler = partial(LocalWebHandler, directory=str(WEB_ROOT))
    server = ThreadingHTTPServer((WEB_HOST, port), handler)
    server.daemon_threads = True
    return server


def run(
    *,
    server_factory: Callable[[], Server] = create_server,
    browser_open: Callable[[str], bool] = webbrowser.open,
) -> None:
    server = server_factory()
    try:
        if not browser_open(WEB_URL):
            raise LauncherError("BROWSER_LAUNCH_FAILED")
        server.serve_forever()
    finally:
        server.server_close()


def main() -> int:
    try:
        run()
    except KeyboardInterrupt:
        return 0
    except (LauncherError, OSError):
        print("Local web launcher failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
