from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from time import monotonic
from typing import Any, Protocol

import numpy as np
from physical_vision_geometry import ExtractedRoi, NormalizedBox, measure_raw_quality
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

_RECIPE_VERSION = "barcode-frame-ready-v1"
_LOCALIZATION_RECIPE = "classical-localization-recipe-v1"

# Fixed VT gate priority (first failing wins dominant action). Documented as VT seeds.
_DEFAULT_GATE_PRIORITY: tuple[str, ...] = (
    "min_area",
    "min_short_side_px",
    "margin_left",
    "margin_right",
    "margin_top",
    "margin_bottom",
    "blur",
    "aspect",
    "exposure",
)


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


class BarcodeReadiness(str, Enum):
    ABSTAIN = "abstain"
    GUIDANCE = "guidance"
    READY = "ready"


class BarcodeGuidanceAction(str, Enum):
    NONE = "none"
    CAMERA_CLOSER = "camera_closer"
    CAMERA_FARTHER = "camera_farther"
    CAMERA_LEFT = "camera_left"
    CAMERA_RIGHT = "camera_right"
    CAMERA_UP = "camera_up"
    CAMERA_DOWN = "camera_down"
    CAMERA_STEADY = "camera_steady"
    REDUCE_GLARE = "reduce_glare"


@dataclass(frozen=True, slots=True)
class BarcodeQualityMetrics:
    """Content-free quality scalars for a single barcode box (no image bytes)."""

    area_normalized: float
    short_side_px: float
    margin_left: float
    margin_right: float
    margin_top: float
    margin_bottom: float
    laplacian_variance: float
    aspect_ratio: float
    exposure_mean: float


@dataclass(frozen=True, slots=True)
class BarcodeFrameConfig:
    version: str
    max_image_pixels: int
    max_analyze_seconds: float
    localization_config_version: str
    min_area_normalized: float
    min_short_side_px: int
    margin_frac: float
    min_laplacian_variance: float
    min_aspect_ratio: float
    max_aspect_ratio: float
    exposure_high: float
    exposure_low: float
    gate_priority: tuple[str, ...]

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
        if type(self.min_short_side_px) is not int or self.min_short_side_px < 0:
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "BARCODE_FRAME_CONFIG_INVALID",
            )
        floats = (
            self.min_area_normalized,
            self.margin_frac,
            self.min_laplacian_variance,
            self.min_aspect_ratio,
            self.max_aspect_ratio,
            self.exposure_high,
            self.exposure_low,
        )
        if any(type(value) is not float or not isfinite(value) for value in floats):
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "BARCODE_FRAME_CONFIG_INVALID",
            )
        if not (
            0.0 < self.min_area_normalized < 1.0
            and 0.0 <= self.margin_frac < 0.5
            and self.min_laplacian_variance >= 0.0
            and 0.0 < self.min_aspect_ratio < self.max_aspect_ratio
            and 0.0 <= self.exposure_low < self.exposure_high <= 255.0
        ):
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "BARCODE_FRAME_CONFIG_INVALID",
            )
        if not isinstance(self.gate_priority, tuple) or not self.gate_priority:
            raise BarcodeFrameFailure(
                BarcodeFrameFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "BARCODE_FRAME_CONFIG_INVALID",
            )
        if any(type(item) is not str or not item for item in self.gate_priority):
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
    # VT seeds (spec §0.2.2) — not calibrated production thresholds.
    min_area_normalized=DEFAULT_LOCALIZATION_CONFIG.min_barcode_area_normalized,
    min_short_side_px=48,
    margin_frac=0.04,
    min_laplacian_variance=50.0,
    min_aspect_ratio=DEFAULT_LOCALIZATION_CONFIG.min_barcode_aspect_ratio,
    max_aspect_ratio=DEFAULT_LOCALIZATION_CONFIG.max_barcode_aspect_ratio,
    exposure_high=245.0,
    exposure_low=12.0,
    gate_priority=_DEFAULT_GATE_PRIORITY,
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
    readiness: BarcodeReadiness
    guidance_action: BarcodeGuidanceAction
    failing_gates: tuple[str, ...]
    quality: BarcodeQualityMetrics | None


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


def _measure_quality(array: np.ndarray, box: NormalizedBox) -> BarcodeQualityMetrics:
    height, width = array.shape[:2]
    x0, y0, x1, y1 = box.to_pixel_bounds((width, height))
    short_side_px = float(min(x1 - x0, y1 - y0))
    width_n = box.width()
    height_n = box.height()
    aspect = width_n / height_n if height_n > 0.0 else float("inf")
    raw = measure_raw_quality(array, box)
    lap = float(raw.blur.value) if raw.blur.value is not None else 0.0
    exposure = float(raw.exposure.value) if raw.exposure.value is not None else 0.0
    return BarcodeQualityMetrics(
        area_normalized=float(box.area()),
        short_side_px=short_side_px,
        margin_left=float(box.x0),
        margin_right=float(1.0 - box.x1),
        margin_top=float(box.y0),
        margin_bottom=float(1.0 - box.y1),
        laplacian_variance=lap,
        aspect_ratio=float(aspect),
        exposure_mean=exposure,
    )


