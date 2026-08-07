from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from time import monotonic
from typing import Any, Protocol

import numpy as np
from physical_vision_geometry import ExtractedRoi, NormalizedBox
from physical_vision_image import CanonicalImage
from physical_vision_localization import (
    DEFAULT_LOCALIZATION_CONFIG,
    LocalizationConfig,
    LocalizationFailure,
    LocalizationResult,
    ProposalKind,
    ProposalPresence,
    propose_classical_regions,
)
from PIL import Image

_RECIPE_VERSION = "barcode-frame-analyze-v1"
_LOCALIZATION_RECIPE = "classical-localization-recipe-v1"


class BarcodeFrameFailureCode(str, Enum):
    CONFIG_VERSION_UNSUPPORTED = "CONFIG_VERSION_UNSUPPORTED"
    IMAGE_BUDGET_EXCEEDED = "IMAGE_BUDGET_EXCEEDED"
    INVALID_IMAGE = "INVALID_IMAGE"
    ANALYZE_BUDGET_EXCEEDED = "ANALYZE_BUDGET_EXCEEDED"


class BarcodeFrameFailure(ValueError):
    def __init__(self, code: BarcodeFrameFailureCode, category: str, message_key: str) -> None:
        super().__init__(message_key)
        self.code = code
        self.category = category
        self.message_key = message_key


class BarcodeCountStatus(str, Enum):
    NONE = "none"
    ONE = "one"
    MULTIPLE = "multiple"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class BarcodeFrameConfig:
    version: str
    max_image_pixels: int
    max_analyze_seconds: float
    localization_config_version: str

    def validate(self) -> None:
        if type(self) is not BarcodeFrameConfig:
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "BARCODE_FRAME_CONFIG_TYPE_UNSUPPORTED",
            )
        if type(self.version) is not str or self.version != _RECIPE_VERSION:
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "BARCODE_FRAME_CONFIG_VERSION_UNSUPPORTED",
            )
        if (
            type(self.localization_config_version) is not str
            or self.localization_config_version != _LOCALIZATION_RECIPE
        ):
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "BARCODE_FRAME_CONFIG_LOCALIZATION_UNSUPPORTED",
            )
        if type(self.max_image_pixels) is not int or self.max_image_pixels <= 0:
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "BARCODE_FRAME_CONFIG_INVALID",
            )
        if (
            type(self.max_analyze_seconds) is not float
            or not isfinite(self.max_analyze_seconds)
            or self.max_analyze_seconds <= 0.0
        ):
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "BARCODE_FRAME_CONFIG_INVALID",
            )


DEFAULT_BARCODE_FRAME_CONFIG = BarcodeFrameConfig(
    version=_RECIPE_VERSION,
    max_image_pixels=DEFAULT_LOCALIZATION_CONFIG.max_image_pixels,
    max_analyze_seconds=2.0,
    localization_config_version=_LOCALIZATION_RECIPE,
)


@dataclass(frozen=True, slots=True)
class BarcodeFrameEvidence:
    """Immutable barcode-frame evidence for live framing.

    Must not carry decoded payload, serial text, or raw barcode bytes.
    """

    count_status: BarcodeCountStatus
    barcode_box: NormalizedBox | None
    proposal_sources: tuple[str, ...]
    elapsed_ms: float
    recipe_version: str


class RegionProposer(Protocol):
    def __call__(
        self,
        image: Any,
        config: LocalizationConfig = ...,
        **kwargs: Any,
    ) -> LocalizationResult: ...


