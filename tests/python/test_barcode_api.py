from __future__ import annotations

import io
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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


def _abstain_evidence():
    from physical_vision_barcode import (
        BarcodeCountStatus,
        BarcodeFrameEvidence,
        BarcodeGuidanceAction,
        BarcodeReadiness,
    )

    return BarcodeFrameEvidence(
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


def test_analyze_rejects_overload_without_queueing_or_second_analyzer_call() -> None:
    from physical_vision_api import ApiSettings, create_app
    from starlette.testclient import TestClient

    entered = threading.Event()
    release = threading.Event()
    active = 0
    maximum_active = 0
    calls = 0
    lock = threading.Lock()

    def analyzer(*args, **kwargs):
        nonlocal active, maximum_active, calls
        with lock:
            calls += 1
            active += 1
            maximum_active = max(maximum_active, active)
        entered.set()
        assert release.wait(timeout=2.0)
        with lock:
            active -= 1
        return _abstain_evidence()

    settings = ApiSettings(max_in_flight=1, analysis_timeout_seconds=1.0)
    with (
        TestClient(
            create_app(analyzer=analyzer, settings=settings),
            base_url="http://127.0.0.1:8000",
        ) as client,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        first = executor.submit(
            client.post,
            "/v1/barcode/analyze",
            content=_png_bytes(),
            headers={"Content-Type": "image/png"},
        )
        assert entered.wait(timeout=2.0)
        overloaded = client.post(
            "/v1/barcode/analyze",
            content=_png_bytes(),
            headers={"Content-Type": "image/png"},
        )
        release.set()
        assert first.result(timeout=2.0).status_code == 200

    assert overloaded.status_code == 503
    assert overloaded.json() == {
        "error": "LOCAL_BUSY",
        "category": "local-resource",
        "message_key": "API_ANALYZER_BUSY",
    }
    assert calls == 1
    assert maximum_active == 1


def test_analyze_timeout_is_content_free_and_capacity_recovers() -> None:
    from physical_vision_api import ApiSettings, create_app
    from physical_vision_barcode import (
        BarcodeFrameFailure,
        BarcodeFrameFailureCode,
    )
    from starlette.testclient import TestClient

    calls = 0
    cancellation_seen = threading.Event()
    sentinel = "SN-CANARY-C:/Users/private/hostile.example"

    def analyzer(*args, deadline=None, cancelled=None, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            while cancelled is not None and not cancelled():
                time.sleep(0.001)
            cancellation_seen.set()
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.ANALYZE_BUDGET_EXCEEDED,
                "timeout",
                sentinel,
            )
        return _abstain_evidence()

    settings = ApiSettings(max_in_flight=1, analysis_timeout_seconds=0.03)
    with TestClient(
        create_app(analyzer=analyzer, settings=settings),
        base_url="http://127.0.0.1:8000",
    ) as client:
        timed_out = client.post(
            "/v1/barcode/analyze",
            content=_png_bytes(),
            headers={"Content-Type": "image/png"},
        )
        recovered = client.post(
            "/v1/barcode/analyze",
            content=_png_bytes(),
            headers={"Content-Type": "image/png"},
        )

    assert timed_out.status_code == 504
    assert timed_out.json() == {
        "error": "LOCAL_TIMEOUT",
        "category": "timeout",
        "message_key": "API_ANALYZER_TIMEOUT",
    }
    assert sentinel not in timed_out.text
    assert cancellation_seen.is_set()
    assert recovered.status_code == 200
    assert calls == 2


def test_analyzer_failure_is_content_free_and_capacity_recovers() -> None:
    from physical_vision_api import create_app
    from physical_vision_barcode import (
        BarcodeFrameFailure,
        BarcodeFrameFailureCode,
    )
    from starlette.testclient import TestClient

    calls = 0
    sentinel = "SN-CANARY-C:/Users/private/payload=secret"

    def analyzer(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.INVALID_IMAGE,
                "unsupported-input",
                sentinel,
            )
        return _abstain_evidence()

    with TestClient(
        create_app(analyzer=analyzer), base_url="http://127.0.0.1:8000"
    ) as client:
        failed = client.post(
            "/v1/barcode/analyze",
            content=_png_bytes(),
            headers={"Content-Type": "image/png"},
        )
        recovered = client.post(
            "/v1/barcode/analyze",
            content=_png_bytes(),
            headers={"Content-Type": "image/png"},
        )

    assert failed.status_code == 400
    assert failed.json() == {
        "error": "INVALID_IMAGE",
        "category": "unsupported-input",
        "message_key": "API_INVALID_IMAGE",
    }
    assert sentinel not in failed.text
    assert recovered.status_code == 200
    assert calls == 2


def test_cancelled_request_signals_analyzer_and_capacity_recovers() -> None:
    import asyncio

    import httpx
    from physical_vision_api import create_app
    from physical_vision_barcode import (
        BarcodeFrameFailure,
        BarcodeFrameFailureCode,
    )

    entered = threading.Event()
    cancellation_seen = threading.Event()
    calls = 0

    def analyzer(*args, cancelled=None, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            while cancelled is not None and not cancelled():
                time.sleep(0.001)
            cancellation_seen.set()
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.ANALYZE_BUDGET_EXCEEDED,
                "timeout",
                "BARCODE_FRAME_CANCELLED",
            )
        return _abstain_evidence()

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=create_app(analyzer=analyzer))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1:8000",
        ) as client:
            request = asyncio.create_task(
                client.post(
                    "/v1/barcode/analyze",
                    content=_png_bytes(),
                    headers={"Content-Type": "image/png"},
                )
            )
            assert await asyncio.to_thread(entered.wait, 2.0)
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
            assert await asyncio.to_thread(cancellation_seen.wait, 2.0)
            recovered = await client.post(
                "/v1/barcode/analyze",
                content=_png_bytes(),
                headers={"Content-Type": "image/png"},
            )
            assert recovered.status_code == 200

    asyncio.run(scenario())
    assert calls == 2


