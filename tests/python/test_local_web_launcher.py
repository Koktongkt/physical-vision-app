from __future__ import annotations

import http.client
import importlib.util
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest


def _load_launcher():
    path = Path(__file__).parents[2] / "scripts" / "run_local_barcode_web.py"
    spec = importlib.util.spec_from_file_location("run_local_barcode_web", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_web_launcher_binds_only_ipv4_loopback_and_targets_approved_url() -> None:
    launcher = _load_launcher()

    assert launcher.WEB_URL == "http://127.0.0.1:5173/"
    server = launcher.create_server(port=0)
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert server.server_address[1] > 0
    finally:
        server.server_close()


def test_web_launcher_serves_client_with_private_security_headers() -> None:
    launcher = _load_launcher()
    server = launcher.create_server(port=0)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        with urllib.request.urlopen(url, timeout=2) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers["Cache-Control"] == "no-store"
            assert (
                "connect-src http://127.0.0.1:8000" in response.headers["Content-Security-Policy"]
            )
            assert response.headers["Permissions-Policy"] == "camera=(self)"
            assert "Physical Vision" in body
        localhost_request = urllib.request.Request(
            url, headers={"Host": f"localhost:{server.server_address[1]}"}
        )
        with urllib.request.urlopen(localhost_request, timeout=2) as response:
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.parametrize(
    "host",
    [
        "attacker.invalid",
        "attacker.invalid:5173",
        "127.0.0.1.evil.invalid:5173",
        "127.0.0.1:5173,attacker.invalid",
        "localhost@attacker.invalid:5173",
        "",
    ],
)
def test_web_launcher_rejects_hostile_or_malformed_host_content_free(host: str) -> None:
    launcher = _load_launcher()
    server = launcher.create_server(port=0)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    sentinel = "PAYLOAD-CANARY-C:/private/barcode-secret"
    try:
        port = server.server_address[1]
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/{sentinel}", headers={"Host": host}
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=2)
        response = caught.value
        body = response.read().decode("utf-8")
        assert response.code == 403
        assert body == "Local request rejected.\n"
        if host:
            assert host not in body
        assert sentinel not in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert not thread.is_alive()


def test_web_launcher_rejects_duplicate_host_headers() -> None:
    launcher = _load_launcher()
    server = launcher.create_server(port=0)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
    try:
        connection.putrequest("GET", "/", skip_host=True)
        connection.putheader("Host", f"127.0.0.1:{server.server_address[1]}")
        connection.putheader("Host", "attacker.invalid")
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == 403
        assert response.read() == b"Local request rejected.\n"
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert not thread.is_alive()


class _FakeServer:
    def __init__(self, failure: BaseException | None = None) -> None:
        self.failure = failure
        self.served = 0
        self.closed = 0

    def serve_forever(self) -> None:
        self.served += 1
        if self.failure is not None:
            raise self.failure

    def server_close(self) -> None:
        self.closed += 1


def test_web_launcher_closes_server_after_normal_stop() -> None:
    launcher = _load_launcher()
    server = _FakeServer()
    opened = []

    launcher.run(
        server_factory=lambda: server,
        browser_open=lambda url: opened.append(url) or True,
    )

    assert opened == ["http://127.0.0.1:5173/"]
    assert server.served == 1
    assert server.closed == 1


def test_web_launcher_closes_server_when_browser_startup_fails() -> None:
    launcher = _load_launcher()
    server = _FakeServer()

    try:
        launcher.run(server_factory=lambda: server, browser_open=lambda _url: False)
    except launcher.LauncherError as error:
        assert str(error) == "BROWSER_LAUNCH_FAILED"
    else:
        raise AssertionError("expected browser startup failure")

    assert server.served == 0
    assert server.closed == 1


def test_web_launcher_closes_server_when_serving_is_cancelled() -> None:
    launcher = _load_launcher()
    server = _FakeServer(KeyboardInterrupt())

    try:
        launcher.run(server_factory=lambda: server, browser_open=lambda _url: True)
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("expected cancellation")

    assert server.served == 1
    assert server.closed == 1
