from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from time import monotonic
from typing import Any, Protocol

import cv2
import numpy as np
from physical_vision_geometry import NormalizedBox, NormalizedQuad
from physical_vision_image import CanonicalImage, OrientationTransform
from PIL import Image


class LocalizationFailureCode(str, Enum):
    CONFIG_VERSION_UNSUPPORTED = "CONFIG_VERSION_UNSUPPORTED"
    IMAGE_BUDGET_EXCEEDED = "IMAGE_BUDGET_EXCEEDED"
    INVALID_IMAGE = "INVALID_IMAGE"
    PROPOSE_BUDGET_EXCEEDED = "PROPOSE_BUDGET_EXCEEDED"


class LocalizationFailure(ValueError):
    def __init__(self, code: LocalizationFailureCode, category: str, message_key: str) -> None:
        super().__init__(message_key)
        self.code = code
        self.category = category
        self.message_key = message_key


class ProposalKind(str, Enum):
    BARCODE_LANDMARK = "barcode_landmark"
    LABEL_REGION = "label_region"
    TEXT_REGION = "text_region"


class ProposalPresence(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    UNCERTAIN = "uncertain"


class LocalizationOutcome(str, Enum):
    TRUSTWORTHY = "trustworthy"
    NO_LABEL = "no_label"
    MULTIPLE_LABELS = "multiple_labels"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class LocalizationConfig:
    version: str
    max_image_pixels: int
    max_proposals: int
    min_barcode_area_normalized: float
    min_label_area_normalized: float
    min_barcode_aspect_ratio: float
    max_barcode_aspect_ratio: float
    barcode_gradient_threshold: float
    morphology_kernel_width: int
    morphology_kernel_height: int
    max_propose_seconds: float

    def validate(self) -> None:
        if type(self) is not LocalizationConfig:
            raise LocalizationFailure(
                LocalizationFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "LOCALIZATION_CONFIG_TYPE_UNSUPPORTED",
            )
        if type(self.version) is not str or self.version != "classical-localization-recipe-v1":
            raise LocalizationFailure(
                LocalizationFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "LOCALIZATION_CONFIG_VERSION_UNSUPPORTED",
            )
        ints = (
            self.max_image_pixels,
            self.max_proposals,
            self.morphology_kernel_width,
            self.morphology_kernel_height,
        )
        if any(type(value) is not int or value <= 0 for value in ints):
            raise LocalizationFailure(
                LocalizationFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "LOCALIZATION_CONFIG_INVALID",
            )
        floats = (
            self.min_barcode_area_normalized,
            self.min_label_area_normalized,
            self.min_barcode_aspect_ratio,
            self.max_barcode_aspect_ratio,
            self.barcode_gradient_threshold,
            self.max_propose_seconds,
        )
        if any(type(value) is not float or not isfinite(value) or value <= 0.0 for value in floats):
            raise LocalizationFailure(
                LocalizationFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "LOCALIZATION_CONFIG_INVALID",
            )
        if not (
            self.min_barcode_aspect_ratio < self.max_barcode_aspect_ratio
            and 0.0 < self.min_barcode_area_normalized < 1.0
            and 0.0 < self.min_label_area_normalized < 1.0
        ):
            raise LocalizationFailure(
                LocalizationFailureCode.CONFIG_VERSION_UNSUPPORTED,
                "unsupported-input",
                "LOCALIZATION_CONFIG_INVALID",
            )


DEFAULT_LOCALIZATION_CONFIG = LocalizationConfig(
    version="classical-localization-recipe-v1",
    max_image_pixels=40_000_000,
    max_proposals=8,
    min_barcode_area_normalized=0.002,
    min_label_area_normalized=0.05,
    min_barcode_aspect_ratio=1.8,
    max_barcode_aspect_ratio=25.0,
    barcode_gradient_threshold=35.0,
    morphology_kernel_width=21,
    morphology_kernel_height=7,
    max_propose_seconds=2.0,
)


@dataclass(frozen=True, slots=True)
class RegionProposal:
    """Localization proposal in canonical normalized coordinates.

    Never carries barcode payload, decoded bytes, or serial text.
    """

    kind: ProposalKind
    presence: ProposalPresence
    box: NormalizedBox | None
    quad: NormalizedQuad | None
    score: float | None
    recipe_version: str
    source: str

    def __post_init__(self) -> None:
        if self.box is None and self.quad is None and self.presence is ProposalPresence.PRESENT:
            raise LocalizationFailure(
                LocalizationFailureCode.INVALID_IMAGE,
                "unsupported-input",
                "LOCALIZATION_PROPOSAL_GEOMETRY_REQUIRED",
            )


@dataclass(frozen=True, slots=True)
class LocalizationResult:
    outcome: LocalizationOutcome
    proposals: tuple[RegionProposal, ...]
    recipe_version: str
    orientation: int
    elapsed_ms: float
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LocalizationSummary:
    outcome: LocalizationOutcome
    primary: RegionProposal | None
    supporting: tuple[RegionProposal, ...]
    recipe_version: str


class BarcodeDetectorProtocol(Protocol):
    def detectAndDecodeWithType(self, image: np.ndarray) -> tuple[Any, Any, Any]: ...  # noqa: N802


def _check_time_budget(
    config: LocalizationConfig,
    started_at: float,
    deadline: float | None,
    cancelled: Callable[[], bool] | None,
    clock: Callable[[], float],
) -> None:
    if cancelled is not None and cancelled():
        raise LocalizationFailure(
            LocalizationFailureCode.PROPOSE_BUDGET_EXCEEDED,
            "timeout",
            "LOCALIZATION_PROPOSE_CANCELLED",
        )
    now = clock()
    if deadline is not None and now > deadline:
        raise LocalizationFailure(
            LocalizationFailureCode.PROPOSE_BUDGET_EXCEEDED,
            "timeout",
            "LOCALIZATION_PROPOSE_DEADLINE_EXCEEDED",
        )
    if now - started_at > config.max_propose_seconds:
        raise LocalizationFailure(
            LocalizationFailureCode.PROPOSE_BUDGET_EXCEEDED,
            "timeout",
            "LOCALIZATION_PROPOSE_TIME_BUDGET_EXCEEDED",
        )


def _canonical_rgb_array(
    image: CanonicalImage | Image.Image | np.ndarray,
    config: LocalizationConfig,
) -> np.ndarray:
    if isinstance(image, CanonicalImage):
        width, height = image.canonical_size
        if width * height > config.max_image_pixels:
            raise LocalizationFailure(
                LocalizationFailureCode.IMAGE_BUDGET_EXCEEDED,
                "local-resource",
                "LOCALIZATION_IMAGE_BUDGET_EXCEEDED",
            )
        if image.mode != "RGB":
            raise LocalizationFailure(
                LocalizationFailureCode.INVALID_IMAGE,
                "unsupported-input",
                "LOCALIZATION_IMAGE_MODE_UNSUPPORTED",
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
            raise LocalizationFailure(
                LocalizationFailureCode.IMAGE_BUDGET_EXCEEDED,
                "local-resource",
                "LOCALIZATION_IMAGE_BUDGET_EXCEEDED",
            )
        return np.asarray(rgb, dtype=np.uint8).copy()
    if isinstance(image, np.ndarray):
        if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
            raise LocalizationFailure(
                LocalizationFailureCode.INVALID_IMAGE,
                "unsupported-input",
                "LOCALIZATION_IMAGE_ARRAY_UNSUPPORTED",
            )
        height, width = image.shape[:2]
        if width * height > config.max_image_pixels:
            raise LocalizationFailure(
                LocalizationFailureCode.IMAGE_BUDGET_EXCEEDED,
                "local-resource",
                "LOCALIZATION_IMAGE_BUDGET_EXCEEDED",
            )
        return np.ascontiguousarray(image.copy())
    raise LocalizationFailure(
        LocalizationFailureCode.INVALID_IMAGE,
        "unsupported-input",
        "LOCALIZATION_IMAGE_TYPE_UNSUPPORTED",
    )


def _clamp_box(x0: float, y0: float, x1: float, y1: float) -> NormalizedBox | None:
    x0 = float(max(0.0, min(1.0, x0)))
    y0 = float(max(0.0, min(1.0, y0)))
    x1 = float(max(0.0, min(1.0, x1)))
    y1 = float(max(0.0, min(1.0, y1)))
    if not (x0 < x1 and y0 < y1):
        return None
    try:
        return NormalizedBox(x0, y0, x1, y1)
    except Exception:
        return None


def _box_from_pixel_rect(
    x: int, y: int, w: int, h: int, width: int, height: int
) -> NormalizedBox | None:
    if w <= 1 or h <= 1 or width <= 0 or height <= 0:
        return None
    return _clamp_box(x / width, y / height, (x + w) / width, (y + h) / height)


def _box_from_points(points: np.ndarray, width: int, height: int) -> NormalizedBox | None:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if pts.shape[0] < 2:
        return None
    x0 = float(np.min(pts[:, 0])) / width
    y0 = float(np.min(pts[:, 1])) / height
    x1 = float(np.max(pts[:, 0])) / width
    y1 = float(np.max(pts[:, 1])) / height
    return _clamp_box(x0, y0, x1, y1)


def _quad_from_points(points: np.ndarray, width: int, height: int) -> NormalizedQuad | None:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if pts.shape[0] != 4:
        return None
    # order by angle around centroid → approximate TL,TR,BR,BL
    center = pts.mean(axis=0)
    angles = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])
    order = np.argsort(angles)
    ordered = pts[order]
    # start from top-left-most
    start = int(np.argmin(ordered[:, 0] + ordered[:, 1]))
    ordered = np.roll(ordered, -start, axis=0)
    try:
        return NormalizedQuad(
            tuple(
                (
                    float(max(0.0, min(1.0, p[0] / width))),
                    float(max(0.0, min(1.0, p[1] / height))),
                )
                for p in ordered
            )
        )
    except Exception:
        return None


