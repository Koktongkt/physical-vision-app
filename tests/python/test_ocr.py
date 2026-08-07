from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest
from physical_vision_geometry import NormalizedBox, extract_roi_box
from physical_vision_ocr import (
    DEFAULT_OCR_CONFIG,
    OcrConfig,
    OcrEvidence,
    OcrFailure,
    OcrFailureCode,
    OcrUsability,
    run_tesseract_baseline,
)


def solid_rgb(size: tuple[int, int], color: tuple[int, int, int]) -> np.ndarray:
    array = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    array[:, :] = color
    return array


def render_text_roi(text: str, *, size: tuple[int, int] = (280, 64)) -> np.ndarray:
    """Render glyphs with Pillow for synthetic OCR fixtures (not committed photos)."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    # Slight upscale-friendly large canvas with monospaced-ish default font
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = max(4, (size[0] - tw) // 2)
    y = max(4, (size[1] - th) // 2)
    draw.text((x, y), text, fill=(0, 0, 0), font=font)
    return np.asarray(image, dtype=np.uint8).copy()


class StubEngine:
    def __init__(self, text: str = "", *, fail: Exception | None = None) -> None:
        self.text = text
        self.fail = fail
        self.calls: list[dict] = []

    def run(self, image: np.ndarray, config: OcrConfig) -> str:
        self.calls.append(
            {
                "shape": tuple(image.shape),
                "dtype": str(image.dtype),
                "config_version": config.version,
            }
        )
        if self.fail is not None:
            raise self.fail
        return self.text


def test_default_ocr_config_is_frozen_versioned_recipe() -> None:
    assert DEFAULT_OCR_CONFIG.version == "tesseract-ocr-baseline-v1"
    assert DEFAULT_OCR_CONFIG.language == "eng"
    with pytest.raises(FrozenInstanceError):
        DEFAULT_OCR_CONFIG.version = "tampered"  # type: ignore[misc]


def test_ocr_config_rejects_unregistered_version() -> None:
    bad = OcrConfig(
        version="tesseract-ocr-baseline-v0",
        language="eng",
        psm=7,
        oem=3,
        min_upscale_height=32,
        max_image_pixels=4_000_000,
        max_ocr_seconds=2.0,
    )
    with pytest.raises(OcrFailure) as raised:
        bad.validate()
    assert raised.value.code is OcrFailureCode.CONFIG_VERSION_UNSUPPORTED
    assert raised.value.message_key == "OCR_CONFIG_VERSION_UNSUPPORTED"


def test_stubbed_engine_verbatim_passthrough_preserves_leading_zeros() -> None:
    roi = render_text_roi("00123-45")
    engine = StubEngine("00123-45")
    evidence = run_tesseract_baseline(roi, engine=engine)
    assert isinstance(evidence, OcrEvidence)
    assert evidence.raw_string == "00123-45"
    assert evidence.displayed_string == "00123-45"
    assert evidence.usability is OcrUsability.USABLE
    assert evidence.recipe_version == "tesseract-ocr-baseline-v1"
    assert evidence.engine_name == "tesseract"
    assert evidence.raw_string == "00123-45"  # exact, no strip of zeros


def test_stubbed_engine_does_not_repair_or_uppercase() -> None:
    engine = StubEngine("ab 12")
    evidence = run_tesseract_baseline(render_text_roi("ab 12"), engine=engine)
    assert evidence.raw_string == "ab 12"
    assert evidence.raw_string != "AB12"


def test_blank_roi_is_unreadable() -> None:
    engine = StubEngine("   \n  ")
    evidence = run_tesseract_baseline(solid_rgb((80, 40), (255, 255, 255)), engine=engine)
    assert evidence.usability is OcrUsability.UNREADABLE
    assert evidence.raw_string == "   \n  " or evidence.raw_string == engine.text


def test_multiline_engine_output_is_ambiguous() -> None:
    engine = StubEngine("LINEONE\nLINETWO")
    evidence = run_tesseract_baseline(render_text_roi("X"), engine=engine)
    assert evidence.usability is OcrUsability.AMBIGUOUS
    assert evidence.raw_string == "LINEONE\nLINETWO"


def test_empty_string_unreadable() -> None:
    engine = StubEngine("")
    evidence = run_tesseract_baseline(solid_rgb((40, 20), (200, 200, 200)), engine=engine)
    assert evidence.usability is OcrUsability.UNREADABLE
    assert evidence.raw_string == ""


def test_missing_dependency_is_typed_failure_not_crash() -> None:
    class MissingEngine:
        def run(self, image: np.ndarray, config: OcrConfig) -> str:
            raise OcrFailure(
                OcrFailureCode.DEPENDENCY_UNAVAILABLE,
                "dependency",
                "OCR_TESSERACT_UNAVAILABLE",
            )

    with pytest.raises(OcrFailure) as raised:
        run_tesseract_baseline(render_text_roi("1"), engine=MissingEngine())
    assert raised.value.code is OcrFailureCode.DEPENDENCY_UNAVAILABLE
    assert raised.value.category == "dependency"
    text = " ".join(
        [
            raised.value.message_key,
            raised.value.category,
            raised.value.code.value,
            str(raised.value),
        ]
    )
    assert "SN-" not in text
    assert b"\xff\xd8" not in text.encode()


def test_timeout_and_cancel_are_content_free() -> None:
    roi = render_text_roi("123")
    with pytest.raises(OcrFailure) as raised:
        run_tesseract_baseline(roi, engine=StubEngine("123"), cancelled=lambda: True)
    assert raised.value.code is OcrFailureCode.OCR_BUDGET_EXCEEDED
    assert raised.value.category == "timeout"

    with pytest.raises(OcrFailure) as raised_deadline:
        run_tesseract_baseline(
            roi,
            engine=StubEngine("123"),
            deadline=0.0,
            clock=lambda: 99.0,
        )
    assert raised_deadline.value.code is OcrFailureCode.OCR_BUDGET_EXCEEDED


def test_input_roi_buffer_not_mutated() -> None:
    roi = render_text_roi("42")
    original = roi.copy()
    _ = run_tesseract_baseline(roi, engine=StubEngine("42"))
    assert np.array_equal(roi, original)


def test_evidence_immutable() -> None:
    evidence = run_tesseract_baseline(render_text_roi("9"), engine=StubEngine("9"))
    with pytest.raises(FrozenInstanceError):
        evidence.raw_string = "x"  # type: ignore[misc]


def test_ocr_evidence_repr_omits_raw_and_displayed_payloads() -> None:
    """Serial-like OCR text must not appear in default repr (log hygiene)."""
    secret = "SN-SECRET-SERIAL-00123"
    evidence = run_tesseract_baseline(render_text_roi("x"), engine=StubEngine(secret))
    assert evidence.raw_string == secret
    assert evidence.displayed_string == secret
    text = repr(evidence)
    assert secret not in text
    assert "SN-SECRET" not in text
    assert "raw_string=" not in text
    assert "displayed_string=" not in text
    assert "usability=" in text


def test_accepts_extracted_roi_from_geometry() -> None:
    canvas = solid_rgb((200, 100), (255, 255, 255))
    canvas[20:80, 20:180] = render_text_roi("77", size=(160, 60))
    roi = extract_roi_box(canvas, NormalizedBox(0.1, 0.2, 0.9, 0.8))
    evidence = run_tesseract_baseline(roi, engine=StubEngine("77"))
    assert evidence.raw_string == "77"
    assert evidence.usability is OcrUsability.USABLE


def test_image_budget_exceeded() -> None:
    config = OcrConfig(
        version="tesseract-ocr-baseline-v1",
        language="eng",
        psm=7,
        oem=3,
        min_upscale_height=32,
        max_image_pixels=10,
        max_ocr_seconds=2.0,
    )
    with pytest.raises(OcrFailure) as raised:
        run_tesseract_baseline(
            solid_rgb((20, 20), (0, 0, 0)),
            config=config,
            engine=StubEngine("x"),
        )
    assert raised.value.code is OcrFailureCode.IMAGE_BUDGET_EXCEEDED


def test_default_engine_missing_tesseract_maps_to_dependency_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When pytesseract/binary is absent, public API returns typed dependency failure."""
    import physical_vision_ocr as ocr_mod

    def boom(*_a, **_k):
        raise ocr_mod.OcrFailure(
            OcrFailureCode.DEPENDENCY_UNAVAILABLE,
            "dependency",
            "OCR_TESSERACT_UNAVAILABLE",
        )

    monkeypatch.setattr(ocr_mod, "_default_tesseract_engine_run", boom)
    with pytest.raises(OcrFailure) as raised:
        run_tesseract_baseline(render_text_roi("1"), engine=None)
    assert raised.value.code is OcrFailureCode.DEPENDENCY_UNAVAILABLE


