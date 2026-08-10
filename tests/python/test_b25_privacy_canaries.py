from __future__ import annotations

import io
import logging

from PIL import Image
from starlette.testclient import TestClient


def _png_bytes() -> bytes:
    image = Image.new("RGB", (80, 60), (40, 40, 40))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_b25_sentinels_never_reach_responses_metrics_logs_repr_or_disk(
    caplog, capsys, monkeypatch, tmp_path
) -> None:
    from physical_vision_api import create_app
    from physical_vision_barcode import BarcodeFrameFailure, BarcodeFrameFailureCode

    sentinels = (
        "B25-BARCODE-PAYLOAD-CANARY-951753",
        "C:/Users/PrivacyCanary/secret-frame.jpg",
        "http://attacker.invalid:5173/B25-ORIGIN-CANARY",
        "B25-ANALYZER-EXCEPTION-CANARY-864209",
    )
    payload, local_path, hostile_origin, exception_message = sentinels

    def analyzer(*args, **kwargs):
        raise BarcodeFrameFailure(
            BarcodeFrameFailureCode.INVALID_IMAGE,
            "unsupported-input",
            exception_message,
        )

    def resource_probe(**kwargs):
        return {
            "schema_version": payload,
            "policy_version": local_path,
            "elapsed_ms": 1.0,
            "process_rss_bytes": 123,
            "host_available_memory_bytes": 456,
            "in_flight": 99,
            "max_in_flight": 99,
            "gpu": {"status": "unavailable", "name": hostile_origin},
            "exception": exception_message,
            "payload": payload,
            "path": local_path,
            "origin": hostile_origin,
        }

    monkeypatch.chdir(tmp_path)
    caplog.set_level(logging.DEBUG)
    with TestClient(
        create_app(analyzer=analyzer, resource_probe=resource_probe),
        base_url="http://127.0.0.1:8000",
    ) as client:
        host_rejected = client.get(
            "/v1/system/resources",
            headers={"Host": "attacker.invalid:8000"},
        )
        origin_rejected = client.post(
            "/v1/barcode/analyze",
            content=f"{payload}|{local_path}".encode(),
            headers={"Content-Type": "image/png", "Origin": hostile_origin},
        )
        analyzer_failed = client.post(
            "/v1/barcode/analyze",
            content=_png_bytes(),
            headers={"Content-Type": "image/png"},
        )
        resources = client.get("/v1/system/resources")

    assert host_rejected.status_code == 403
    assert origin_rejected.status_code == 403
    assert analyzer_failed.status_code == 400
    assert resources.status_code == 200
    assert resources.json()["schema_version"] == "live-resource-observation-v1"
    assert resources.json()["policy_version"] == "live-resource-policy-v1"
    assert resources.json()["in_flight"] == 0
    assert resources.json()["max_in_flight"] == 1
    assert resources.json()["gpu"] == {"status": "unavailable"}

    captured = capsys.readouterr()
    surfaces = "\n".join(
        (
            host_rejected.text,
            origin_rejected.text,
            analyzer_failed.text,
            resources.text,
            repr(host_rejected.json()),
            repr(origin_rejected.json()),
            repr(analyzer_failed.json()),
            repr(resources.json()),
            caplog.text,
            captured.out,
            captured.err,
        )
    )
    for sentinel in sentinels:
        assert sentinel not in surfaces

    assert list(tmp_path.iterdir()) == []


def test_multipart_frame_never_rolls_to_disk_and_closes_parser_scratch(
    monkeypatch,
) -> None:
    import starlette.formparsers as formparsers
    from physical_vision_api import create_app

    created = []
    real_spooled_temporary_file = formparsers.SpooledTemporaryFile

    def tracked_spooled_temporary_file(*args, **kwargs):
        scratch = real_spooled_temporary_file(*args, **kwargs)
        created.append(scratch)
        return scratch

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", tracked_spooled_temporary_file)
    sentinel = b"B25-MULTIPART-SHADOW-COPY-CANARY" + (b"x" * 1_100_000)
    with TestClient(create_app(), base_url="http://127.0.0.1:8000") as client:
        response = client.post(
            "/v1/barcode/analyze",
            files={"image": ("frame.png", sentinel, "image/png")},
        )

    assert response.status_code == 400
    assert created
    assert all(not scratch._rolled for scratch in created)
    assert all(scratch.closed for scratch in created)
    assert "B25-MULTIPART-SHADOW-COPY-CANARY" not in response.text