def _check_time_budget(
    config: BarcodeFrameConfig,
    started_at: float,
    deadline: float | None,
    cancelled: Callable[[], bool] | None,
    clock: Callable[[], float],
) -> None:
    if cancelled is not None and cancelled():
        raise BarcodeFrameFailure(
            BarcodeFrameFailureCode.ANALYZE_BUDGET_EXCEEDED,
            "timeout",
            "BARCODE_FRAME_CANCELLED",
        )
    now = clock()
    if deadline is not None and now > deadline:
        raise BarcodeFrameFailure(
            BarcodeFrameFailureCode.ANALYZE_BUDGET_EXCEEDED,
            "timeout",
            "BARCODE_FRAME_DEADLINE_EXCEEDED",
        )
    if now - started_at > config.max_analyze_seconds:
        raise BarcodeFrameFailure(
            BarcodeFrameFailureCode.ANALYZE_BUDGET_EXCEEDED,
            "timeout",
            "BARCODE_FRAME_TIME_BUDGET_EXCEEDED",
        )


def _rgb_array(
    image: ExtractedRoi | CanonicalImage | Image.Image | np.ndarray,
    config: BarcodeFrameConfig,
) -> np.ndarray:
    if isinstance(image, ExtractedRoi):
        array = image.to_rgb_array()
        height, width = array.shape[:2]
        if width * height > config.max_image_pixels:
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.IMAGE_BUDGET_EXCEEDED,
                "local-resource",
                "BARCODE_FRAME_IMAGE_BUDGET_EXCEEDED",
            )
        return array
    if isinstance(image, CanonicalImage):
        if image.mode != "RGB":
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.INVALID_IMAGE,
                "unsupported-input",
                "BARCODE_FRAME_IMAGE_MODE_UNSUPPORTED",
            )
        width, height = image.canonical_size
        if width * height > config.max_image_pixels:
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.IMAGE_BUDGET_EXCEEDED,
                "local-resource",
                "BARCODE_FRAME_IMAGE_BUDGET_EXCEEDED",
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
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.IMAGE_BUDGET_EXCEEDED,
                "local-resource",
                "BARCODE_FRAME_IMAGE_BUDGET_EXCEEDED",
            )
        return np.asarray(rgb, dtype=np.uint8).copy()
    if isinstance(image, np.ndarray):
        if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.INVALID_IMAGE,
                "unsupported-input",
                "BARCODE_FRAME_IMAGE_ARRAY_UNSUPPORTED",
            )
        height, width = image.shape[:2]
        if width * height > config.max_image_pixels:
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.IMAGE_BUDGET_EXCEEDED,
                "local-resource",
                "BARCODE_FRAME_IMAGE_BUDGET_EXCEEDED",
            )
        return np.ascontiguousarray(image.copy())
    raise BarcodeFrameFailure(
        BarcodeFrameFailureCode.INVALID_IMAGE,
        "unsupported-input",
        "BARCODE_FRAME_IMAGE_TYPE_UNSUPPORTED",
    )


def _localization_config(config: BarcodeFrameConfig) -> LocalizationConfig:
    base = DEFAULT_LOCALIZATION_CONFIG
    return LocalizationConfig(
        version=base.version,
        max_image_pixels=min(base.max_image_pixels, config.max_image_pixels),
        max_proposals=base.max_proposals,
        min_barcode_area_normalized=base.min_barcode_area_normalized,
        min_label_area_normalized=base.min_label_area_normalized,
        min_barcode_aspect_ratio=base.min_barcode_aspect_ratio,
        max_barcode_aspect_ratio=base.max_barcode_aspect_ratio,
        barcode_gradient_threshold=base.barcode_gradient_threshold,
        morphology_kernel_width=base.morphology_kernel_width,
        morphology_kernel_height=base.morphology_kernel_height,
        max_propose_seconds=min(base.max_propose_seconds, config.max_analyze_seconds),
    )