def test_resource_endpoint_has_stable_content_free_allowlist() -> None:
    from physical_vision_api import create_app
    from starlette.testclient import TestClient

    observation = {
        "schema_version": "live-resource-observation-v1",
        "policy_version": "live-resource-policy-v1",
        "elapsed_ms": 1.25,
        "process_rss_bytes": 123,
        "host_available_memory_bytes": 456,
        "in_flight": 0,
        "max_in_flight": 1,
        "gpu": {"status": "unavailable"},
    }
    client = TestClient(
        create_app(resource_probe=lambda **kwargs: observation),
        base_url="http://127.0.0.1:8000",
    )
    response = client.get("/v1/system/resources")

    assert response.status_code == 200
    assert response.json() == observation
    assert set(response.json()) == {
        "schema_version",
        "policy_version",
        "elapsed_ms",
        "process_rss_bytes",
        "host_available_memory_bytes",
        "in_flight",
        "max_in_flight",
        "gpu",
    }
    serialized = json.dumps(response.json(), sort_keys=True).lower()
    for forbidden in (
        "image",
        "barcode",
        "decoded",
        "ocr",
        "serial",
        "payload",
        "filename",
        "path",
        "url",
        "hostile.example",
        "origin",
        "request",
        "exception",
        "session",
        "user",
    ):
        assert forbidden not in serialized


def test_resource_endpoint_filters_unexpected_probe_content() -> None:
    from physical_vision_api import create_app
    from starlette.testclient import TestClient

    sentinel = "SN-CANARY-C:/private/payload=secret"
    observation = {
        "schema_version": "hostile-schema",
        "policy_version": "hostile-policy",
        "elapsed_ms": 1.25,
        "process_rss_bytes": 123,
        "host_available_memory_bytes": 456,
        "in_flight": 99,
        "max_in_flight": 99,
        "gpu": {"status": "unavailable", "name": sentinel},
        "payload": sentinel,
        "request": {"body": sentinel},
    }
    client = TestClient(
        create_app(resource_probe=lambda **kwargs: observation),
        base_url="http://127.0.0.1:8000",
    )
    response = client.get("/v1/system/resources")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "live-resource-observation-v1"
    assert body["policy_version"] == "live-resource-policy-v1"
    assert body["in_flight"] == 0
    assert body["max_in_flight"] == 1
    assert body["gpu"] == {"status": "unavailable"}
    assert sentinel not in response.text
    assert "payload" not in body
    assert "request" not in body


def test_resource_probe_failure_returns_unavailable_without_request_failure() -> None:
    from physical_vision_api import create_app
    from starlette.testclient import TestClient

    def unavailable_probe(**kwargs):
        raise RuntimeError("SN-CANARY C:/private payload=secret")

    client = TestClient(
        create_app(resource_probe=unavailable_probe),
        base_url="http://127.0.0.1:8000",
    )
    response = client.get("/v1/system/resources")

    assert response.status_code == 200
    body = response.json()
    assert body["process_rss_bytes"] is None
    assert body["host_available_memory_bytes"] is None
    assert body["gpu"] == {"status": "unavailable"}
    assert "SN-CANARY" not in response.text
    assert "private" not in response.text
