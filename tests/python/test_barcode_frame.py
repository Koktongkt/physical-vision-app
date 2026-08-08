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

    assert DEFAULT_BARCODE_FRAME_CONFIG.version == "barcode-frame-ready-v1"
    with pytest.raises(FrozenInstanceError):
        DEFAULT_BARCODE_FRAME_CONFIG.version = "tampered"  # type: ignore[misc]


def test_blank_image_yields_none_without_injection() -> None:
    from physical_vision_barcode import BarcodeCountStatus, analyze_barcode_frame

    image = solid_rgb((160, 120), (180, 180, 180))
    evidence = analyze_barcode_frame(image)
    assert evidence.count_status is BarcodeCountStatus.NONE
    assert evidence.barcode_box is None
    assert evidence.recipe_version == "barcode-frame-ready-v1"
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
    from dataclasses import replace

    from physical_vision_barcode import (
        DEFAULT_BARCODE_FRAME_CONFIG,
        BarcodeFrameFailure,
        BarcodeFrameFailureCode,
    )

    bad = replace(DEFAULT_BARCODE_FRAME_CONFIG, version="barcode-frame-analyze-v0")
    with pytest.raises(BarcodeFrameFailure) as raised:
        bad.validate()
    assert raised.value.code is BarcodeFrameFailureCode.CONFIG_VERSION_UNSUPPORTED
    assert raised.value.message_key == "BARCODE_FRAME_CONFIG_VERSION_UNSUPPORTED"


def test_oversize_image_budget_fails_content_free() -> None:
    from dataclasses import replace

    from physical_vision_barcode import (
        DEFAULT_BARCODE_FRAME_CONFIG,
        BarcodeFrameFailure,
        BarcodeFrameFailureCode,
        analyze_barcode_frame,
    )

    tiny = replace(DEFAULT_BARCODE_FRAME_CONFIG, max_image_pixels=100)
    image = solid_rgb((40, 40), (1, 1, 1))
    with pytest.raises(BarcodeFrameFailure) as raised:
        analyze_barcode_frame(image, config=tiny)
    assert raised.value.code is BarcodeFrameFailureCode.IMAGE_BUDGET_EXCEEDED
    assert raised.value.category == "local-resource"
    assert "BARCODE_FRAME" in raised.value.message_key


# --- Stage 7 B23+B24: readiness gates + one-action guidance ---


def _sharp_barcode_roi(
    size: tuple[int, int],
    box: NormalizedBox,
    *,
    luma: int = 120,
) -> np.ndarray:
    """Fill image with mid-gray and paint a high-contrast bar pattern in ``box``."""
    image = solid_rgb(size, (luma, luma, luma))
    w, h = size
    x0 = int(box.x0 * w)
    y0 = int(box.y0 * h)
    x1 = max(x0 + 1, int(box.x1 * w))
    y1 = max(y0 + 1, int(box.y1 * h))
    x = x0
    toggle = True
    while x < x1:
        # Equal-width dark/light bands keep ROI exposure near mid-range.
        band = 3
        level = 30 if toggle else 200
        image[y0:y1, x : min(x + band, x1)] = level
        x += band
        toggle = not toggle
    return image


def test_none_count_is_abstain_with_no_action() -> None:
    from physical_vision_barcode import (
        BarcodeCountStatus,
        BarcodeGuidanceAction,
        BarcodeReadiness,
        analyze_barcode_frame,
    )

    def propose(_image, _config=None, **_kwargs):
        return _result(())

    evidence = analyze_barcode_frame(solid_rgb((120, 90), (50, 50, 50)), propose_regions=propose)
    assert evidence.count_status is BarcodeCountStatus.NONE
    assert evidence.readiness is BarcodeReadiness.ABSTAIN
    assert evidence.guidance_action is BarcodeGuidanceAction.NONE
    assert evidence.failing_gates == ()
    assert evidence.barcode_box is None


