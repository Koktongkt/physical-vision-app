from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from time import monotonic
from typing import Any, Protocol

import numpy as np
from physical_vision_geometry import ExtractedRoi
from physical_vision_image import CanonicalImage
from PIL import Image


class OcrFailureCode(str, Enum):
    CONFIG_VERSION_UNSUPPORTED = "CONFIG_VERSION_UNSUPPORTED"
    IMAGE_BUDGET_EXCEEDED = "IMAGE_BUDGET_EXCEEDED"
    INVALID_IMAGE = "INVALID_IMAGE"
    OCR_BUDGET_EXCEEDED = "OCR_BUDGET_EXCEEDED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    ENGINE_FAILURE = "ENGINE_FAILURE"


class OcrFailure(ValueError):
    def __init__(self, code: OcrFailureCode, category: str, message_key: str) -> None:
        super().__init__(message_key)
        self.code = code
        self.category = category
        self.message_key = message_key


class OcrUsability(str, Enum):
    """Heuristic baseline labels only — not calibrated confidence."""

    USABLE = "usable"
    UNREADABLE = "unreadable"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class OcrConfig:
    version: str
    language: str
    psm: int
    oem: int
    min_upscale_height: int
    max_image_pixels: int
    max_ocr_seconds: float

    def validate(self) -> None:
        if type(self) is not OcrConfig:
            raise OcrFailure(
                OcrFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "OCR_CONFIG_TYPE_UNSUPPORTED",
            )
        if type(self.version) is not str or self.version != "tesseract-ocr-baseline-v1":
            raise OcrFailure(
                OcrFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "OCR_CONFIG_VERSION_UNSUPPORTED",
            )
        if type(self.language) is not str or self.language != "eng":
            raise OcrFailure(
                OcrFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "OCR_CONFIG_LANGUAGE_UNSUPPORTED",
            )
        if type(self.psm) is not int or type(self.oem) is not int:
            raise OcrFailure(
                OcrFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "OCR_CONFIG_INVALID",
            )
        if self.psm not in {6, 7, 8, 13} or self.oem not in {0, 1, 2, 3}:
            raise OcrFailure(
                OcrFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "OCR_CONFIG_INVALID",
            )
        if (
            type(self.min_upscale_height) is not int
            or self.min_upscale_height <= 0
            or type(self.max_image_pixels) is not int
            or self.max_image_pixels <= 0
            or type(self.max_ocr_seconds) is not float
            or not isfinite(self.max_ocr_seconds)
            or self.max_ocr_seconds <= 0.0
        ):
            raise OcrFailure(
                OcrFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "OCR_CONFIG_INVALID",
            )


DEFAULT_OCR_CONFIG = OcrConfig(
    version="tesseract-ocr-baseline-v1",
    language="eng",
    psm=7,  # treat image as a single text line
    oem=3,  # default engine mode
    min_upscale_height=48,
    max_image_pixels=16_000_000,
    max_ocr_seconds=5.0,
)


@dataclass(frozen=True, slots=True)
class OcrEvidence:
    """Immutable OCR evidence. ``raw_string`` is verbatim engine output — no repair.

    Serial-like ``raw_string`` / ``displayed_string`` are omitted from default ``repr``
    so accidental logging cannot leak OCR payloads (same hygiene as B06/B07 pixel bytes).
    """

    usability: OcrUsability
    recipe_version: str
    engine_name: str
    engine_version: str | None
    language: str
    psm: int
    oem: int
    elapsed_ms: float
    raw_string: str = field(repr=False)
    displayed_string: str = field(repr=False)
    # Heuristic only; never a calibrated confidence claim.
    notes: tuple[str, ...] = ()


class OcrEngine(Protocol):
    def run(self, image: np.ndarray, config: OcrConfig) -> str: ...


def _check_time_budget(
    config: OcrConfig,
    started_at: float,
    deadline: float | None,
    cancelled: Callable[[], bool] | None,
    clock: Callable[[], float],
) -> None:
    if cancelled is not None and cancelled():
        raise OcrFailure(
            OcrFailureCode.OCR_BUDGET_EXCEEDED,
            "timeout",
            "OCR_CANCELLED",
        )
    now = clock()
    if deadline is not None and now > deadline:
        raise OcrFailure(
            OcrFailureCode.OCR_BUDGET_EXCEEDED,
            "timeout",
            "OCR_DEADLINE_EXCEEDED",
        )
    if now - started_at > config.max_ocr_seconds:
        raise OcrFailure(
            OcrFailureCode.OCR_BUDGET_EXCEEDED,
            "timeout",
            "OCR_TIME_BUDGET_EXCEEDED",
        )


