from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from math import hypot, isfinite
from time import monotonic
from typing import Any

import cv2
import numpy as np
from physical_vision_image import CanonicalImage, OrientationTransform
from PIL import Image


class GeometryFailureCode(str, Enum):
    CONFIG_VERSION_UNSUPPORTED = "CONFIG_VERSION_UNSUPPORTED"
    COORDINATE_OUT_OF_RANGE = "COORDINATE_OUT_OF_RANGE"
    INVALID_GEOMETRY = "INVALID_GEOMETRY"
    IMAGE_BUDGET_EXCEEDED = "IMAGE_BUDGET_EXCEEDED"
    ROI_BUDGET_EXCEEDED = "ROI_BUDGET_EXCEEDED"
    HOMOGRAPHY_ILL_CONDITIONED = "HOMOGRAPHY_ILL_CONDITIONED"
    QUAD_DEGENERATE = "QUAD_DEGENERATE"
    QUAD_OUT_OF_BOUNDS = "QUAD_OUT_OF_BOUNDS"
    MEASURE_BUDGET_EXCEEDED = "MEASURE_BUDGET_EXCEEDED"


class GeometryFailure(ValueError):
    def __init__(self, code: GeometryFailureCode, category: str, message_key: str) -> None:
        super().__init__(message_key)
        self.code = code
        self.category = category
        self.message_key = message_key


@dataclass(frozen=True, slots=True)
class GeometryConfig:
    version: str
    measurement_recipe_version: str
    max_image_pixels: int
    max_roi_pixels: int
    max_homography_condition_number: float
    min_quad_area_normalized: float
    edge_contact_threshold_normalized: float
    clipped_luminance_low: float
    clipped_luminance_high: float
    max_measure_seconds: float

    def validate(self) -> None:
        if type(self) is not GeometryConfig:
            raise GeometryFailure(
                GeometryFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "GEOMETRY_CONFIG_TYPE_UNSUPPORTED",
            )
        if (
            type(self.version) is not str
            or self.version != "geometry-resource-policy-v1"
            or type(self.measurement_recipe_version) is not str
            or self.measurement_recipe_version != "raw-quality-recipe-v1"
        ):
            raise GeometryFailure(
                GeometryFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "GEOMETRY_CONFIG_VERSION_UNSUPPORTED",
            )
        integer_fields = (self.max_image_pixels, self.max_roi_pixels)
        if any(type(value) is not int or value <= 0 for value in integer_fields):
            raise GeometryFailure(
                GeometryFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "GEOMETRY_CONFIG_INVALID",
            )
        float_fields = (
            self.max_homography_condition_number,
            self.min_quad_area_normalized,
            self.edge_contact_threshold_normalized,
            self.clipped_luminance_low,
            self.clipped_luminance_high,
            self.max_measure_seconds,
        )
        if any(
            type(value) is not float or not isfinite(value) or value <= 0.0
            for value in float_fields
        ):
            raise GeometryFailure(
                GeometryFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "GEOMETRY_CONFIG_INVALID",
            )
        if not 0.0 < self.clipped_luminance_low < self.clipped_luminance_high < 255.0:
            raise GeometryFailure(
                GeometryFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "GEOMETRY_CONFIG_INVALID",
            )


DEFAULT_GEOMETRY_CONFIG = GeometryConfig(
    version="geometry-resource-policy-v1",
    measurement_recipe_version="raw-quality-recipe-v1",
    max_image_pixels=40_000_000,
    max_roi_pixels=16_000_000,
    max_homography_condition_number=1_000.0,
    min_quad_area_normalized=1e-6,
    edge_contact_threshold_normalized=0.02,
    clipped_luminance_low=5.0,
    clipped_luminance_high=250.0,
    max_measure_seconds=2.0,
)


def _finite_unit_interval(value: float, *, inclusive_upper: bool = True) -> None:
    if type(value) is not float and type(value) is not int:
        raise GeometryFailure(
            GeometryFailureCode.COORDINATE_OUT_OF_RANGE,
            "unsupported-input",
            "GEOMETRY_COORDINATE_OUT_OF_RANGE",
        )
    number = float(value)
    if not isfinite(number):
        raise GeometryFailure(
            GeometryFailureCode.COORDINATE_OUT_OF_RANGE,
            "unsupported-input",
            "GEOMETRY_COORDINATE_OUT_OF_RANGE",
        )
    upper_ok = number <= 1.0 if inclusive_upper else number < 1.0
    if number < 0.0 or not upper_ok:
        raise GeometryFailure(
            GeometryFailureCode.COORDINATE_OUT_OF_RANGE,
            "unsupported-input",
            "GEOMETRY_COORDINATE_OUT_OF_RANGE",
        )