def _iou(a: NormalizedBox, b: NormalizedBox) -> float:
    ix0 = max(a.x0, b.x0)
    iy0 = max(a.y0, b.y0)
    ix1 = min(a.x1, b.x1)
    iy1 = min(a.y1, b.y1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    union = a.area() + b.area() - inter
    if union <= 0:
        return 0.0
    return inter / union


def _nms(proposals: list[RegionProposal], iou_threshold: float = 0.5) -> list[RegionProposal]:
    kept: list[RegionProposal] = []
    sorted_props = sorted(
        proposals,
        key=lambda p: (
            0 if p.kind is ProposalKind.BARCODE_LANDMARK else 1,
            -(p.score if p.score is not None else 0.0),
            -(p.box.area() if p.box is not None else 0.0),
        ),
    )
    for proposal in sorted_props:
        if proposal.box is None:
            continue
        if any(
            other.box is not None
            and other.kind == proposal.kind
            and _iou(proposal.box, other.box) >= iou_threshold
            for other in kept
        ):
            continue
        kept.append(proposal)
    return kept


def _opencv_barcode_proposals(
    gray: np.ndarray,
    width: int,
    height: int,
    config: LocalizationConfig,
    detector: Any | None,
    recipe: str,
) -> list[RegionProposal]:
    proposals: list[RegionProposal] = []
    try:
        if detector is None:
            detector = cv2.barcode.BarcodeDetector()
        # Prefer multi detect geometry-only path; never retain payload strings.
        if hasattr(detector, "detectMulti"):
            ok, corners = detector.detectMulti(gray)
            if ok and corners is not None:
                for corner in np.asarray(corners):
                    box = _box_from_points(corner, width, height)
                    if box is None or box.area() < config.min_barcode_area_normalized:
                        continue
                    aspect = box.width() / max(box.height(), 1e-9)
                    aspect_ok = config.min_barcode_aspect_ratio <= max(aspect, 1.0 / aspect) or (
                        config.min_barcode_aspect_ratio <= aspect <= config.max_barcode_aspect_ratio
                    )
                    # allow if area is large enough even if aspect is borderline
                    if not aspect_ok and box.area() < config.min_barcode_area_normalized * 2:
                        continue
                    quad = _quad_from_points(corner, width, height)
                    proposals.append(
                        RegionProposal(
                            kind=ProposalKind.BARCODE_LANDMARK,
                            presence=ProposalPresence.PRESENT,
                            box=box,
                            quad=quad,
                            score=float(box.area()),
                            recipe_version=recipe,
                            source="opencv_barcode_detect",
                        )
                    )
                return proposals
        if hasattr(detector, "detectAndDecodeWithType"):
            raw = detector.detectAndDecodeWithType(gray)
            # Drop index 0 (payload string) and type strings immediately.
            points = raw[1] if isinstance(raw, tuple) and len(raw) >= 2 else None
        elif hasattr(detector, "detectAndDecode"):
            raw = detector.detectAndDecode(gray)
            points = raw[1] if isinstance(raw, tuple) and len(raw) >= 2 else None
        elif hasattr(detector, "detect"):
            ok, points = detector.detect(gray)
            if not ok:
                points = None
        else:
            points = None
        if points is None:
            return proposals
        arr = np.asarray(points)
        if arr.size == 0:
            return proposals
        if arr.ndim == 2:
            arr = arr.reshape(1, -1, 2)
        elif arr.ndim == 3 and arr.shape[0] == 4 and arr.shape[1] != 4:
            arr = arr.reshape(1, 4, 2)
        for corner in arr:
            box = _box_from_points(corner, width, height)
            if box is None or box.area() < config.min_barcode_area_normalized:
                continue
            proposals.append(
                RegionProposal(
                    kind=ProposalKind.BARCODE_LANDMARK,
                    presence=ProposalPresence.PRESENT,
                    box=box,
                    quad=_quad_from_points(corner, width, height),
                    score=float(box.area()),
                    recipe_version=recipe,
                    source="opencv_barcode_detect",
                )
            )
    except LocalizationFailure:
        raise
    except Exception:
        # Detector unavailable or failed — morphological path still runs.
        return []
    return proposals


def _morph_barcode_proposals(
    gray: np.ndarray,
    width: int,
    height: int,
    config: LocalizationConfig,
    recipe: str,
) -> list[RegionProposal]:
    # Vertical gradient energy (barcode bars are vertical edges when upright).
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    grad_x = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
    # Prefer strong horizontal variation vs vertical (barcode stripes).
    energy = cv2.convertScaleAbs(grad_x) - 0.35 * cv2.convertScaleAbs(grad_y)
    energy = np.clip(energy, 0, 255).astype(np.uint8)
    _, thresh = cv2.threshold(
        energy, float(config.barcode_gradient_threshold), 255, cv2.THRESH_BINARY
    )
    kw = max(3, int(config.morphology_kernel_width) | 1)
    kh = max(3, int(config.morphology_kernel_height) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kw, kh))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    closed = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel, iterations=1)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    proposals: list[RegionProposal] = []
    image_area = float(width * height)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area_norm = (w * h) / image_area
        if area_norm < config.min_barcode_area_normalized:
            continue
        aspect = w / max(h, 1)
        if aspect < config.min_barcode_aspect_ratio or aspect > config.max_barcode_aspect_ratio:
            continue
        # Require dense vertical edge energy inside the box.
        roi = energy[y : y + h, x : x + w]
        if roi.size == 0:
            continue
        mean_energy = float(np.mean(roi))
        if mean_energy < config.barcode_gradient_threshold * 0.5:
            continue
        box = _box_from_pixel_rect(x, y, w, h, width, height)
        if box is None:
            continue
        proposals.append(
            RegionProposal(
                kind=ProposalKind.BARCODE_LANDMARK,
                presence=ProposalPresence.PRESENT,
                box=box,
                quad=None,
                score=float(area_norm * mean_energy),
                recipe_version=recipe,
                source="morph_gradient_barcode",
            )
        )
    return proposals


