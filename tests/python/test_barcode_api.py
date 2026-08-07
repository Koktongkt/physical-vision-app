from __future__ import annotations

import io
from unittest.mock import patch

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

    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_analyze_multipart_png_returns_count_without_decode_fields() -> None:
    from physical_vision_api import create_app
    from physical_vision_barcode import BarcodeCountStatus, BarcodeFrameEvidence
    from starlette.testclient import TestClient

    fake = BarcodeFrameEvidence(
        count_status=BarcodeCountStatus.ONE,
        barcode_box=NormalizedBox(0.1, 0.2, 0.9, 0.5),
        proposal_sources=("opencv_barcode_detect",),
        elapsed_ms=3.5,
        recipe_version="barcode-frame-analyze-v1",
    )

    with patch("physical_vision_api.app.analyze_barcode_frame", return_value=fake):
        client = TestClient(create_app())
        response = client.post(
            "/v1/barcode/analyze",
            files={"image": ("frame.png", _png_bytes(), "image/png")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["count_status"] == "one"
    assert body["barcode_box"] == {"x0": 0.1, "y0": 0.2, "x1": 0.9, "y1": 0.5}
    assert body["proposal_sources"] == ["opencv_barcode_detect"]
    assert body["recipe_version"] == "barcode-frame-analyze-v1"
    assert "payload" not in body
    assert "decoded" not in body
    assert "raw_string" not in body
    assert "serial" not in str(body).lower()


def test_analyze_multiple_returns_null_box() -> None:
    from physical_vision_api import create_app
    from physical_vision_barcode import BarcodeCountStatus, BarcodeFrameEvidence
    from starlette.testclient import TestClient

    fake = BarcodeFrameEvidence(
        count_status=BarcodeCountStatus.MULTIPLE,
        barcode_box=None,
        proposal_sources=("morph_barcode", "opencv_barcode_detect"),
        elapsed_ms=1.0,
        recipe_version="barcode-frame-analyze-v1",
    )
    with patch("physical_vision_api.app.analyze_barcode_frame", return_value=fake):
        client = TestClient(create_app())
        response = client.post(
            "/v1/barcode/analyze",
            files={"image": ("frame.png", _png_bytes(), "image/png")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["count_status"] == "multiple"
    assert body["barcode_box"] is None


def test_analyze_rejects_oversize_body() -> None:
    from physical_vision_api import create_app
    from starlette.testclient import TestClient

    client = TestClient(create_app(max_body_bytes=1024))
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
    from physical_vision_barcode import BarcodeCountStatus, BarcodeFrameEvidence
    from starlette.testclient import TestClient

    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (20, 20, 20)).save(buf, format="JPEG")
    jpeg = buf.getvalue()
    fake = BarcodeFrameEvidence(
        count_status=BarcodeCountStatus.NONE,
        barcode_box=None,
        proposal_sources=(),
        elapsed_ms=0.5,
        recipe_version="barcode-frame-analyze-v1",
    )
    with patch("physical_vision_api.app.analyze_barcode_frame", return_value=fake):
        client = TestClient(create_app())
        response = client.post(
            "/v1/barcode/analyze",
            content=jpeg,
            headers={"Content-Type": "image/jpeg"},
        )
    assert response.status_code == 200
    assert response.json()["count_status"] == "none"


def test_analyze_invalid_bytes_returns_content_free_error() -> None:
    from physical_vision_api import create_app
    from starlette.testclient import TestClient

    client = TestClient(create_app())
    response = client.post(
        "/v1/barcode/analyze",
        files={"image": ("bad.png", b"not-an-image", "image/png")},
    )
    assert response.status_code in {400, 422}
    body = response.json()
    assert "message_key" in body
    # Must not echo raw body content.
    assert "not-an-image" not in str(body)