def test_multiple_count_is_abstain_with_no_action() -> None:
    from physical_vision_barcode import (
        BarcodeCountStatus,
        BarcodeGuidanceAction,
        BarcodeReadiness,
        analyze_barcode_frame,
    )

    a = NormalizedBox(0.1, 0.2, 0.4, 0.45)
    b = NormalizedBox(0.55, 0.2, 0.9, 0.45)

    def propose(_image, _config=None, **_kwargs):
        return _result((_proposal(a), _proposal(b)))

    evidence = analyze_barcode_frame(solid_rgb((200, 120), (30, 30, 30)), propose_regions=propose)
    assert evidence.count_status is BarcodeCountStatus.MULTIPLE
    assert evidence.readiness is BarcodeReadiness.ABSTAIN
    assert evidence.guidance_action is BarcodeGuidanceAction.NONE
    assert evidence.failing_gates == ()


def test_one_all_gates_pass_is_ready() -> None:
    from physical_vision_barcode import (
        BarcodeCountStatus,
        BarcodeGuidanceAction,
        BarcodeReadiness,
        analyze_barcode_frame,
    )

    # Centered large barcode-like region on 400x300 frame.
    box = NormalizedBox(0.2, 0.35, 0.8, 0.65)
    image = _sharp_barcode_roi((400, 300), box)

    def propose(_image, _config=None, **_kwargs):
        return _result((_proposal(box),))

    evidence = analyze_barcode_frame(image, propose_regions=propose)
    assert evidence.count_status is BarcodeCountStatus.ONE
    assert evidence.readiness is BarcodeReadiness.READY
    assert evidence.guidance_action is BarcodeGuidanceAction.NONE
    assert evidence.failing_gates == ()
    assert evidence.quality is not None
    assert evidence.quality.area_normalized >= 0.002
    assert evidence.recipe_version == "barcode-frame-ready-v1"


def test_one_tiny_area_guides_camera_closer() -> None:
    from dataclasses import replace

    from physical_vision_barcode import (
        DEFAULT_BARCODE_FRAME_CONFIG,
        BarcodeGuidanceAction,
        BarcodeReadiness,
        analyze_barcode_frame,
    )

    # Area 0.04*0.04 = 0.0016 < default min 0.002; short side may also fail but
    # min_area is first in priority → camera_closer.
    box = NormalizedBox(0.48, 0.48, 0.52, 0.52)
    image = _sharp_barcode_roi((400, 400), box)
    config = replace(DEFAULT_BARCODE_FRAME_CONFIG, min_short_side_px=1)

    def propose(_image, _config=None, **_kwargs):
        return _result((_proposal(box),))

    evidence = analyze_barcode_frame(image, config=config, propose_regions=propose)
    assert evidence.readiness is BarcodeReadiness.GUIDANCE
    assert evidence.guidance_action is BarcodeGuidanceAction.CAMERA_CLOSER
    assert "min_area" in evidence.failing_gates
    assert evidence.failing_gates[0] == "min_area"


def test_one_clipped_left_guides_camera_right() -> None:
    from dataclasses import replace

    from physical_vision_barcode import (
        DEFAULT_BARCODE_FRAME_CONFIG,
        BarcodeGuidanceAction,
        BarcodeReadiness,
        analyze_barcode_frame,
    )

    # Left edge at 0.0 → margin_left fails; keep area/short-side/blur healthy.
    box = NormalizedBox(0.0, 0.35, 0.55, 0.65)
    image = _sharp_barcode_roi((400, 300), box)
    config = replace(
        DEFAULT_BARCODE_FRAME_CONFIG,
        min_area_normalized=0.001,
        min_short_side_px=10,
        min_laplacian_variance=1.0,
    )

    def propose(_image, _config=None, **_kwargs):
        return _result((_proposal(box),))

    evidence = analyze_barcode_frame(image, config=config, propose_regions=propose)
    assert evidence.readiness is BarcodeReadiness.GUIDANCE
    assert evidence.guidance_action is BarcodeGuidanceAction.CAMERA_RIGHT
    assert "margin_left" in evidence.failing_gates
    # Exactly one action enum (not a list of actions).
    assert isinstance(evidence.guidance_action, BarcodeGuidanceAction)