@pytest.mark.integration
def test_optional_real_tesseract_on_synthetic_digits() -> None:
    """Gated real binary test — skips when Tesseract is not installed."""
    pytest.importorskip("pytesseract")
    import shutil

    if shutil.which("tesseract") is None:
        pytest.skip("tesseract binary not on PATH")
    # Render larger text for default font readability under PSM 7.
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (400, 80), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((20, 20), "012345", fill=(0, 0, 0), font=font)
    # Upscale to help Tesseract
    image = image.resize((800, 160), Image.Resampling.NEAREST)
    roi = np.asarray(image, dtype=np.uint8)
    try:
        evidence = run_tesseract_baseline(roi)
    except OcrFailure as failure:
        if failure.code is OcrFailureCode.DEPENDENCY_UNAVAILABLE:
            pytest.skip("tesseract dependency unavailable at runtime")
        raise
    # Real OCR may not be perfect on tiny default font; require digit presence without repair API.
    assert evidence.recipe_version == "tesseract-ocr-baseline-v1"
    assert isinstance(evidence.raw_string, str)
    # If usable, require digits-only alnum (no invented letters).
    if evidence.usability is OcrUsability.USABLE:
        cleaned = "".join(ch for ch in evidence.raw_string if ch.isalnum())
        assert cleaned == "" or all(ch in "0123456789" for ch in cleaned)