def _roi_rgb_array(
    image: ExtractedRoi | CanonicalImage | Image.Image | np.ndarray,
    config: OcrConfig,
) -> np.ndarray:
    if isinstance(image, ExtractedRoi):
        array = image.to_rgb_array()
        height, width = array.shape[:2]
        if width * height > config.max_image_pixels:
            raise OcrFailure(
                OcrFailureCode.IMAGE_BUDGET_EXCEEDED,
                "local-resource",
                "OCR_IMAGE_BUDGET_EXCEEDED",
            )
        return array
    if isinstance(image, CanonicalImage):
        if image.mode != "RGB":
            raise OcrFailure(
                OcrFailureCode.INVALID_IMAGE,
                "unsupported-input",
                "OCR_IMAGE_MODE_UNSUPPORTED",
            )
        width, height = image.canonical_size
        if width * height > config.max_image_pixels:
            raise OcrFailure(
                OcrFailureCode.IMAGE_BUDGET_EXCEEDED,
                "local-resource",
                "OCR_IMAGE_BUDGET_EXCEEDED",
            )
        return (
            np.frombuffer(image.to_pillow().tobytes(), dtype=np.uint8)
            .reshape(height, width, 3)
            .copy()
        )
    if isinstance(image, Image.Image):
        rgb = image.convert("RGB")
        width, height = rgb.size
        if width * height > config.max_image_pixels:
            raise OcrFailure(
                OcrFailureCode.IMAGE_BUDGET_EXCEEDED,
                "local-resource",
                "OCR_IMAGE_BUDGET_EXCEEDED",
            )
        return np.asarray(rgb, dtype=np.uint8).copy()
    if isinstance(image, np.ndarray):
        if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
            raise OcrFailure(
                OcrFailureCode.INVALID_IMAGE,
                "unsupported-input",
                "OCR_IMAGE_ARRAY_UNSUPPORTED",
            )
        height, width = image.shape[:2]
        if width * height > config.max_image_pixels:
            raise OcrFailure(
                OcrFailureCode.IMAGE_BUDGET_EXCEEDED,
                "local-resource",
                "OCR_IMAGE_BUDGET_EXCEEDED",
            )
        return np.ascontiguousarray(image.copy())
    raise OcrFailure(
        OcrFailureCode.INVALID_IMAGE,
        "unsupported-input",
        "OCR_IMAGE_TYPE_UNSUPPORTED",
    )


def _prepare_for_ocr(array: np.ndarray, config: OcrConfig) -> np.ndarray:
    """Optional upscale only — no binarization that could alter character identity claims."""
    height, width = array.shape[:2]
    if height >= config.min_upscale_height:
        return array
    scale = max(2, int(np.ceil(config.min_upscale_height / max(height, 1))))
    new_w = max(1, width * scale)
    new_h = max(1, height * scale)
    if new_w * new_h > config.max_image_pixels:
        return array
    image = Image.fromarray(array, mode="RGB")
    scaled = image.resize((new_w, new_h), Image.Resampling.NEAREST)
    return np.asarray(scaled, dtype=np.uint8).copy()


def _classify_usability(raw: str) -> OcrUsability:
    if "\n" in raw.rstrip("\n") or "\r" in raw:
        # Multiple lines retained verbatim → ambiguous for single-line baseline policy.
        non_empty_lines = [line for line in raw.replace("\r\n", "\n").split("\n") if line.strip()]
        if len(non_empty_lines) > 1:
            return OcrUsability.AMBIGUOUS
    stripped = raw.strip()
    if stripped == "":
        return OcrUsability.UNREADABLE
    return OcrUsability.USABLE