def _label_contour_proposals(
    gray: np.ndarray,
    width: int,
    height: int,
    config: LocalizationConfig,
    recipe: str,
) -> list[RegionProposal]:
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 120)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    proposals: list[RegionProposal] = []
    image_area = float(width * height)
    for contour in contours:
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        x, y, w, h = cv2.boundingRect(approx if len(approx) >= 4 else contour)
        area_norm = (w * h) / image_area
        if area_norm < config.min_label_area_normalized:
            continue
        # Reject near-full-frame and tiny frames.
        if area_norm > 0.95:
            continue
        aspect = w / max(h, 1)
        if aspect < 0.4 or aspect > 4.0:
            continue
        box = _box_from_pixel_rect(x, y, w, h, width, height)
        if box is None:
            continue
        quad = None
        if len(approx) == 4:
            quad = _quad_from_points(approx.reshape(4, 2), width, height)
        proposals.append(
            RegionProposal(
                kind=ProposalKind.LABEL_REGION,
                presence=ProposalPresence.PRESENT,
                box=box,
                quad=quad,
                score=float(area_norm),
                recipe_version=recipe,
                source="contour_label",
            )
        )
    return proposals


def _text_region_near_barcode(
    barcodes: Sequence[RegionProposal],
    labels: Sequence[RegionProposal],
    recipe: str,
) -> list[RegionProposal]:
    """Heuristic single text band above/below a barcode landmark (not a full scene detector)."""
    proposals: list[RegionProposal] = []
    for barcode in barcodes:
        if barcode.box is None:
            continue
        b = barcode.box
        height = b.height()
        # Prefer a band above the barcode of similar width and ~0.8x barcode height.
        y1 = b.y0
        y0 = max(0.0, b.y0 - max(height * 0.9, 0.04))
        if y1 - y0 < 0.02:
            y0 = b.y1
            y1 = min(1.0, b.y1 + max(height * 0.9, 0.04))
        box = _clamp_box(b.x0, y0, b.x1, y1)
        if box is None or box.area() < 0.001:
            continue
        # If a label already covers this area heavily, skip.
        if any(lab.box is not None and _iou(box, lab.box) > 0.7 for lab in labels):
            continue
        proposals.append(
            RegionProposal(
                kind=ProposalKind.TEXT_REGION,
                presence=ProposalPresence.PRESENT,
                box=box,
                quad=None,
                score=float(box.area()),
                recipe_version=recipe,
                source="near_barcode_heuristic",
            )
        )
    return proposals