@dataclass(frozen=True, slots=True)
class NormalizedPoint:
    x: float
    y: float

    def __post_init__(self) -> None:
        _finite_unit_interval(self.x)
        _finite_unit_interval(self.y)
        object.__setattr__(self, "x", float(self.x))
        object.__setattr__(self, "y", float(self.y))

    def as_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)


def _validate_size(size: tuple[int, int]) -> tuple[int, int]:
    if (
        type(size) is not tuple
        or len(size) != 2
        or any(type(value) is not int or value <= 0 for value in size)
    ):
        raise GeometryFailure(
            GeometryFailureCode.INVALID_GEOMETRY,
            "unsupported-input",
            "GEOMETRY_INVALID_SIZE",
        )
    return size


def normalized_to_pixel(point: NormalizedPoint, size: tuple[int, int]) -> tuple[int, int]:
    if type(point) is not NormalizedPoint:
        raise GeometryFailure(
            GeometryFailureCode.INVALID_GEOMETRY,
            "unsupported-input",
            "GEOMETRY_INVALID_POINT",
        )
    width, height = _validate_size(size)
    # Map normalized [0,1] onto the closed pixel extent [0, width] x [0, height].
    # Lattice-aligned fractions (k/width) round-trip exactly via nearest integer.
    x = int(round(point.x * width))
    y = int(round(point.y * height))
    x = min(max(x, 0), width)
    y = min(max(y, 0), height)
    return (x, y)


def pixel_to_normalized(pixel: tuple[int, int], size: tuple[int, int]) -> NormalizedPoint:
    width, height = _validate_size(size)
    if (
        type(pixel) is not tuple
        or len(pixel) != 2
        or any(type(value) is not int for value in pixel)
        or pixel[0] < 0
        or pixel[1] < 0
        or pixel[0] > width
        or pixel[1] > height
    ):
        raise GeometryFailure(
            GeometryFailureCode.COORDINATE_OUT_OF_RANGE,
            "unsupported-input",
            "GEOMETRY_COORDINATE_OUT_OF_RANGE",
        )
    return NormalizedPoint(pixel[0] / width, pixel[1] / height)