def _default_tesseract_engine_run(image: np.ndarray, config: OcrConfig) -> str:
    """Invoke system Tesseract via pytesseract. Payload/errors stay content-free at boundary."""
    try:
        import pytesseract
        from pytesseract import TesseractError, TesseractNotFoundError
    except ImportError as exc:
        raise OcrFailure(
            OcrFailureCode.DEPENDENCY_UNAVAILABLE,
            "dependency",
            "OCR_TESSERACT_UNAVAILABLE",
        ) from exc

    pil = Image.fromarray(image, mode="RGB")
    tess_config = f"--oem {config.oem} --psm {config.psm}"
    try:
        # verbatim=False is the default; we still do not post-process the string.
        text = pytesseract.image_to_string(pil, lang=config.language, config=tess_config)
    except TesseractNotFoundError as exc:
        raise OcrFailure(
            OcrFailureCode.DEPENDENCY_UNAVAILABLE,
            "dependency",
            "OCR_TESSERACT_UNAVAILABLE",
        ) from exc
    except TesseractError as exc:
        raise OcrFailure(
            OcrFailureCode.ENGINE_FAILURE,
            "dependency",
            "OCR_TESSERACT_ENGINE_FAILURE",
        ) from exc
    except OSError as exc:
        raise OcrFailure(
            OcrFailureCode.DEPENDENCY_UNAVAILABLE,
            "dependency",
            "OCR_TESSERACT_UNAVAILABLE",
        ) from exc
    if type(text) is not str:
        raise OcrFailure(
            OcrFailureCode.ENGINE_FAILURE,
            "dependency",
            "OCR_TESSERACT_ENGINE_FAILURE",
        )
    return text


def _resolve_engine_version() -> str | None:
    try:
        import pytesseract

        version = pytesseract.get_tesseract_version()
        return str(version)
    except Exception:
        return None


class _DefaultTesseractEngine:
    def run(self, image: np.ndarray, config: OcrConfig) -> str:
        return _default_tesseract_engine_run(image, config)


def run_tesseract_baseline(
    image: ExtractedRoi | CanonicalImage | Image.Image | np.ndarray,
    config: OcrConfig = DEFAULT_OCR_CONFIG,
    *,
    engine: Any | None = None,
    deadline: float | None = None,
    cancelled: Callable[[], bool] | None = None,
    clock: Callable[[], float] = monotonic,
) -> OcrEvidence:
    """Run the Tesseract single-line OCR baseline on a detached ROI image.

    Returns verbatim engine text with no format repair, checksum fix, case folding,
    or silent character substitution. Missing Tesseract yields ``DEPENDENCY_UNAVAILABLE``.
    """
    config.validate()
    started_at = clock()
    _check_time_budget(config, started_at, deadline, cancelled, clock)
    array = _roi_rgb_array(image, config)
    prepared = _prepare_for_ocr(array, config)
    _check_time_budget(config, started_at, deadline, cancelled, clock)

    active_engine: Any = engine if engine is not None else _DefaultTesseractEngine()
    try:
        raw = active_engine.run(prepared, config)
    except OcrFailure:
        raise
    except Exception as exc:
        # Do not leak exception content (may include paths).
        raise OcrFailure(
            OcrFailureCode.ENGINE_FAILURE,
            "dependency",
            "OCR_ENGINE_FAILURE",
        ) from exc

    if type(raw) is not str:
        raise OcrFailure(
            OcrFailureCode.ENGINE_FAILURE,
            "dependency",
            "OCR_ENGINE_NON_STRING",
        )

    _check_time_budget(config, started_at, deadline, cancelled, clock)
    usability = _classify_usability(raw)
    # displayed_string is a pure presentation copy identical to raw for this baseline.
    displayed = raw
    elapsed_ms = (clock() - started_at) * 1000.0
    engine_version = None
    if engine is None:
        engine_version = _resolve_engine_version()
    return OcrEvidence(
        usability=usability,
        recipe_version=config.version,
        engine_name="tesseract",
        engine_version=engine_version,
        language=config.language,
        psm=config.psm,
        oem=config.oem,
        elapsed_ms=float(elapsed_ms),
        raw_string=raw,
        displayed_string=displayed,
        notes=("usability_heuristic_uncalibrated",),
    )


__all__ = [
    "DEFAULT_OCR_CONFIG",
    "OcrConfig",
    "OcrEvidence",
    "OcrFailure",
    "OcrFailureCode",
    "OcrUsability",
    "run_tesseract_baseline",
]