def _stable_sort_key(proposal: RegionProposal) -> tuple:
    box = proposal.box
    return (
        proposal.kind.value,
        round(box.y0, 6) if box else 0.0,
        round(box.x0, 6) if box else 0.0,
        round(-(proposal.score or 0.0), 6),
    )


def _derive_outcome(proposals: Sequence[RegionProposal]) -> LocalizationOutcome:
    barcodes = [p for p in proposals if p.kind is ProposalKind.BARCODE_LANDMARK]
    labels = [p for p in proposals if p.kind is ProposalKind.LABEL_REGION]
    strong = barcodes or labels
    if not strong and not proposals:
        return LocalizationOutcome.NO_LABEL
    if not strong:
        return LocalizationOutcome.UNCERTAIN
    # Multiple distinct barcode landmarks or multiple large labels → ambiguous.
    distinct_barcodes = []
    for barcode in barcodes:
        if barcode.box is None:
            continue
        if any(other.box and _iou(barcode.box, other.box) > 0.4 for other in distinct_barcodes):
            continue
        distinct_barcodes.append(barcode)
    distinct_labels = []
    for label in labels:
        if label.box is None:
            continue
        if any(other.box and _iou(label.box, other.box) > 0.4 for other in distinct_labels):
            continue
        # ignore labels that largely contain a single barcode (same physical label)
        barcode_box = distinct_barcodes[0].box if len(distinct_barcodes) == 1 else None
        if barcode_box is not None and (
            _iou(label.box, barcode_box) > 0.15
            or (
                label.box.x0 <= barcode_box.x0
                and label.box.y0 <= barcode_box.y0
                and label.box.x1 >= barcode_box.x1
                and label.box.y1 >= barcode_box.y1
            )
        ):
            continue
        distinct_labels.append(label)
    if len(distinct_barcodes) >= 2:
        return LocalizationOutcome.MULTIPLE_LABELS
    if len(distinct_labels) >= 2 and len(distinct_barcodes) == 0:
        return LocalizationOutcome.MULTIPLE_LABELS
    if len(distinct_barcodes) == 1 or len(distinct_labels) == 1:
        return LocalizationOutcome.TRUSTWORTHY
    if strong:
        return LocalizationOutcome.TRUSTWORTHY
    return LocalizationOutcome.UNCERTAIN