@dataclass(frozen=True, slots=True)
class NormalizedBox:
    """Axis-aligned box in canonical normalized coordinates.

    Coordinates are inclusive of the origin edge and use half-open pixel bounds:
    ``to_pixel_bounds`` returns ``(x0, y0, x1, y1)`` suitable for ``array[y0:y1, x0:x1]``.
    """

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        for value in (self.x0, self.y0, self.x1, self.y1):
            _finite_unit_interval(value)
        if not (self.x0 < self.x1 and self.y0 < self.y1):
            raise GeometryFailure(
                GeometryFailureCode.INVALID_GEOMETRY,
                "unsupported-input",
                "GEOMETRY_INVALID_BOX",
            )
        object.__setattr__(self, "x0", float(self.x0))
        object.__setattr__(self, "y0", float(self.y0))
        object.__setattr__(self, "x1", float(self.x1))
        object.__setattr__(self, "y1", float(self.y1))

    def width(self) -> float:
        return self.x1 - self.x0

    def height(self) -> float:
        return self.y1 - self.y0

    def area(self) -> float:
        return self.width() * self.height()

    def center(self) -> NormalizedPoint:
        return NormalizedPoint((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)

    def to_pixel_bounds(self, size: tuple[int, int]) -> tuple[int, int, int, int]:
        width, height = _validate_size(size)
        x0 = int(self.x0 * width)
        y0 = int(self.y0 * height)
        x1 = int(self.x1 * width)
        y1 = int(self.y1 * height)
        if x1 <= x0:
            x1 = min(width, x0 + 1)
        if y1 <= y0:
            y1 = min(height, y0 + 1)
        x0 = min(max(x0, 0), width)
        y0 = min(max(y0, 0), height)
        x1 = min(max(x1, 0), width)
        y1 = min(max(y1, 0), height)
        if x1 <= x0 or y1 <= y0:
            raise GeometryFailure(
                GeometryFailureCode.INVALID_GEOMETRY,
                "unsupported-input",
                "GEOMETRY_EMPTY_PIXEL_BOX",
            )
        return (x0, y0, x1, y1)


@dataclass(frozen=True, slots=True)
class NormalizedQuad:
    """Ordered convex quadrilateral: top-left, top-right, bottom-right, bottom-left."""

    points: tuple[NormalizedPoint, NormalizedPoint, NormalizedPoint, NormalizedPoint]

    def __init__(self, points: Sequence[NormalizedPoint | tuple[float, float]]) -> None:
        if len(points) != 4:
            raise GeometryFailure(
                GeometryFailureCode.INVALID_GEOMETRY,
                "unsupported-input",
                "GEOMETRY_INVALID_QUAD",
            )
        normalized: list[NormalizedPoint] = []
        for point in points:
            if type(point) is NormalizedPoint:
                normalized.append(point)
            elif type(point) is tuple and len(point) == 2:
                normalized.append(NormalizedPoint(float(point[0]), float(point[1])))
            else:
                raise GeometryFailure(
                    GeometryFailureCode.INVALID_GEOMETRY,
                    "unsupported-input",
                    "GEOMETRY_INVALID_QUAD",
                )
        object.__setattr__(self, "points", tuple(normalized))

    def as_array(self) -> np.ndarray:
        return np.array([point.as_tuple() for point in self.points], dtype=np.float64)


def compose_source_point_to_canonical_pixel(
    source_point: NormalizedPoint,
    transform: OrientationTransform,
    canonical_size: tuple[int, int],
) -> tuple[int, int]:
    if type(transform) is not OrientationTransform:
        raise GeometryFailure(
            GeometryFailureCode.INVALID_GEOMETRY,
            "unsupported-input",
            "GEOMETRY_INVALID_TRANSFORM",
        )
    canonical = NormalizedPoint(*transform.source_to_canonical(source_point.as_tuple()))
    return normalized_to_pixel(canonical, canonical_size)


@dataclass(frozen=True, slots=True)
class ExtractedRoi:
    """Detached ROI crop. ``evidence_kind`` distinguishes source ROI from rectified derivative."""

    width: int
    height: int
    mode: str
    evidence_kind: str
    recipe_version: str
    source_box: NormalizedBox | None
    source_quad: NormalizedQuad | None
    rectified: bool
    homography_condition_number: float | None
    _pixels: bytes = field(repr=False)

    def to_pillow(self) -> Image.Image:
        return Image.frombytes(self.mode, (self.width, self.height), self._pixels)

    def to_rgb_array(self) -> np.ndarray:
        array = np.frombuffer(self._pixels, dtype=np.uint8).reshape(self.height, self.width, 3)
        return array.copy()


def _check_time_budget(
    config: GeometryConfig,
    started_at: float,
    deadline: float | None,
    cancelled: Callable[[], bool] | None,
    clock: Callable[[], float],
) -> float:
    if cancelled is not None and cancelled():
        raise GeometryFailure(
            GeometryFailureCode.MEASURE_BUDGET_EXCEEDED,
            "timeout",
            "GEOMETRY_MEASURE_CANCELLED",
        )
    now = clock()
    if deadline is not None and now > deadline:
        raise GeometryFailure(
            GeometryFailureCode.MEASURE_BUDGET_EXCEEDED,
            "timeout",
            "GEOMETRY_MEASURE_DEADLINE_EXCEEDED",
        )
    if now - started_at > config.max_measure_seconds:
        raise GeometryFailure(
            GeometryFailureCode.MEASURE_BUDGET_EXCEEDED,
            "timeout",
            "GEOMETRY_MEASURE_TIME_BUDGET_EXCEEDED",
        )
    return now


def _canonical_rgb_array(
    image: CanonicalImage | Image.Image | np.ndarray,
    config: GeometryConfig,
) -> np.ndarray:
    if isinstance(image, CanonicalImage):
        width, height = image.canonical_size
        if width * height > config.max_image_pixels:
            raise GeometryFailure(
                GeometryFailureCode.IMAGE_BUDGET_EXCEEDED,
                "local-resource",
                "GEOMETRY_IMAGE_BUDGET_EXCEEDED",
            )
        if image.mode != "RGB":
            raise GeometryFailure(
                GeometryFailureCode.INVALID_GEOMETRY,
                "unsupported-input",
                "GEOMETRY_IMAGE_MODE_UNSUPPORTED",
            )
        array = np.frombuffer(image.to_pillow().tobytes(), dtype=np.uint8).reshape(height, width, 3)
        return array.copy()
    if isinstance(image, Image.Image):
        rgb = image.convert("RGB")
        width, height = rgb.size
        if width * height > config.max_image_pixels:
            raise GeometryFailure(
                GeometryFailureCode.IMAGE_BUDGET_EXCEEDED,
                "local-resource",
                "GEOMETRY_IMAGE_BUDGET_EXCEEDED",
            )
        return np.asarray(rgb, dtype=np.uint8).copy()
    if isinstance(image, np.ndarray):
        if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
            raise GeometryFailure(
                GeometryFailureCode.INVALID_GEOMETRY,
                "unsupported-input",
                "GEOMETRY_IMAGE_ARRAY_UNSUPPORTED",
            )
        height, width = image.shape[:2]
        if width * height > config.max_image_pixels:
            raise GeometryFailure(
                GeometryFailureCode.IMAGE_BUDGET_EXCEEDED,
                "local-resource",
                "GEOMETRY_IMAGE_BUDGET_EXCEEDED",
            )
        return np.ascontiguousarray(image.copy())
    raise GeometryFailure(
        GeometryFailureCode.INVALID_GEOMETRY,
        "unsupported-input",
        "GEOMETRY_IMAGE_TYPE_UNSUPPORTED",
    )


def extract_roi_box(
    image: CanonicalImage | Image.Image | np.ndarray,
    box: NormalizedBox,
    config: GeometryConfig = DEFAULT_GEOMETRY_CONFIG,
    *,
    deadline: float | None = None,
    cancelled: Callable[[], bool] | None = None,
    clock: Callable[[], float] = monotonic,
) -> ExtractedRoi:
    config.validate()
    if type(box) is not NormalizedBox:
        raise GeometryFailure(
            GeometryFailureCode.INVALID_GEOMETRY,
            "unsupported-input",
            "GEOMETRY_INVALID_BOX",
        )
    started_at = clock()
    _check_time_budget(config, started_at, deadline, cancelled, clock)
    array = _canonical_rgb_array(image, config)
    height, width = array.shape[:2]
    x0, y0, x1, y1 = box.to_pixel_bounds((width, height))
    crop = np.ascontiguousarray(array[y0:y1, x0:x1].copy())
    roi_h, roi_w = crop.shape[:2]
    if roi_w * roi_h > config.max_roi_pixels:
        raise GeometryFailure(
            GeometryFailureCode.ROI_BUDGET_EXCEEDED,
            "local-resource",
            "GEOMETRY_ROI_BUDGET_EXCEEDED",
        )
    _check_time_budget(config, started_at, deadline, cancelled, clock)
    return ExtractedRoi(
        width=roi_w,
        height=roi_h,
        mode="RGB",
        evidence_kind="source_roi",
        recipe_version=config.measurement_recipe_version,
        source_box=box,
        source_quad=None,
        rectified=False,
        homography_condition_number=None,
        _pixels=crop.tobytes(),
    )


def _quad_signed_area(points: np.ndarray) -> float:
    x = points[:, 0]
    y = points[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _side_lengths(points: np.ndarray) -> tuple[float, float, float, float]:
    lengths = []
    for index in range(4):
        a = points[index]
        b = points[(index + 1) % 4]
        lengths.append(hypot(float(b[0] - a[0]), float(b[1] - a[1])))
    return (lengths[0], lengths[1], lengths[2], lengths[3])


def _is_convex_quad(points: np.ndarray) -> bool:
    signs: list[float] = []
    for index in range(4):
        a = points[index]
        b = points[(index + 1) % 4]
        c = points[(index + 2) % 4]
        cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cross) < 1e-12:
            return False
        signs.append(cross)
    return all(value > 0 for value in signs) or all(value < 0 for value in signs)


def _homography_condition_number(matrix: np.ndarray) -> float:
    singular_values = np.linalg.svd(matrix, compute_uv=False)
    smallest = float(singular_values[-1])
    if smallest <= 0.0 or not isfinite(smallest):
        return float("inf")
    return float(singular_values[0] / smallest)


def rectify_quad(
    image: CanonicalImage | Image.Image | np.ndarray,
    quad: NormalizedQuad,
    config: GeometryConfig = DEFAULT_GEOMETRY_CONFIG,
    *,
    output_size: tuple[int, int] | None = None,
    deadline: float | None = None,
    cancelled: Callable[[], bool] | None = None,
    clock: Callable[[], float] = monotonic,
) -> ExtractedRoi:
    """Perspective-rectify a caller-provided convex quadrilateral.

    Rectification never claims recovery of hidden wraparound content. The result is a
    detached rectified derivative with ``evidence_kind='rectified_derivative'`` and does
    not replace the unrectified source ROI identity.
    """
    config.validate()
    if type(quad) is not NormalizedQuad:
        raise GeometryFailure(
            GeometryFailureCode.INVALID_GEOMETRY,
            "unsupported-input",
            "GEOMETRY_INVALID_QUAD",
        )
    started_at = clock()
    _check_time_budget(config, started_at, deadline, cancelled, clock)
    array = _canonical_rgb_array(image, config)
    height, width = array.shape[:2]
    normalized = quad.as_array()
    if np.any(normalized < 0.0) or np.any(normalized > 1.0):
        raise GeometryFailure(
            GeometryFailureCode.QUAD_OUT_OF_BOUNDS,
            "unsupported-input",
            "GEOMETRY_QUAD_OUT_OF_BOUNDS",
        )
    area = abs(_quad_signed_area(normalized))
    if area < config.min_quad_area_normalized or not _is_convex_quad(normalized):
        raise GeometryFailure(
            GeometryFailureCode.QUAD_DEGENERATE,
            "unsupported-input",
            "GEOMETRY_QUAD_DEGENERATE",
        )
    src = normalized.copy()
    src[:, 0] *= width
    src[:, 1] *= height
    src = src.astype(np.float32)
    side_top, side_right, side_bottom, side_left = _side_lengths(src)
    out_w = int(round(max(side_top, side_bottom)))
    out_h = int(round(max(side_left, side_right)))
    if output_size is not None:
        out_w, out_h = _validate_size(output_size)
    out_w = max(out_w, 1)
    out_h = max(out_h, 1)
    if out_w * out_h > config.max_roi_pixels:
        raise GeometryFailure(
            GeometryFailureCode.ROI_BUDGET_EXCEEDED,
            "local-resource",
            "GEOMETRY_ROI_BUDGET_EXCEEDED",
        )
    dst = np.array(
        [[0.0, 0.0], [out_w - 1.0, 0.0], [out_w - 1.0, out_h - 1.0], [0.0, out_h - 1.0]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(src, dst)
    condition = _homography_condition_number(matrix)
    if not isfinite(condition) or condition > config.max_homography_condition_number:
        raise GeometryFailure(
            GeometryFailureCode.HOMOGRAPHY_ILL_CONDITIONED,
            "unsupported-input",
            "GEOMETRY_HOMOGRAPHY_ILL_CONDITIONED",
        )
    # OpenCV expects BGR for color images; keep RGB channel order by treating as 3-channel.
    warped = cv2.warpPerspective(
        array,
        matrix,
        (out_w, out_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    warped = np.ascontiguousarray(warped.copy())
    _check_time_budget(config, started_at, deadline, cancelled, clock)
    return ExtractedRoi(
        width=out_w,
        height=out_h,
        mode="RGB",
        evidence_kind="rectified_derivative",
        recipe_version=config.measurement_recipe_version,
        source_box=None,
        source_quad=quad,
        rectified=True,
        homography_condition_number=float(condition),
        _pixels=warped.tobytes(),
    )


@dataclass(frozen=True, slots=True)
class QualityFeature:
    name: str
    value: float | None
    state: str
    unit: str | None = None

    def __post_init__(self) -> None:
        if self.state not in {"measured", "unknown", "not_determinable"}:
            raise GeometryFailure(
                GeometryFailureCode.INVALID_GEOMETRY,
                "unsupported-input",
                "GEOMETRY_INVALID_FEATURE_STATE",
            )
        if self.state == "measured":
            if self.value is None or not isfinite(float(self.value)):
                raise GeometryFailure(
                    GeometryFailureCode.INVALID_GEOMETRY,
                    "unsupported-input",
                    "GEOMETRY_INVALID_FEATURE_VALUE",
                )
            object.__setattr__(self, "value", float(self.value))
        else:
            object.__setattr__(self, "value", None)


@dataclass(frozen=True, slots=True)
class RawQualityMeasurements:
    recipe_version: str
    crop: QualityFeature
    scale: QualityFeature
    center: QualityFeature
    blur: QualityFeature
    exposure: QualityFeature
    contrast: QualityFeature
    glare: QualityFeature
    occlusion: QualityFeature
    perspective: QualityFeature
    motion: QualityFeature
    extras: dict[str, QualityFeature]

    def as_content_free_dict(self) -> dict[str, Any]:
        def pack(feature: QualityFeature) -> dict[str, Any]:
            payload: dict[str, Any] = {
                "name": feature.name,
                "state": feature.state,
                "unit": feature.unit,
            }
            if feature.value is not None:
                payload["value"] = feature.value
            return payload

        body = {
            "recipe_version": self.recipe_version,
            "crop": pack(self.crop),
            "scale": pack(self.scale),
            "center": pack(self.center),
            "blur": pack(self.blur),
            "exposure": pack(self.exposure),
            "contrast": pack(self.contrast),
            "glare": pack(self.glare),
            "occlusion": pack(self.occlusion),
            "perspective": pack(self.perspective),
            "motion": pack(self.motion),
            "extras": {key: pack(value) for key, value in sorted(self.extras.items())},
        }
        return body


def _luminance(rgb: np.ndarray) -> np.ndarray:
    # Rec. 601 luma as float64 so OpenCV derivative filters accept the source.
    arr = rgb.astype(np.float64)
    return 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]


def measure_raw_quality(
    image: CanonicalImage | Image.Image | np.ndarray,
    roi: NormalizedBox | NormalizedQuad | None = None,
    config: GeometryConfig = DEFAULT_GEOMETRY_CONFIG,
    *,
    synthetic_motion_label: bool = False,
    deadline: float | None = None,
    cancelled: Callable[[], bool] | None = None,
    clock: Callable[[], float] = monotonic,
) -> RawQualityMeasurements:
    """Content-free raw quality features on a full frame or caller-provided ROI.

    Motion remains ``not_determinable`` for a single still unless the caller explicitly
    marks synthetic labeled motion evidence (``synthetic_motion_label=True``), in which
    case motion stays ``unknown`` rather than inventing a physical direction claim.
    """
    config.validate()
    started_at = clock()
    _check_time_budget(config, started_at, deadline, cancelled, clock)
    array = _canonical_rgb_array(image, config)
    frame_h, frame_w = array.shape[:2]
    frame_area = float(frame_w * frame_h)

    box: NormalizedBox
    perspective_feature: QualityFeature
    if roi is None:
        box = NormalizedBox(0.0, 0.0, 1.0, 1.0)
        perspective_feature = QualityFeature(
            "perspective_condition",
            None,
            "not_determinable",
            unit=None,
        )
        crop = array
    elif type(roi) is NormalizedBox:
        box = roi
        perspective_feature = QualityFeature(
            "perspective_condition",
            None,
            "not_determinable",
            unit=None,
        )
        extracted = extract_roi_box(
            array,
            box,
            config,
            deadline=deadline,
            cancelled=cancelled,
            clock=clock,
        )
        crop = extracted.to_rgb_array()
    elif type(roi) is NormalizedQuad:
        points = roi.as_array()
        box = NormalizedBox(
            float(points[:, 0].min()),
            float(points[:, 1].min()),
            float(points[:, 0].max()),
            float(points[:, 1].max()),
        )
        sides = _side_lengths(points)
        # Opposite-side ratio imbalance in normalized space (content-free proxy).
        ratio_tb = sides[0] / sides[2] if sides[2] > 1e-12 else float("inf")
        ratio_lr = sides[3] / sides[1] if sides[1] > 1e-12 else float("inf")
        imbalance = abs(math_log_ratio(ratio_tb)) + abs(math_log_ratio(ratio_lr))
        try:
            rectified = rectify_quad(
                array,
                roi,
                config,
                deadline=deadline,
                cancelled=cancelled,
                clock=clock,
            )
            condition = rectified.homography_condition_number or float("inf")
            crop = rectified.to_rgb_array()
            perspective_value = float(condition) + float(imbalance)
            perspective_feature = QualityFeature(
                "perspective_condition",
                perspective_value,
                "measured",
                unit="condition",
            )
        except GeometryFailure:
            crop = extract_roi_box(
                array,
                box,
                config,
                deadline=deadline,
                cancelled=cancelled,
                clock=clock,
            ).to_rgb_array()
            perspective_feature = QualityFeature(
                "perspective_condition",
                None,
                "unknown",
                unit="condition",
            )
    else:
        raise GeometryFailure(
            GeometryFailureCode.INVALID_GEOMETRY,
            "unsupported-input",
            "GEOMETRY_INVALID_ROI",
        )

    _check_time_budget(config, started_at, deadline, cancelled, clock)
    roi_h, roi_w = crop.shape[:2]
    roi_area = float(max(roi_w * roi_h, 1))
    short_side = float(min(roi_w, roi_h))

    left = box.x0
    top = box.y0
    right = 1.0 - box.x1
    bottom = 1.0 - box.y1
    min_margin = min(left, top, right, bottom)
    edge_contact = 1.0 if min_margin <= config.edge_contact_threshold_normalized else 0.0
    completeness = max(
        0.0, min(1.0, min_margin / max(config.edge_contact_threshold_normalized, 1e-9))
    )

    center = box.center()
    center_offset = hypot(center.x - 0.5, center.y - 0.5)

    gray = _luminance(crop)
    # Laplacian variance (blur/sharpness). Higher => sharper.
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    blur_var = float(lap.var())
    # Tenengrad / Sobel energy.
    sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    tenengrad = float(np.mean(sobel_x * sobel_x + sobel_y * sobel_y))

    percentiles = np.percentile(gray, [5.0, 50.0, 95.0])
    p5, p50, p95 = (float(percentiles[0]), float(percentiles[1]), float(percentiles[2]))
    clipped_low = float(np.mean(gray <= config.clipped_luminance_low))
    clipped_high = float(np.mean(gray >= config.clipped_luminance_high))
    contrast = float(p95 - p5)
    global_std = float(np.std(gray))

    # Glare/specular candidate: high value + low saturation + low local texture.
    rgb_f = crop.astype(np.float32)
    max_c = np.max(rgb_f, axis=2)
    min_c = np.min(rgb_f, axis=2)
    sat = np.zeros_like(max_c, dtype=np.float32)
    positive = max_c > 1e-6
    sat[positive] = (max_c[positive] - min_c[positive]) / max_c[positive]
    high_value = max_c >= 240.0
    low_sat = sat <= 0.15
    texture = cv2.Laplacian(gray, cv2.CV_64F)
    low_texture = np.abs(texture) <= 12.0
    glare_score = float(np.mean(high_value & low_sat & low_texture))

    # Occlusion remains residual/unknown-capable; single still cannot claim direction.
    occlusion_feature = QualityFeature("occlusion_proxy", None, "unknown", unit=None)

    if synthetic_motion_label:
        motion_feature = QualityFeature("motion", None, "unknown", unit=None)
    else:
        motion_feature = QualityFeature("motion", None, "not_determinable", unit=None)

    _check_time_budget(config, started_at, deadline, cancelled, clock)
    return RawQualityMeasurements(
        recipe_version=config.measurement_recipe_version,
        crop=QualityFeature("edge_contact", edge_contact, "measured", unit="fraction"),
        scale=QualityFeature(
            "roi_area_fraction", roi_area / frame_area, "measured", unit="fraction"
        ),
        center=QualityFeature("center_offset", center_offset, "measured", unit="normalized"),
        blur=QualityFeature("laplacian_variance", blur_var, "measured", unit="variance"),
        exposure=QualityFeature("luminance_p50", p50, "measured", unit="luma"),
        contrast=QualityFeature("luminance_p95_minus_p5", contrast, "measured", unit="luma"),
        glare=QualityFeature("specular_candidate", glare_score, "measured", unit="fraction"),
        occlusion=occlusion_feature,
        perspective=perspective_feature,
        motion=motion_feature,
        extras={
            "completeness_margin": QualityFeature(
                "completeness_margin",
                completeness,
                "measured",
                unit="fraction",
            ),
            "roi_short_side_px": QualityFeature(
                "roi_short_side_px",
                short_side,
                "measured",
                unit="px",
            ),
            "tenengrad": QualityFeature("tenengrad", tenengrad, "measured", unit="energy"),
            "clipped_low_fraction": QualityFeature(
                "clipped_low_fraction",
                clipped_low,
                "measured",
                unit="fraction",
            ),
            "clipped_high_fraction": QualityFeature(
                "clipped_high_fraction",
                clipped_high,
                "measured",
                unit="fraction",
            ),
            "luminance_std": QualityFeature("luminance_std", global_std, "measured", unit="luma"),
            "frame_width_px": QualityFeature(
                "frame_width_px", float(frame_w), "measured", unit="px"
            ),
            "frame_height_px": QualityFeature(
                "frame_height_px", float(frame_h), "measured", unit="px"
            ),
        },
    )


def math_log_ratio(ratio: float) -> float:
    if not isfinite(ratio) or ratio <= 0.0:
        return float("inf")
    return float(np.log(ratio))


@dataclass(frozen=True, slots=True)
class OverlayBox:
    box: NormalizedBox
    kind: str = "box"

    def __post_init__(self) -> None:
        if type(self.box) is not NormalizedBox:
            raise GeometryFailure(
                GeometryFailureCode.INVALID_GEOMETRY,
                "unsupported-input",
                "GEOMETRY_INVALID_OVERLAY",
            )
        if type(self.kind) is not str or not self.kind:
            raise GeometryFailure(
                GeometryFailureCode.INVALID_GEOMETRY,
                "unsupported-input",
                "GEOMETRY_INVALID_OVERLAY",
            )


@dataclass(frozen=True, slots=True)
class OverlayPolygon:
    points: tuple[NormalizedPoint, ...]
    kind: str = "polygon"

    def __post_init__(self) -> None:
        if len(self.points) < 3:
            raise GeometryFailure(
                GeometryFailureCode.INVALID_GEOMETRY,
                "unsupported-input",
                "GEOMETRY_INVALID_OVERLAY",
            )
        if any(type(point) is not NormalizedPoint for point in self.points):
            raise GeometryFailure(
                GeometryFailureCode.INVALID_GEOMETRY,
                "unsupported-input",
                "GEOMETRY_INVALID_OVERLAY",
            )
        object.__setattr__(self, "points", tuple(self.points))


@dataclass(frozen=True, slots=True)
class OverlayArrow:
    """Directional segment in canonical normalized coordinates (start -> end)."""

    start: NormalizedPoint
    end: NormalizedPoint
    kind: str = "arrow"

    def __post_init__(self) -> None:
        if type(self.start) is not NormalizedPoint or type(self.end) is not NormalizedPoint:
            raise GeometryFailure(
                GeometryFailureCode.INVALID_GEOMETRY,
                "unsupported-input",
                "GEOMETRY_INVALID_OVERLAY",
            )
        if self.start.as_tuple() == self.end.as_tuple():
            raise GeometryFailure(
                GeometryFailureCode.INVALID_GEOMETRY,
                "unsupported-input",
                "GEOMETRY_INVALID_OVERLAY",
            )


def overlay_box_from_normalized(box: NormalizedBox) -> OverlayBox:
    return OverlayBox(box=box)


def overlay_polygon_from_quad(quad: NormalizedQuad) -> OverlayPolygon:
    return OverlayPolygon(points=quad.points, kind="quad")


def overlay_arrow(start: NormalizedPoint, end: NormalizedPoint) -> OverlayArrow:
    return OverlayArrow(start=start, end=end)


def canonicalize_overlay_point(
    source_point: NormalizedPoint,
    transform: OrientationTransform,
) -> NormalizedPoint:
    return NormalizedPoint(*transform.source_to_canonical(source_point.as_tuple()))