def _map_localization_failure(exc: LocalizationFailure) -> BarcodeFrameFailure:
    code_name = exc.code.name if hasattr(exc.code, "name") else str(exc.code)
    if "BUDGET" in code_name and "IMAGE" in code_name:
        return BarcodeFrameFailure(
            BarcodeFrameFailureCode.IMAGE_BUDGET_EXCEEDED,
            exc.category,
            "BARCODE_FRAME_IMAGE_BUDGET_EXCEEDED",
        )
    if "BUDGET" in code_name or "CANCEL" in (exc.message_key or ""):
        return BarcodeFrameFailure(
            BarcodeFrameFailureCode.ANALYZE_BUDGET_EXCEEDED,
            exc.category,
            "BARCODE_FRAME_ANALYZE_BUDGET_EXCEEDED",
        )
    if "CONFIG" in code_name:
        return BarcodeFrameFailure(
            BarcodeFrameFailureCode.CONFIG_VERSION_UNSUPPORTED,
            exc.category,
            "BARCODE_FRAME_CONFIG_INVALID",
        )
    return BarcodeFrameFailure(
        BarcodeFrameFailureCode.INVALID_IMAGE,
        exc.category,
        "BARCODE_FRAME_INVALID_IMAGE",
    )


def analyze_barcode_frame(
    image: ExtractedRoi | CanonicalImage | Image.Image | np.ndarray,
    config: BarcodeFrameConfig = DEFAULT_BARCODE_FRAME_CONFIG,
    *,
    propose_regions: RegionProposer | None = None,
    barcode_detector: Any | None = None,
    deadline: float | None = None,
    cancelled: Callable[[], bool] | None = None,
    clock: Callable[[], float] = monotonic,
) -> BarcodeFrameEvidence:
    """Analyze a frame for 1D barcode count/geometry only (decode off).

    Composes Stage 5 ``propose_classical_regions`` and filters to
    ``barcode_landmark`` proposals. Zero → none, one → one + box, two+ →
    multiple with box=None (no pick-largest). Detector payload strings are never
    admitted onto evidence.
    """
    config.validate()
    started_at = clock()
    _check_time_budget(config, started_at, deadline, cancelled, clock)
    array = _rgb_array(image, config)
    _check_time_budget(config, started_at, deadline, cancelled, clock)

    loc_config = _localization_config(config)
    proposer = propose_regions if propose_regions is not None else propose_classical_regions
    try:
        loc_result = proposer(
            array,
            loc_config,
            barcode_detector=barcode_detector,
            deadline=deadline,
            cancelled=cancelled,
            clock=clock,
        )
    except LocalizationFailure as exc:
        raise _map_localization_failure(exc) from exc
    except TypeError:
        # Injected proposers may use a simpler signature.
        try:
            loc_result = proposer(array, loc_config)  # type: ignore[misc]
        except LocalizationFailure as exc:
            raise _map_localization_failure(exc) from exc

    if type(loc_result) is not LocalizationResult:
        raise BarcodeFrameFailure(
            BarcodeFrameFailureCode.INVALID_IMAGE,
            "unsupported-input",
            "BARCODE_FRAME_INVALID_PROPOSER_RESULT",
        )

    barcodes = [
        p
        for p in loc_result.proposals
        if p.kind is ProposalKind.BARCODE_LANDMARK
        and p.presence is ProposalPresence.PRESENT
        and p.box is not None
    ]
    sources = tuple(dict.fromkeys(p.source for p in barcodes if type(p.source) is str))

    if len(barcodes) == 0:
        status = BarcodeCountStatus.NONE
        box: NormalizedBox | None = None
    elif len(barcodes) == 1:
        status = BarcodeCountStatus.ONE
        box = barcodes[0].box
    else:
        status = BarcodeCountStatus.MULTIPLE
        box = None

    _check_time_budget(config, started_at, deadline, cancelled, clock)
    elapsed_ms = (clock() - started_at) * 1000.0
    return BarcodeFrameEvidence(
        count_status=status,
        barcode_box=box,
        proposal_sources=sources,
        elapsed_ms=float(elapsed_ms),
        recipe_version=config.version,
    )


__all__ = [
    "DEFAULT_BARCODE_FRAME_CONFIG",
    "BarcodeCountStatus",
    "BarcodeFrameConfig",
    "BarcodeFrameEvidence",
    "BarcodeFrameFailure",
    "BarcodeFrameFailureCode",
    "RegionProposer",
    "analyze_barcode_frame",
]
