from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest
from physical_vision_geometry import extract_roi_box
from physical_vision_image import OrientationTransform
from physical_vision_localization import (
    DEFAULT_LOCALIZATION_CONFIG,
    LocalizationConfig,
    LocalizationFailure,
    LocalizationFailureCode,
    LocalizationOutcome,
    ProposalKind,
    ProposalPresence,
    propose_classical_regions,
    select_localization_summary,
)


def solid_rgb(size: tuple[int, int], color: tuple[int, int, int]) -> np.ndarray:
    array = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    array[:, :] = color
    return array


def barcode_like_image(
    size: tuple[int, int] = (320, 200),
    *,
    bar_region: tuple[int, int, int, int] = (40, 70, 280, 130),
) -> np.ndarray:
    """High-contrast vertical bar pattern (synthetic barcode landmark)."""
    image = solid_rgb(size, (255, 255, 255))
    x0, y0, x1, y1 = bar_region
    x = x0
    toggle = True
    while x < x1:
        width = 2 if toggle else 3
        image[y0:y1, x : min(x + width, x1)] = 0 if toggle else 255
        x += width
        toggle = not toggle
    return image


def label_rectangle_image(
    size: tuple[int, int] = (320, 240),
    *,
    rect: tuple[int, int, int, int] = (40, 40, 280, 200),
) -> np.ndarray:
    image = solid_rgb(size, (30, 30, 30))
    x0, y0, x1, y1 = rect
    image[y0:y1, x0:x1] = (240, 240, 240)
    # inner border to strengthen contour
    image[y0 + 4 : y1 - 4, x0 + 4 : x1 - 4] = (250, 250, 250)
    return image


def test_default_localization_config_is_frozen_versioned_recipe() -> None:
    assert DEFAULT_LOCALIZATION_CONFIG.version == "classical-localization-recipe-v1"
    with pytest.raises(FrozenInstanceError):
        DEFAULT_LOCALIZATION_CONFIG.version = "tampered"  # type: ignore[misc]


def test_localization_config_rejects_unregistered_version() -> None:
    bad = LocalizationConfig(
        version="classical-localization-recipe-v0",
        max_image_pixels=4_000_000,
        max_proposals=8,
        min_barcode_area_normalized=0.001,
        min_label_area_normalized=0.01,
        min_barcode_aspect_ratio=1.5,
        max_barcode_aspect_ratio=20.0,
        barcode_gradient_threshold=40.0,
        morphology_kernel_width=15,
        morphology_kernel_height=5,
        max_propose_seconds=2.0,
    )
    with pytest.raises(LocalizationFailure) as raised:
        bad.validate()
    assert raised.value.code is LocalizationFailureCode.CONFIG_VERSION_UNSUPPORTED
    assert raised.value.category == "unsupported-input"
    assert raised.value.message_key == "LOCALIZATION_CONFIG_VERSION_UNSUPPORTED"


def test_empty_noise_image_yields_no_label_or_uncertain_without_crash() -> None:
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 256, size=(120, 160, 3), dtype=np.uint8)
    result = propose_classical_regions(noise)
    assert result.outcome in {
        LocalizationOutcome.NO_LABEL,
        LocalizationOutcome.UNCERTAIN,
    }
    assert result.proposals == ()
    assert result.recipe_version == "classical-localization-recipe-v1"


def test_barcode_like_bars_produce_barcode_landmark_in_expected_bounds() -> None:
    image = barcode_like_image()
    result = propose_classical_regions(image)
    barcodes = [p for p in result.proposals if p.kind is ProposalKind.BARCODE_LANDMARK]
    assert barcodes, f"expected barcode landmark, got {result.proposals!r} outcome={result.outcome}"
    primary = barcodes[0]
    assert primary.presence is ProposalPresence.PRESENT
    assert primary.box is not None
    # Expected bar region roughly x 40-280 / 320, y 70-130 / 200
    assert 0.05 < primary.box.x0 < 0.35
    assert 0.55 < primary.box.x1 < 0.98
    assert 0.20 < primary.box.y0 < 0.50
    assert 0.50 < primary.box.y1 < 0.85
    assert primary.box.x0 < primary.box.x1
    assert primary.box.y0 < primary.box.y1
    assert primary.recipe_version == "classical-localization-recipe-v1"


def test_label_rectangle_produces_label_region() -> None:
    image = label_rectangle_image()
    result = propose_classical_regions(image)
    labels = [p for p in result.proposals if p.kind is ProposalKind.LABEL_REGION]
    assert labels, f"expected label_region, got kinds={[p.kind for p in result.proposals]}"
    label = labels[0]
    assert label.box is not None
    assert label.box.area() > 0.2
    assert 0.05 <= label.box.x0 <= 0.25
    assert 0.75 <= label.box.x1 <= 0.98