def test_one_low_blur_guides_camera_steady() -> None:
    from dataclasses import replace

    from physical_vision_barcode import (
        DEFAULT_BARCODE_FRAME_CONFIG,
        BarcodeGuidanceAction,
        BarcodeReadiness,
        analyze_barcode_frame,
    )

    box = NormalizedBox(0.2, 0.35, 0.8, 0.65)
    # Uniform ROI → near-zero Laplacian variance.
    image = solid_rgb((400, 300), (128, 128, 128))
    config = replace(
        DEFAULT_BARCODE_FRAME_CONFIG,
        min_area_normalized=0.001,
        min_short_side_px=10,
        min_laplacian_variance=50.0,
        min_aspect_ratio=0.1,
        max_aspect_ratio=100.0,
    )

    def propose(_image, _config=None, **_kwargs):
        return _result((_proposal(box),))

    evidence = analyze_barcode_frame(image, config=config, propose_regions=propose)
    assert evidence.readiness is BarcodeReadiness.GUIDANCE
    assert evidence.guidance_action is BarcodeGuidanceAction.CAMERA_STEADY
    assert "blur" in evidence.failing_gates


def test_guidance_never_returns_two_actions() -> None:
    from dataclasses import replace

    from physical_vision_barcode import (
        DEFAULT_BARCODE_FRAME_CONFIG,
        BarcodeGuidanceAction,
        BarcodeReadiness,
        analyze_barcode_frame,
    )

    # Tiny + left-clipped → multiple gates fail, still one dominant action.
    box = NormalizedBox(0.0, 0.48, 0.03, 0.52)
    image = solid_rgb((300, 300), (100, 100, 100))
    config = replace(DEFAULT_BARCODE_FRAME_CONFIG, min_laplacian_variance=1.0)

    def propose(_image, _config=None, **_kwargs):
        return _result((_proposal(box),))

    evidence = analyze_barcode_frame(image, config=config, propose_regions=propose)
    assert evidence.readiness is BarcodeReadiness.GUIDANCE
    assert evidence.guidance_action is not BarcodeGuidanceAction.NONE
    # Single enum value — not a collection of actions.
    assert type(evidence.guidance_action) is BarcodeGuidanceAction
    assert evidence.guidance_action is not BarcodeGuidanceAction.NONE


def test_priority_picks_higher_gate_when_two_fail() -> None:
    from dataclasses import replace

    from physical_vision_barcode import (
        DEFAULT_BARCODE_FRAME_CONFIG,
        BarcodeGuidanceAction,
        BarcodeReadiness,
        analyze_barcode_frame,
    )

    # Fails min_area (priority) and margin_left; dominant must be min_area → closer.
    box = NormalizedBox(0.0, 0.49, 0.02, 0.51)
    image = _sharp_barcode_roi((500, 500), box)
    config = replace(
        DEFAULT_BARCODE_FRAME_CONFIG,
        min_area_normalized=0.01,
        min_short_side_px=1,
        min_laplacian_variance=0.0,
        min_aspect_ratio=0.01,
        max_aspect_ratio=1000.0,
    )

    def propose(_image, _config=None, **_kwargs):
        return _result((_proposal(box),))

    evidence = analyze_barcode_frame(image, config=config, propose_regions=propose)
    assert evidence.readiness is BarcodeReadiness.GUIDANCE
    assert evidence.failing_gates[0] == "min_area"
    assert evidence.guidance_action is BarcodeGuidanceAction.CAMERA_CLOSER
    assert "margin_left" in evidence.failing_gates


def test_evidence_json_and_repr_have_no_payload_fields_with_readiness() -> None:
    from physical_vision_barcode import analyze_barcode_frame

    box = NormalizedBox(0.2, 0.35, 0.8, 0.65)
    image = _sharp_barcode_roi((400, 300), box)

    def propose(_image, _config=None, **_kwargs):
        return _result((_proposal(box),))

    evidence = analyze_barcode_frame(image, propose_regions=propose)
    text = repr(evidence).lower()
    assert "payload" not in text
    assert "decoded" not in text
    fields = getattr(evidence, "__dataclass_fields__", {})
    for banned in ("payload", "decoded", "raw_string", "serial"):
        assert banned not in fields
        assert not any(banned in name.lower() for name in fields)


def test_ready_gate_config_version_is_ready_v1() -> None:
    from physical_vision_barcode import DEFAULT_BARCODE_FRAME_CONFIG

    assert DEFAULT_BARCODE_FRAME_CONFIG.version == "barcode-frame-ready-v1"
    assert DEFAULT_BARCODE_FRAME_CONFIG.gate_priority[0] == "min_area"
