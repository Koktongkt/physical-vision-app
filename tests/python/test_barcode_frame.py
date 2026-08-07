from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest
from physical_vision_geometry import NormalizedBox
from physical_vision_localization import (
    LocalizationOutcome,
    LocalizationResult,
    ProposalKind,
    ProposalPresence,
    RegionProposal,
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


def _proposal(
    box: NormalizedBox,
    *,
    source: str = "inject_test",
    score: float = 0.9,
) -> RegionProposal:
    return RegionProposal(
        kind=ProposalKind.BARCODE_LANDMARK,
        presence=ProposalPresence.PRESENT,
        box=box,
        quad=None,
        score=score,
        recipe_version="classical-localization-recipe-v1",
        source=source,
    )


def _label_proposal(box: NormalizedBox) -> RegionProposal:
    return RegionProposal(
        kind=ProposalKind.LABEL_REGION,
        presence=ProposalPresence.PRESENT,
        box=box,
        quad=None,
        score=0.5,
        recipe_version="classical-localization-recipe-v1",
        source="label_contour",
    )


def _result(proposals: tuple[RegionProposal, ...]) -> LocalizationResult:
    barcodes = [p for p in proposals if p.kind is ProposalKind.BARCODE_LANDMARK]
    if len(barcodes) == 0:
        outcome = LocalizationOutcome.NO_LABEL
    elif len(barcodes) == 1:
        outcome = LocalizationOutcome.TRUSTWORTHY
    else:
        outcome = LocalizationOutcome.MULTIPLE_LABELS
    return LocalizationResult(
        outcome=outcome,
        proposals=proposals,
        recipe_version="classical-localization-recipe-v1",
        orientation=1,
        elapsed_ms=1.0,
        notes=(),
    )


def test_default_barcode_frame_config_is_frozen_versioned_recipe() -> None:
    from physical_vision_barcode import DEFAULT_BARCODE_FRAME_CONFIG

    assert DEFAULT_BARCODE_FRAME_CONFIG.version == "barcode-frame-analyze-v1"
    with pytest.raises(FrozenInstanceError):
        DEFAULT_BARCODE_FRAME_CONFIG.version = "tampered"  # type: ignore[misc]


def test_blank_image_yields_none_without_injection() -> None:
    from physical_vision_barcode import BarcodeCountStatus, analyze_barcode_frame

    image = solid_rgb((160, 120), (180, 180, 180))
    evidence = analyze_barcode_frame(image)
    assert evidence.count_status is BarcodeCountStatus.NONE
    assert evidence.barcode_box is None
    assert evidence.recipe_version == "barcode-frame-analyze-v1"
    assert evidence.elapsed_ms >= 0.0


def test_one_injected_box_yields_one_and_box_coords() -> None:
    from physical_vision_barcode import BarcodeCountStatus, analyze_barcode_frame

    box = NormalizedBox(0.1, 0.2, 0.8, 0.5)

    def propose(_image, _config=None, **_kwargs):
        return _result((_proposal(box, source="opencv_barcode_detect"),))

    evidence = analyze_barcode_frame(solid_rgb((100, 80), (10, 10, 10)), propose_regions=propose)
    assert evidence.count_status is BarcodeCountStatus.ONE
    assert evidence.barcode_box is not None
    assert evidence.barcode_box.x0 == pytest.approx(0.1)
    assert evidence.barcode_box.y0 == pytest.approx(0.2)
    assert evidence.barcode_box.x1 == pytest.approx(0.8)
    assert evidence.barcode_box.y1 == pytest.approx(0.5)
    assert "opencv_barcode_detect" in evidence.proposal_sources


def test_two_injected_boxes_yield_multiple_and_box_is_none() -> None:
    from physical_vision_barcode import BarcodeCountStatus, analyze_barcode_frame

    a = NormalizedBox(0.05, 0.1, 0.4, 0.4)
    b = NormalizedBox(0.55, 0.1, 0.95, 0.4)

    def propose(_image, _config=None, **_kwargs):
        return _result(
            (
                _proposal(a, source="morph_barcode"),
                _proposal(b, source="opencv_barcode_detect"),
            )
        )

    evidence = analyze_barcode_frame(solid_rgb((200, 100), (0, 0, 0)), propose_regions=propose)
    assert evidence.count_status is BarcodeCountStatus.MULTIPLE
    assert evidence.barcode_box is None
    assert set(evidence.proposal_sources) >= {"morph_barcode", "opencv_barcode_detect"}


def test_label_only_proposals_do_not_count_as_barcode() -> None:
    from physical_vision_barcode import BarcodeCountStatus, analyze_barcode_frame

    def propose(_image, _config=None, **_kwargs):
        return _result((_label_proposal(NormalizedBox(0.1, 0.1, 0.9, 0.9)),))

    evidence = analyze_barcode_frame(solid_rgb((80, 80), (40, 40, 40)), propose_regions=propose)
    assert evidence.count_status is BarcodeCountStatus.NONE
    assert evidence.barcode_box is None


def test_evidence_immutable_and_repr_has_no_payload_fields() -> None:
    from physical_vision_barcode import BarcodeCountStatus, analyze_barcode_frame

    box = NormalizedBox(0.2, 0.3, 0.7, 0.6)

    def propose(_image, _config=None, **_kwargs):
        return _result((_proposal(box),))

    evidence = analyze_barcode_frame(solid_rgb((64, 64), (0, 0, 0)), propose_regions=propose)
    with pytest.raises(FrozenInstanceError):
        evidence.count_status = BarcodeCountStatus.NONE  # type: ignore[misc]
    text = repr(evidence)
    assert "payload" not in text.lower()
    assert "decoded" not in text.lower()
    fields = getattr(evidence, "__dataclass_fields__", {})
    assert "payload" not in fields
    assert "decoded" not in fields
    assert "raw_string" not in fields
    assert not any("serial" in name.lower() for name in fields)


def test_image_buffer_not_mutated() -> None:
    from physical_vision_barcode import analyze_barcode_frame

    image = solid_rgb((96, 64), (90, 90, 90))
    before = image.copy()

    def propose(_image, _config=None, **_kwargs):
        return _result(())

    analyze_barcode_frame(image, propose_regions=propose)
    assert np.array_equal(image, before)


def test_barcode_like_synthetic_may_find_one_via_classical_path() -> None:
    """Classical path should find the synthetic bar pattern (Stage 5 fixture)."""
    from physical_vision_barcode import BarcodeCountStatus, analyze_barcode_frame

    evidence = analyze_barcode_frame(barcode_like_image())
    assert evidence.count_status is BarcodeCountStatus.ONE
    assert evidence.barcode_box is not None
    assert evidence.barcode_box.x0 < evidence.barcode_box.x1
    assert any(
        src.startswith("opencv") or src.startswith("morph") for src in evidence.proposal_sources
    )


def test_config_rejects_unregistered_version() -> None:
    from physical_vision_barcode import (
        BarcodeFrameConfig,
        BarcodeFrameFailure,
        BarcodeFrameFailureCode,
    )

    bad = BarcodeFrameConfig(
        version="barcode-frame-analyze-v0",
        max_image_pixels=1_000_000,
        max_analyze_seconds=1.0,
        localization_config_version="classical-localization-recipe-v1",
    )
    with pytest.raises(BarcodeFrameFailure) as raised:
        bad.validate()
    assert raised.value.code is BarcodeFrameFailureCode.CONFIG_VERSION_UNSUPPORTED
    assert raised.value.message_key == "BARCODE_FRAME_CONFIG_VERSION_UNSUPPORTED"


def test_oversize_image_budget_fails_content_free() -> None:
    from physical_vision_barcode import (
        DEFAULT_BARCODE_FRAME_CONFIG,
        BarcodeFrameConfig,
        BarcodeFrameFailure,
        BarcodeFrameFailureCode,
        analyze_barcode_frame,
    )

    tiny = BarcodeFrameConfig(
        version=DEFAULT_BARCODE_FRAME_CONFIG.version,
        max_image_pixels=100,
        max_analyze_seconds=2.0,
        localization_config_version=DEFAULT_BARCODE_FRAME_CONFIG.localization_config_version,
    )
    image = solid_rgb((40, 40), (1, 1, 1))
    with pytest.raises(BarcodeFrameFailure) as raised:
        analyze_barcode_frame(image, config=tiny)
    assert raised.value.code is BarcodeFrameFailureCode.IMAGE_BUDGET_EXCEEDED
    assert raised.value.category == "local-resource"
    assert "BARCODE_FRAME" in raised.value.message_key