def propose_classical_regions(
    image: CanonicalImage | Image.Image | np.ndarray,
    config: LocalizationConfig = DEFAULT_LOCALIZATION_CONFIG,
    *,
    orientation_transform: OrientationTransform | None = None,
    barcode_detector: Any | None = None,
    deadline: float | None = None,
    cancelled: Callable[[], bool] | None = None,
    clock: Callable[[], float] = monotonic,
) -> LocalizationResult:
    """Propose barcode/label/text regions using classical OpenCV methods.

    Geometry is always in the coordinate frame of the provided image (canonical
    when callers pass B06 ``CanonicalImage``). Barcode payload bytes/strings from
    any detector are dropped at this boundary and never appear on public results.
    """
    config.validate()
    started_at = clock()
    _check_time_budget(config, started_at, deadline, cancelled, clock)
    array = _canonical_rgb_array(image, config)
    height, width = array.shape[:2]
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    _check_time_budget(config, started_at, deadline, cancelled, clock)

    recipe = config.version
    barcodes = _opencv_barcode_proposals(gray, width, height, config, barcode_detector, recipe)
    _check_time_budget(config, started_at, deadline, cancelled, clock)
    barcodes.extend(_morph_barcode_proposals(gray, width, height, config, recipe))
    barcodes = _nms(barcodes, iou_threshold=0.45)

    _check_time_budget(config, started_at, deadline, cancelled, clock)
    labels = _nms(_label_contour_proposals(gray, width, height, config, recipe), 0.5)
    texts = _text_region_near_barcode(barcodes, labels, recipe)

    combined = barcodes + labels + texts
    combined = sorted(combined, key=_stable_sort_key)
    if len(combined) > config.max_proposals:
        # Keep highest-score first after kind priority, then re-sort stable.
        combined = sorted(
            combined,
            key=lambda p: (
                0
                if p.kind is ProposalKind.BARCODE_LANDMARK
                else 1
                if p.kind is ProposalKind.LABEL_REGION
                else 2,
                -(p.score or 0.0),
            ),
        )[: config.max_proposals]
        combined = sorted(combined, key=_stable_sort_key)

    outcome = _derive_outcome(combined)
    orientation = 1
    if orientation_transform is not None:
        if type(orientation_transform) is not OrientationTransform:
            raise LocalizationFailure(
                LocalizationFailureCode.INVALID_IMAGE,
                "unsupported-input",
                "LOCALIZATION_INVALID_TRANSFORM",
            )
        orientation = int(orientation_transform.orientation)
    elif isinstance(image, CanonicalImage):
        orientation = int(image.orientation)

    elapsed_ms = (clock() - started_at) * 1000.0
    return LocalizationResult(
        outcome=outcome,
        proposals=tuple(combined),
        recipe_version=recipe,
        orientation=orientation,
        elapsed_ms=float(elapsed_ms),
        notes=(),
    )