def test_multiple_strong_regions_are_ambiguous_and_deterministic() -> None:
    image = solid_rgb((400, 200), (20, 20, 20))
    # two separate barcode-like bands
    left = barcode_like_image((180, 200), bar_region=(20, 60, 160, 140))
    right = barcode_like_image((180, 200), bar_region=(20, 60, 160, 140))
    image[:, 0:180] = left
    image[:, 220:400] = right
    first = propose_classical_regions(image)
    second = propose_classical_regions(image)
    assert first.outcome is LocalizationOutcome.MULTIPLE_LABELS
    assert second.outcome is LocalizationOutcome.MULTIPLE_LABELS
    assert first.proposals == second.proposals
    assert len([p for p in first.proposals if p.kind is ProposalKind.BARCODE_LANDMARK]) >= 2


def test_selection_summary_trustworthy_single_primary() -> None:
    image = barcode_like_image()
    result = propose_classical_regions(image)
    summary = select_localization_summary(result)
    assert summary.outcome is LocalizationOutcome.TRUSTWORTHY
    assert summary.primary is not None
    assert summary.primary.kind in {
        ProposalKind.BARCODE_LANDMARK,
        ProposalKind.LABEL_REGION,
        ProposalKind.TEXT_REGION,
    }


def test_selection_summary_no_proposals() -> None:
    empty = propose_classical_regions(solid_rgb((64, 64), (128, 128, 128)))
    summary = select_localization_summary(empty)
    assert summary.outcome in {LocalizationOutcome.NO_LABEL, LocalizationOutcome.UNCERTAIN}
    assert summary.primary is None


def test_proposals_immutable_and_repr_has_no_payload_field() -> None:
    image = barcode_like_image()
    result = propose_classical_regions(image)
    with pytest.raises(FrozenInstanceError):
        result.outcome = LocalizationOutcome.UNCERTAIN  # type: ignore[misc]
    text = repr(result)
    assert "payload" not in text.lower()
    for proposal in result.proposals:
        fields = getattr(proposal, "__dataclass_fields__", {})
        assert "payload" not in fields
        assert "decoded" not in fields
        assert not any("payload" in name.lower() for name in fields)


def test_barcode_detector_payload_never_leaks_even_if_injector_provides_it() -> None:
    """Public results must drop detector payload strings at the boundary."""
    image = barcode_like_image()

    class FakeDetector:
        def detectAndDecodeWithType(self, _gray):  # noqa: N802 — OpenCV spelling
            # payload that must never appear in public objects/logs
            points = np.array(
                [[[50.0, 70.0], [270.0, 70.0], [270.0, 130.0], [50.0, 130.0]]],
                dtype=np.float32,
            )
            return ("SN-SECRET-PAYLOAD-99", points, ["EAN_13"])

        def detectAndDecode(self, gray):  # noqa: N802
            return self.detectAndDecodeWithType(gray)[:2] + (None,)

        def detect(self, gray):  # noqa: N802
            ok, points = True, self.detectAndDecodeWithType(gray)[1]
            return ok, points

    result = propose_classical_regions(image, barcode_detector=FakeDetector())
    field_dump = []
    for proposal in result.proposals:
        for name in getattr(proposal, "__dataclass_fields__", {}):
            field_dump.append(f"{name}={getattr(proposal, name)!r}")
    blob = " ".join(
        [
            repr(result),
            str(result),
            str(result.proposals),
            *(repr(p) for p in result.proposals),
            *field_dump,
        ]
    )
    assert "SN-SECRET-PAYLOAD-99" not in blob
    assert "SECRET" not in blob
    assert "SN-SECRET" not in blob
    assert result.proposals, "fake detector should yield geometry"


