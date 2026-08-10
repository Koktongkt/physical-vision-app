from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from physical_vision_geometry import NormalizedBox
from PIL import Image


def _png_bytes(
    size: tuple[int, int] = (80, 60), color: tuple[int, int, int] = (40, 40, 40)
) -> bytes:
    image = Image.new("RGB", size, color)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def test_health_returns_ok() -> None:
    from physical_vision_api import create_app
    from starlette.testclient import TestClient

    client = TestClient(create_app(), base_url="http://127.0.0.1:8000")
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_analyze_multipart_png_returns_count_without_decode_fields() -> None:
    from physical_vision_api import create_app
    from physical_vision_barcode import (
        BarcodeCountStatus,
        BarcodeFrameEvidence,
        BarcodeGuidanceAction,
        BarcodeQualityMetrics,
        BarcodeReadiness,
    )
    from starlette.testclient import TestClient

    fake = BarcodeFrameEvidence(
        count_status=BarcodeCountStatus.ONE,
        barcode_box=NormalizedBox(0.1, 0.2, 0.9, 0.5),
        proposal_sources=("opencv_barcode_detect",),
        elapsed_ms=3.5,
        recipe_version="barcode-frame-ready-v1",
        readiness=BarcodeReadiness.READY,
        guidance_action=BarcodeGuidanceAction.NONE,
        failing_gates=(),
        quality=BarcodeQualityMetrics(
            area_normalized=0.24,
            short_side_px=90.0,
            margin_left=0.1,
            margin_right=0.1,
            margin_top=0.2,
            margin_bottom=0.5,
            laplacian_variance=120.0,
            aspect_ratio=2.67,
            exposure_mean=128.0,
        ),
    )

    with patch("physical_vision_api.app.analyze_barcode_frame", return_value=fake):
        client = TestClient(create_app(), base_url="http://127.0.0.1:8000")
        response = client.post(
            "/v1/barcode/analyze",
            files={"image": ("frame.png", _png_bytes(), "image/png")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["count_status"] == "one"
    assert body["barcode_box"] == {"x0": 0.1, "y0": 0.2, "x1": 0.9, "y1": 0.5}
    assert body["proposal_sources"] == ["opencv_barcode_detect"]
    assert body["recipe_version"] == "barcode-frame-ready-v1"
    assert body["readiness"] == "ready"
    assert body["guidance_action"] == "none"
    assert body["failing_gates"] == []
    assert body["quality"]["area_normalized"] == pytest.approx(0.24)
    assert body["quality"]["laplacian_variance"] == pytest.approx(120.0)
    assert "payload" not in body
    assert "decoded" not in body
    assert "raw_string" not in body
    assert "serial" not in str(body).lower()


def test_analyze_multiple_returns_null_box() -> None:
    from physical_vision_api import create_app
    from physical_vision_barcode import (
        BarcodeCountStatus,
        BarcodeFrameEvidence,
        BarcodeGuidanceAction,
        BarcodeReadiness,
    )
    from starlette.testclient import TestClient

    fake = BarcodeFrameEvidence(
        count_status=BarcodeCountStatus.MULTIPLE,
        barcode_box=None,
        proposal_sources=("morph_barcode", "opencv_barcode_detect"),
        elapsed_ms=1.0,
        recipe_version="barcode-frame-ready-v1",
        readiness=BarcodeReadiness.ABSTAIN,
        guidance_action=BarcodeGuidanceAction.NONE,
        failing_gates=(),
        quality=None,
    )
    with patch("physical_vision_api.app.analyze_barcode_frame", return_value=fake):
        client = TestClient(create_app(), base_url="http://127.0.0.1:8000")
        response = client.post(
            "/v1/barcode/analyze",
            files={"image": ("frame.png", _png_bytes(), "image/png")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["count_status"] == "multiple"
    assert body["barcode_box"] is None
    assert body["readiness"] == "abstain"
    assert body["guidance_action"] == "none"
    assert body["failing_gates"] == []
    assert body["quality"] is None


def test_analyze_rejects_oversize_body() -> None:
    from physical_vision_api import create_app
    from starlette.testclient import TestClient

    client = TestClient(create_app(max_body_bytes=1024), base_url="http://127.0.0.1:8000")
    huge = b"\x89PNG\r\n\x1a\n" + (b"x" * 5000)
    response = client.post(
        "/v1/barcode/analyze",
        files={"image": ("huge.png", huge, "image/png")},
    )
    assert response.status_code == 413
    body = response.json()
    assert "message_key" in body
    assert "payload" not in body


def test_analyze_raw_body_jpeg_accepted() -> None:
    from physical_vision_api import create_app
    from physical_vision_barcode import (
        BarcodeCountStatus,
        BarcodeFrameEvidence,
        BarcodeGuidanceAction,
        BarcodeReadiness,
    )
    from starlette.testclient import TestClient

    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (20, 20, 20)).save(buf, format="JPEG")
    jpeg = buf.getvalue()
    fake = BarcodeFrameEvidence(
        count_status=BarcodeCountStatus.NONE,
        barcode_box=None,
        proposal_sources=(),
        elapsed_ms=0.5,
        recipe_version="barcode-frame-ready-v1",
        readiness=BarcodeReadiness.ABSTAIN,
        guidance_action=BarcodeGuidanceAction.NONE,
        failing_gates=(),
        quality=None,
    )
    with patch("physical_vision_api.app.analyze_barcode_frame", return_value=fake):
        client = TestClient(create_app(), base_url="http://127.0.0.1:8000")
        response = client.post(
            "/v1/barcode/analyze",
            content=jpeg,
            headers={"Content-Type": "image/jpeg"},
        )
    assert response.status_code == 200
    assert response.json()["count_status"] == "none"
    assert response.json()["readiness"] == "abstain"


def test_analyze_guidance_returns_single_action_and_failing_gates() -> None:
    from physical_vision_api import create_app
    from physical_vision_barcode import (
        BarcodeCountStatus,
        BarcodeFrameEvidence,
        BarcodeGuidanceAction,
        BarcodeQualityMetrics,
        BarcodeReadiness,
    )
    from starlette.testclient import TestClient

    fake = BarcodeFrameEvidence(
        count_status=BarcodeCountStatus.ONE,
        barcode_box=NormalizedBox(0.0, 0.3, 0.5, 0.6),
        proposal_sources=("inject",),
        elapsed_ms=2.0,
        recipe_version="barcode-frame-ready-v1",
        readiness=BarcodeReadiness.GUIDANCE,
        guidance_action=BarcodeGuidanceAction.CAMERA_RIGHT,
        failing_gates=("margin_left",),
        quality=BarcodeQualityMetrics(
            area_normalized=0.15,
            short_side_px=60.0,
            margin_left=0.0,
            margin_right=0.5,
            margin_top=0.3,
            margin_bottom=0.4,
            laplacian_variance=80.0,
            aspect_ratio=2.5,
            exposure_mean=100.0,
        ),
    )
    with patch("physical_vision_api.app.analyze_barcode_frame", return_value=fake):
        client = TestClient(create_app(), base_url="http://127.0.0.1:8000")
        response = client.post(
            "/v1/barcode/analyze",
            files={"image": ("frame.png", _png_bytes(), "image/png")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["readiness"] == "guidance"
    assert body["guidance_action"] == "camera_right"
    assert body["failing_gates"] == ["margin_left"]
    assert body["count_status"] == "one"
    assert "payload" not in body


def test_analyze_invalid_bytes_returns_content_free_error() -> None:
    from physical_vision_api import create_app
    from starlette.testclient import TestClient

    client = TestClient(create_app(), base_url="http://127.0.0.1:8000")
    response = client.post(
        "/v1/barcode/analyze",
        files={"image": ("bad.png", b"not-an-image", "image/png")},
    )
    assert response.status_code in {400, 422}
    body = response.json()
    assert "message_key" in body
    # Must not echo raw body content.
    assert "not-an-image" not in str(body)
