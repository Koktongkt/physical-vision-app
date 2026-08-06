from __future__ import annotations

import math
from dataclasses import FrozenInstanceError

import cv2
import numpy as np
import pytest
from physical_vision_geometry import (
    DEFAULT_GEOMETRY_CONFIG,
    GeometryConfig,
    GeometryFailure,
    GeometryFailureCode,
    NormalizedBox,
    NormalizedPoint,
    NormalizedQuad,
    OverlayArrow,
    canonicalize_overlay_point,
    extract_roi_box,
    measure_raw_quality,
    normalized_to_pixel,
    overlay_arrow,
    overlay_box_from_normalized,
    overlay_polygon_from_quad,
    pixel_to_normalized,
    rectify_quad,
)
from physical_vision_image import OrientationTransform


def solid_rgb(size: tuple[int, int], color: tuple[int, int, int]) -> np.ndarray:
    array = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    array[:, :] = color
    return array


def test_default_geometry_config_is_frozen_versioned_policy() -> None:
    assert DEFAULT_GEOMETRY_CONFIG.version == "geometry-resource-policy-v1"
    assert DEFAULT_GEOMETRY_CONFIG.measurement_recipe_version == "raw-quality-recipe-v1"
    with pytest.raises(FrozenInstanceError):
        DEFAULT_GEOMETRY_CONFIG.version = "tampered"  # type: ignore[misc]


def test_geometry_config_rejects_unregistered_version() -> None:
    bad = GeometryConfig(
        version="geometry-resource-policy-v0",
        measurement_recipe_version="raw-quality-recipe-v1",
        max_image_pixels=4_000_000,
        max_roi_pixels=2_000_000,
        max_homography_condition_number=1_000.0,
        min_quad_area_normalized=1e-6,
        edge_contact_threshold_normalized=0.02,
        clipped_luminance_low=5.0,
        clipped_luminance_high=250.0,
        max_measure_seconds=2.0,
    )
    with pytest.raises(GeometryFailure) as raised:
        bad.validate()
    assert raised.value.code is GeometryFailureCode.CONFIG_VERSION_UNSUPPORTED
    assert raised.value.category == "unsupported-input"
    assert raised.value.message_key == "GEOMETRY_CONFIG_VERSION_UNSUPPORTED"
    text = " ".join(
        [
            raised.value.message_key,
            raised.value.category,
            raised.value.code.value,
            str(raised.value),
        ]
    )
    assert "SN-" not in text
    assert "serial" not in text.lower()
    assert b"\xff\xd8" not in text.encode()


@pytest.mark.parametrize(
    ("point", "size", "pixel"),
    (
        (NormalizedPoint(0.0, 0.0), (10, 20), (0, 0)),
        (NormalizedPoint(1.0, 1.0), (10, 20), (10, 20)),
        (NormalizedPoint(0.5, 0.25), (8, 8), (4, 2)),
        (NormalizedPoint(0.0, 1.0), (5, 7), (0, 7)),
        (NormalizedPoint(1.0, 0.0), (5, 7), (5, 0)),
    ),
)
def test_normalized_pixel_round_trip_at_corners_edges_and_interior(
    point: NormalizedPoint,
    size: tuple[int, int],
    pixel: tuple[int, int],
) -> None:
    px = normalized_to_pixel(point, size)
    assert px == pixel
    back = pixel_to_normalized(px, size)
    assert math.isclose(back.x, point.x, abs_tol=1e-12)
    assert math.isclose(back.y, point.y, abs_tol=1e-12)


def test_normalized_point_rejects_out_of_range() -> None:
    with pytest.raises(GeometryFailure) as raised:
        NormalizedPoint(1.5, 0.2)
    assert raised.value.code is GeometryFailureCode.COORDINATE_OUT_OF_RANGE