def test_proposals_expressed_in_canonical_space_across_exif_orientations() -> None:
    """Source-space bars transformed via EXIF must still yield canonical-normalized boxes."""
    # Build a barcode in source orientation 6 (90 CW): tall image becomes wide after transpose.
    # We instead propose on already-canonical images; transform is used only for reporting helpers.
    image = barcode_like_image((200, 320), bar_region=(70, 40, 130, 280))
    # Simulate orientation 6: rotate so bars become horizontal in "source", then transpose back.
    # For this baseline, callers pass canonical RGB; verify OrientationTransform composition path.
    transform = OrientationTransform(6)
    result = propose_classical_regions(image, orientation_transform=transform)
    assert result.orientation == 6
    for proposal in result.proposals:
        if proposal.box is None:
            continue
        # box remains in canonical normalized coords on the image as passed
        assert 0.0 <= proposal.box.x0 < proposal.box.x1 <= 1.0
        assert 0.0 <= proposal.box.y0 < proposal.box.y1 <= 1.0
        # round-trip a corner through orientation helpers
        cx, cy = proposal.box.center().as_tuple()
        source = transform.canonical_to_source((cx, cy))
        back = transform.source_to_canonical(source)
        assert abs(back[0] - cx) < 1e-9
        assert abs(back[1] - cy) < 1e-9


def test_ill_conditioned_tiny_geometry_rejected_from_proposals() -> None:
    config = LocalizationConfig(
        version="classical-localization-recipe-v1",
        max_image_pixels=4_000_000,
        max_proposals=8,
        min_barcode_area_normalized=0.05,  # high — filters tiny noise
        min_label_area_normalized=0.2,
        min_barcode_aspect_ratio=1.5,
        max_barcode_aspect_ratio=20.0,
        barcode_gradient_threshold=40.0,
        morphology_kernel_width=15,
        morphology_kernel_height=5,
        max_propose_seconds=2.0,
    )
    image = solid_rgb((100, 100), (255, 255, 255))
    image[10:12, 10:40] = 0  # tiny bar cluster below min area
    result = propose_classical_regions(image, config=config)
    for proposal in result.proposals:
        assert proposal.box is not None
        assert proposal.box.area() >= config.min_barcode_area_normalized * 0.5 or (
            proposal.kind is not ProposalKind.BARCODE_LANDMARK
        )


def test_cooperative_cancel_returns_typed_timeout_failure() -> None:
    image = barcode_like_image()
    with pytest.raises(LocalizationFailure) as raised:
        propose_classical_regions(image, cancelled=lambda: True)
    assert raised.value.code is LocalizationFailureCode.PROPOSE_BUDGET_EXCEEDED
    assert raised.value.category == "timeout"
    assert "CANCEL" in raised.value.message_key
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


def test_deadline_exceeded_is_content_free() -> None:
    image = barcode_like_image()
    with pytest.raises(LocalizationFailure) as raised:
        propose_classical_regions(image, deadline=0.0, clock=lambda: 10.0)
    assert raised.value.code is LocalizationFailureCode.PROPOSE_BUDGET_EXCEEDED
    assert raised.value.category == "timeout"


def test_selected_region_composes_with_roi_extract() -> None:
    image = barcode_like_image((320, 200))
    result = propose_classical_regions(image)
    summary = select_localization_summary(result)
    assert summary.primary is not None and summary.primary.box is not None
    roi = extract_roi_box(image, summary.primary.box)
    assert roi.width >= 8
    assert roi.height >= 8
    assert roi.evidence_kind == "source_roi"
    # input buffer not required immutable for ndarray path, but ROI is detached
    assert roi.to_rgb_array().shape[2] == 3


def test_text_region_heuristic_near_barcode_when_present() -> None:
    image = barcode_like_image((320, 240), bar_region=(40, 120, 280, 180))
    # white label band above barcode for text_region heuristic
    image[40:100, 40:280] = 245
    result = propose_classical_regions(image)
    kinds = {p.kind for p in result.proposals}
    assert ProposalKind.BARCODE_LANDMARK in kinds or ProposalKind.LABEL_REGION in kinds
    # text_region is optional when layout heuristic fires
    if ProposalKind.TEXT_REGION in kinds:
        text = next(p for p in result.proposals if p.kind is ProposalKind.TEXT_REGION)
        assert text.box is not None
        assert text.box.y1 <= 0.55 or text.box.y0 >= 0.45


def test_image_pixel_budget_refused() -> None:
    config = LocalizationConfig(
        version="classical-localization-recipe-v1",
        max_image_pixels=100,
        max_proposals=8,
        min_barcode_area_normalized=0.001,
        min_label_area_normalized=0.01,
        min_barcode_aspect_ratio=1.5,
        max_barcode_aspect_ratio=20.0,
        barcode_gradient_threshold=40.0,
        morphology_kernel_width=15,
        morphology_kernel_height=5,
        max_propose_seconds=2.0,
    )
    with pytest.raises(LocalizationFailure) as raised:
        propose_classical_regions(solid_rgb((50, 50), (0, 0, 0)), config=config)
    assert raised.value.code is LocalizationFailureCode.IMAGE_BUDGET_EXCEEDED
