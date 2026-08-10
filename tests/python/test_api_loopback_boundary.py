from __future__ import annotations

import io
from unittest.mock import Mock

import pytest
from physical_vision_geometry import NormalizedBox
from PIL import Image
from starlette.testclient import TestClient


def _png_bytes() -> bytes:
    image = Image.new("RGB", (80, 60), (40, 40, 40))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _evidence():
    from physical_vision_barcode import (
        BarcodeCountStatus,
        BarcodeFrameEvidence,
        BarcodeGuidanceAction,
        BarcodeReadiness,
    )

    return BarcodeFrameEvidence(
        count_status=BarcodeCountStatus.ONE,
        barcode_box=NormalizedBox(0.1, 0.2, 0.9, 0.5),
        proposal_sources=("test",),
        elapsed_ms=1.0,
        recipe_version="barcode-frame-ready-v1",
        readiness=BarcodeReadiness.READY,
        guidance_action=BarcodeGuidanceAction.NONE,
        failing_gates=(),
        quality=None,
    )


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost:8000", "[::1]:8000"])
def test_configured_loopback_host_forms_are_allowed(host: str) -> None:
    from physical_vision_api import create_app

    client = TestClient(create_app(), base_url="http://127.0.0.1:8000")

    response = client.get("/health", headers={"host": host})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        "",
        "testserver",
        "192.168.1.20:8000",
        "physical-vision.local:8000",
        "127.0.0.1.evil.example:8000",
        "127.0.0.1:9000",
        "localhost:5173",
        "localhost@evil.example:8000",
        "::1:8000",
        "localhost:8000,evil.example",
    ],
)
def test_non_loopback_malformed_or_disallowed_host_is_rejected_content_free(host: str) -> None:
    from physical_vision_api import create_app

    client = TestClient(create_app(), base_url="http://127.0.0.1:8000")

    response = client.get("/health", headers={"host": host})

    assert response.status_code == 403
    assert response.json() == {
        "error": "HOST_NOT_ALLOWED",
        "category": "local-security",
        "message_key": "API_HOST_NOT_ALLOWED",
    }
    if host:
        assert host not in response.text


@pytest.mark.parametrize(
    "origin",
    [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://[::1]:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
        "http://[::1]:4173",
        "http://127.0.0.1:8080",
        "http://localhost:8080",
        "http://[::1]:8080",
    ],
)
def test_configured_loopback_origins_are_allowed_for_analysis(origin: str) -> None:
    from physical_vision_api import create_app

    analyzer = Mock(return_value=_evidence())
    client = TestClient(create_app(analyzer=analyzer), base_url="http://127.0.0.1:8000")

    response = client.post(
        "/v1/barcode/analyze",
        files={"image": ("frame.png", _png_bytes(), "image/png")},
        headers={"origin": origin},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    analyzer.assert_called_once()


def test_analysis_without_origin_is_allowed_for_local_cli() -> None:
    from physical_vision_api import create_app

    analyzer = Mock(return_value=_evidence())
    client = TestClient(create_app(analyzer=analyzer), base_url="http://127.0.0.1:8000")

    response = client.post(
        "/v1/barcode/analyze",
        files={"image": ("frame.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    analyzer.assert_called_once()


@pytest.mark.parametrize(
    "origin",
    [
        "null",
        "file://",
        "https://127.0.0.1:5173",
        "http://192.168.1.20:5173",
        "http://evil.example:5173",
        "http://localhost.evil.example:5173",
        "http://localhost:5174",
        "http://localhost:5173/path",
        "http://user@localhost:5173",
        "http://localhost:5173, http://evil.example",
        "not-an-origin",
    ],
)
def test_disallowed_or_malformed_origin_is_rejected_before_processing(origin: str) -> None:
    from physical_vision_api import create_app

    analyzer = Mock(return_value=_evidence())
    client = TestClient(create_app(analyzer=analyzer), base_url="http://127.0.0.1:8000")

    response = client.post(
        "/v1/barcode/analyze",
        content=b"private-image-sentinel",
        headers={"content-type": "image/png", "origin": origin},
    )

    assert response.status_code == 403
    assert response.json() == {
        "error": "ORIGIN_NOT_ALLOWED",
        "category": "local-security",
        "message_key": "API_ORIGIN_NOT_ALLOWED",
    }
    assert origin not in response.text
    assert "private-image-sentinel" not in response.text
    analyzer.assert_not_called()


def test_lan_host_and_origin_cannot_be_configured() -> None:
    from physical_vision_api.app import ApiSettings, create_app

    with pytest.raises(ValueError, match="loopback"):
        create_app(settings=ApiSettings(allowed_hosts=("192.168.1.20:8000",)))

    with pytest.raises(ValueError, match="loopback"):
        create_app(settings=ApiSettings(cors_origins=("http://192.168.1.20:5173",)))