def test_normalized_box_pixel_bounds_are_half_open() -> None:
    box = NormalizedBox(0.0, 0.0, 0.5, 0.5)
    x0, y0, x1, y1 = box.to_pixel_bounds((10, 8))
    assert (x0, y0, x1, y1) == (0, 0, 5, 4)
    assert x1 - x0 == 5
    assert y1 - y0 == 4


def test_normalized_quad_rejects_non_finite_or_wrong_cardinality() -> None:
    with pytest.raises(GeometryFailure) as raised:
        NormalizedQuad(
            (
                NormalizedPoint(0.0, 0.0),
                NormalizedPoint(1.0, 0.0),
                NormalizedPoint(1.0, 1.0),
            )
        )
    assert raised.value.code is GeometryFailureCode.INVALID_GEOMETRY


@pytest.mark.parametrize("orientation", range(1, 9))
def test_source_canonical_pixel_composition_round_trips_exif_orientations(
    orientation: int,
) -> None:
    transform = OrientationTransform(orientation)
    size = (8, 8)
    lattice = (
        NormalizedPoint(0.0, 0.0),
        NormalizedPoint(1.0, 0.0),
        NormalizedPoint(0.0, 1.0),
        NormalizedPoint(1.0, 1.0),
        NormalizedPoint(0.25, 0.75),
        NormalizedPoint(0.5, 0.5),
    )
    for source in lattice:
        canonical = NormalizedPoint(*transform.source_to_canonical((source.x, source.y)))
        pixel = normalized_to_pixel(canonical, size)
        back_canonical = pixel_to_normalized(pixel, size)
        back_source = NormalizedPoint(
            *transform.canonical_to_source((back_canonical.x, back_canonical.y))
        )
        assert math.isclose(back_source.x, source.x, abs_tol=1e-12)
        assert math.isclose(back_source.y, source.y, abs_tol=1e-12)
        again = NormalizedPoint(*transform.canonical_to_source(canonical.as_tuple()))
        assert math.isclose(again.x, source.x, abs_tol=1e-12)
        assert math.isclose(again.y, source.y, abs_tol=1e-12)


def test_roi_box_crop_is_detached_from_source_mutation() -> None:
    source = solid_rgb((20, 10), (10, 20, 30))
    source[2:6, 4:12] = (200, 100, 50)
    box = NormalizedBox(0.2, 0.2, 0.6, 0.6)
    roi = extract_roi_box(source, box)
    assert roi.evidence_kind == "source_roi"
    assert roi.rectified is False
    assert roi.mode == "RGB"
    assert "_pixels" not in repr(roi)
    before = roi.to_rgb_array().copy()
    source[:, :] = 0
    after = roi.to_rgb_array()
    assert np.array_equal(before, after)
    assert before[0, 0].tolist() == [200, 100, 50]


def test_well_conditioned_quad_rectification_yields_expected_rectangle() -> None:
    canvas = solid_rgb((40, 30), (0, 0, 0))
    canvas[5:25, 8:32] = (255, 255, 255)
    quad = NormalizedQuad(
        (
            (8 / 40, 5 / 30),
            (32 / 40, 5 / 30),
            (32 / 40, 25 / 30),
            (8 / 40, 25 / 30),
        )
    )
    rectified = rectify_quad(canvas, quad, output_size=(24, 20))
    assert rectified.evidence_kind == "rectified_derivative"
    assert rectified.rectified is True
    assert rectified.source_quad is not None
    assert rectified.homography_condition_number is not None
    assert rectified.homography_condition_number < 100.0
    pixels = rectified.to_rgb_array()
    center = pixels[10, 12]
    assert all(int(channel) >= 240 for channel in center)