def select_localization_summary(result: LocalizationResult) -> LocalizationSummary:
    """Deterministic primary-region selection for later v3.1 reason mapping."""
    if type(result) is not LocalizationResult:
        raise LocalizationFailure(
            LocalizationFailureCode.INVALID_IMAGE,
            "unsupported-input",
            "LOCALIZATION_INVALID_RESULT",
        )
    proposals = list(result.proposals)
    if result.outcome is LocalizationOutcome.MULTIPLE_LABELS:
        return LocalizationSummary(
            outcome=LocalizationOutcome.MULTIPLE_LABELS,
            primary=None,
            supporting=tuple(proposals),
            recipe_version=result.recipe_version,
        )
    if result.outcome is LocalizationOutcome.NO_LABEL or not proposals:
        outcome = (
            result.outcome
            if result.outcome in {LocalizationOutcome.NO_LABEL, LocalizationOutcome.UNCERTAIN}
            else LocalizationOutcome.NO_LABEL
        )
        return LocalizationSummary(
            outcome=outcome,
            primary=None,
            supporting=(),
            recipe_version=result.recipe_version,
        )
    if result.outcome is LocalizationOutcome.UNCERTAIN:
        return LocalizationSummary(
            outcome=LocalizationOutcome.UNCERTAIN,
            primary=None,
            supporting=tuple(proposals),
            recipe_version=result.recipe_version,
        )

    barcodes = [p for p in proposals if p.kind is ProposalKind.BARCODE_LANDMARK]
    labels = [p for p in proposals if p.kind is ProposalKind.LABEL_REGION]
    texts = [p for p in proposals if p.kind is ProposalKind.TEXT_REGION]
    primary = None
    if len(barcodes) == 1:
        primary = barcodes[0]
    elif len(labels) == 1:
        primary = labels[0]
    elif barcodes:
        primary = max(barcodes, key=lambda p: p.score or 0.0)
    elif labels:
        primary = max(labels, key=lambda p: p.score or 0.0)
    elif texts:
        primary = max(texts, key=lambda p: p.score or 0.0)
    else:
        primary = proposals[0]

    supporting = tuple(p for p in proposals if p is not primary)
    return LocalizationSummary(
        outcome=LocalizationOutcome.TRUSTWORTHY,
        primary=primary,
        supporting=supporting,
        recipe_version=result.recipe_version,
    )


__all__ = [
    "DEFAULT_LOCALIZATION_CONFIG",
    "LocalizationConfig",
    "LocalizationFailure",
    "LocalizationFailureCode",
    "LocalizationOutcome",
    "LocalizationResult",
    "LocalizationSummary",
    "ProposalKind",
    "ProposalPresence",
    "RegionProposal",
    "propose_classical_regions",
    "select_localization_summary",
]