def _gate_failures(
    quality: BarcodeQualityMetrics,
    config: BarcodeFrameConfig,
) -> list[str]:
    failed: list[str] = []
    if quality.area_normalized < config.min_area_normalized:
        failed.append("min_area")
    if quality.short_side_px < float(config.min_short_side_px):
        failed.append("min_short_side_px")
    if quality.margin_left < config.margin_frac:
        failed.append("margin_left")
    if quality.margin_right < config.margin_frac:
        failed.append("margin_right")
    if quality.margin_top < config.margin_frac:
        failed.append("margin_top")
    if quality.margin_bottom < config.margin_frac:
        failed.append("margin_bottom")
    if quality.laplacian_variance < config.min_laplacian_variance:
        failed.append("blur")
    if (
        quality.aspect_ratio < config.min_aspect_ratio
        or quality.aspect_ratio > config.max_aspect_ratio
    ):
        failed.append("aspect")
    if (
        quality.exposure_mean >= config.exposure_high
        or quality.exposure_mean <= config.exposure_low
    ):
        failed.append("exposure")
    return failed


def _action_for_gate(
    gate_id: str,
    quality: BarcodeQualityMetrics,
    config: BarcodeFrameConfig,
) -> BarcodeGuidanceAction:
    if gate_id == "min_area" or gate_id == "min_short_side_px":
        return BarcodeGuidanceAction.CAMERA_CLOSER
    if gate_id == "margin_left":
        # Camera-referent: left-clipped → move camera right (table §card).
        return BarcodeGuidanceAction.CAMERA_RIGHT
    if gate_id == "margin_right":
        return BarcodeGuidanceAction.CAMERA_LEFT
    if gate_id == "margin_top":
        return BarcodeGuidanceAction.CAMERA_DOWN
    if gate_id == "margin_bottom":
        return BarcodeGuidanceAction.CAMERA_UP
    if gate_id == "blur":
        return BarcodeGuidanceAction.CAMERA_STEADY
    if gate_id == "aspect":
        # Deterministic: too thin/tall (low aspect) → closer; too wide → farther.
        if quality.aspect_ratio < config.min_aspect_ratio:
            return BarcodeGuidanceAction.CAMERA_CLOSER
        return BarcodeGuidanceAction.CAMERA_FARTHER
    if gate_id == "exposure":
        if quality.exposure_mean >= config.exposure_high:
            return BarcodeGuidanceAction.REDUCE_GLARE
        return BarcodeGuidanceAction.CAMERA_STEADY
    return BarcodeGuidanceAction.CAMERA_STEADY


def _order_failing_gates(
    failed: Sequence[str],
    priority: Sequence[str],
) -> tuple[str, ...]:
    failed_set = set(failed)
    ordered = [gate for gate in priority if gate in failed_set]
    # Any unexpected gate ids append after configured priority (stable).
    extras = [gate for gate in failed if gate not in priority]
    return tuple(ordered + extras)


def _evaluate_readiness(
    count_status: BarcodeCountStatus,
    box: NormalizedBox | None,
    array: np.ndarray,
    config: BarcodeFrameConfig,
) -> tuple[
    BarcodeReadiness,
    BarcodeGuidanceAction,
    tuple[str, ...],
    BarcodeQualityMetrics | None,
]:
    if count_status is not BarcodeCountStatus.ONE or box is None:
        return (
            BarcodeReadiness.ABSTAIN,
            BarcodeGuidanceAction.NONE,
            (),
            None,
        )

    quality = _measure_quality(array, box)
    failed = _gate_failures(quality, config)
    if not failed:
        return (
            BarcodeReadiness.READY,
            BarcodeGuidanceAction.NONE,
            (),
            quality,
        )

    ordered = _order_failing_gates(failed, config.gate_priority)
    dominant = ordered[0]
    action = _action_for_gate(dominant, quality, config)
    return (
        BarcodeReadiness.GUIDANCE,
        action,
        ordered,
        quality,
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
    """Analyze a frame for 1D barcode count/geometry and ready/guidance (decode off).

    Composes Stage 5 ``propose_classical_regions`` and filters to
    ``barcode_landmark`` proposals. Zero → none/abstain, one → gates →
    ready|guidance, two+ → multiple/abstain with box=None (no pick-largest).
    Detector payload strings are never admitted onto evidence.
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

    readiness, action, failing, quality = _evaluate_readiness(status, box, array, config)

    _check_time_budget(config, started_at, deadline, cancelled, clock)
    elapsed_ms = (clock() - started_at) * 1000.0
    return BarcodeFrameEvidence(
        count_status=status,
        barcode_box=box,
        proposal_sources=sources,
        elapsed_ms=float(elapsed_ms),
        recipe_version=config.version,
        readiness=readiness,
        guidance_action=action,
        failing_gates=failing,
        quality=quality,
    )


__all__ = [
    "DEFAULT_BARCODE_FRAME_CONFIG",
    "BarcodeCountStatus",
    "BarcodeFrameConfig",
    "BarcodeFrameEvidence",
    "BarcodeFrameFailure",
    "BarcodeFrameFailureCode",
    "BarcodeGuidanceAction",
    "BarcodeQualityMetrics",
    "BarcodeReadiness",
    "RegionProposer",
    "analyze_barcode_frame",
]