def test_degenerate_and_ill_conditioned_quads_are_rejected() -> None:
    canvas = solid_rgb((20, 20), (40, 40, 40))
    collinear = NormalizedQuad(((0.1, 0.1), (0.5, 0.1), (0.9, 0.1), (0.5, 0.1)))
    with pytest.raises(GeometryFailure) as raised:
        rectify_quad(canvas, collinear)
    assert raised.value.code in {
        GeometryFailureCode.QUAD_DEGENERATE,
        GeometryFailureCode.HOMOGRAPHY_ILL_CONDITIONED,
        GeometryFailureCode.INVALID_GEOMETRY,
    }

    skinny = NormalizedQuad(((0.1, 0.5), (0.9, 0.5), (0.9, 0.5001), (0.1, 0.5001)))
    with pytest.raises(GeometryFailure) as raised_skinny:
        rectify_quad(canvas, skinny)
    assert raised_skinny.value.code in {
        GeometryFailureCode.QUAD_DEGENERATE,
        GeometryFailureCode.HOMOGRAPHY_ILL_CONDITIONED,
    }

    with pytest.raises(GeometryFailure) as raised_oob:
        NormalizedPoint(-0.1, 0.5)
    assert raised_oob.value.code is GeometryFailureCode.COORDINATE_OUT_OF_RANGE


def test_raw_quality_features_respond_directionally_on_synthetic_pairs() -> None:
    # Checkerboard interior so ROI contains real edges for sharpness comparison.
    sharp = solid_rgb((32, 32), (0, 0, 0))
    for y in range(32):
        for x in range(32):
            if ((x // 4) + (y // 4)) % 2 == 0:
                sharp[y, x] = (255, 255, 255)
    blurred = cv2.GaussianBlur(sharp, (9, 9), 2.0)

    sharp_q = measure_raw_quality(sharp, NormalizedBox(0.25, 0.25, 0.75, 0.75))
    blur_q = measure_raw_quality(blurred, NormalizedBox(0.25, 0.25, 0.75, 0.75))
    assert sharp_q.blur.state == "measured"
    assert blur_q.blur.state == "measured"
    assert sharp_q.blur.value is not None and blur_q.blur.value is not None
    assert sharp_q.blur.value > blur_q.blur.value

    dark = solid_rgb((24, 24), (5, 5, 5))
    bright = solid_rgb((24, 24), (250, 250, 250))
    dark_q = measure_raw_quality(dark)
    bright_q = measure_raw_quality(bright)
    assert dark_q.exposure.value is not None and bright_q.exposure.value is not None
    assert bright_q.exposure.value > dark_q.exposure.value
    assert bright_q.extras["clipped_high_fraction"].value is not None
    assert dark_q.extras["clipped_low_fraction"].value is not None
    assert (
        bright_q.extras["clipped_high_fraction"].value
        > dark_q.extras["clipped_high_fraction"].value
    )
    assert (
        dark_q.extras["clipped_low_fraction"].value > bright_q.extras["clipped_low_fraction"].value
    )

    low_c = solid_rgb((24, 24), (120, 120, 120))
    high_c = solid_rgb((24, 24), (0, 0, 0))
    high_c[:, :12] = (255, 255, 255)
    low_q = measure_raw_quality(low_c)
    high_q = measure_raw_quality(high_c)
    assert high_q.contrast.value is not None and low_q.contrast.value is not None
    assert high_q.contrast.value > low_q.contrast.value

    centered = measure_raw_quality(sharp, NormalizedBox(0.25, 0.25, 0.75, 0.75))
    off = measure_raw_quality(sharp, NormalizedBox(0.0, 0.0, 0.4, 0.4))
    assert off.center.value is not None and centered.center.value is not None
    assert off.center.value > centered.center.value

    small = measure_raw_quality(sharp, NormalizedBox(0.4, 0.4, 0.55, 0.55))
    large = measure_raw_quality(sharp, NormalizedBox(0.1, 0.1, 0.9, 0.9))
    assert large.scale.value is not None and small.scale.value is not None
    assert large.scale.value > small.scale.value

    matte = solid_rgb((32, 32), (40, 80, 40))
    glare = solid_rgb((32, 32), (40, 80, 40))
    glare[10:22, 10:22] = (255, 255, 255)
    matte_q = measure_raw_quality(matte, NormalizedBox(0.3, 0.3, 0.7, 0.7))
    glare_q = measure_raw_quality(glare, NormalizedBox(0.3, 0.3, 0.7, 0.7))
    assert glare_q.glare.value is not None and matte_q.glare.value is not None
    assert glare_q.glare.value > matte_q.glare.value

    edge = measure_raw_quality(sharp, NormalizedBox(0.0, 0.2, 0.3, 0.8))
    inset = measure_raw_quality(sharp, NormalizedBox(0.2, 0.2, 0.8, 0.8))
    assert edge.crop.value is not None and inset.crop.value is not None
    assert edge.crop.value > inset.crop.value


def test_motion_is_not_determinable_for_single_still_unless_synthetic_labeled() -> None:
    image = solid_rgb((16, 16), (30, 30, 30))
    plain = measure_raw_quality(image)
    assert plain.motion.state == "not_determinable"
    assert plain.motion.value is None
    labeled = measure_raw_quality(image, synthetic_motion_label=True)
    assert labeled.motion.state == "unknown"
    assert labeled.motion.value is None
    assert plain.occlusion.state == "unknown"


def test_overlay_primitives_are_immutable_and_exif_consistent() -> None:
    box = NormalizedBox(0.1, 0.2, 0.4, 0.5)
    overlay = overlay_box_from_normalized(box)
    with pytest.raises(FrozenInstanceError):
        overlay.kind = "mutated"  # type: ignore[misc]
    quad = NormalizedQuad(((0.1, 0.1), (0.4, 0.1), (0.4, 0.4), (0.1, 0.4)))
    poly = overlay_polygon_from_quad(quad)
    assert len(poly.points) == 4
    arrow = overlay_arrow(NormalizedPoint(0.2, 0.5), NormalizedPoint(0.8, 0.5))
    assert isinstance(arrow, OverlayArrow)
    transform = OrientationTransform(6)
    source = NormalizedPoint(0.25, 0.75)
    canonical = canonicalize_overlay_point(source, transform)
    back = NormalizedPoint(*transform.canonical_to_source(canonical.as_tuple()))
    assert math.isclose(back.x, source.x, abs_tol=1e-12)
    assert math.isclose(back.y, source.y, abs_tol=1e-12)


def test_measure_deadline_and_cancellation_are_content_free() -> None:
    image = solid_rgb((8, 8), (1, 2, 3))
    with pytest.raises(GeometryFailure) as cancelled:
        measure_raw_quality(image, cancelled=lambda: True)
    assert cancelled.value.code is GeometryFailureCode.MEASURE_BUDGET_EXCEEDED
    assert cancelled.value.message_key == "GEOMETRY_MEASURE_CANCELLED"
    with pytest.raises(GeometryFailure) as deadline:
        measure_raw_quality(image, deadline=-1.0)
    assert deadline.value.code is GeometryFailureCode.MEASURE_BUDGET_EXCEEDED
    blob = " ".join(
        [
            cancelled.value.message_key,
            deadline.value.message_key,
            cancelled.value.category,
            deadline.value.category,
        ]
    )
    assert "SN-" not in blob
    assert "ocr" not in blob.lower()
    assert "serial" not in blob.lower()


def test_quality_dict_is_content_free() -> None:
    payload = measure_raw_quality(solid_rgb((12, 12), (9, 9, 9))).as_content_free_dict()
    text = repr(payload)
    assert "SN-" not in text
    assert "serial" not in text.lower()
    assert ".jpg" not in text.lower()


def test_perspective_proxy_measured_for_well_conditioned_quad() -> None:
    canvas = solid_rgb((40, 40), (20, 20, 20))
    canvas[10:30, 10:30] = (200, 200, 200)
    quad = NormalizedQuad(((0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)))
    measured = measure_raw_quality(canvas, quad)
    assert measured.perspective.state == "measured"
    assert measured.perspective.value is not None
    assert measured.perspective.value > 0.0
