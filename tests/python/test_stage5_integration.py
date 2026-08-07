from __future__ import annotations

import json
from io import BytesIO

import numpy as np
from physical_vision_geometry import extract_roi_box
from physical_vision_image import DEFAULT_DECODE_CONFIG, decode_image
from physical_vision_localization import (
    LocalizationOutcome,
    ProposalKind,
    propose_classical_regions,
    select_localization_summary,
)
from physical_vision_ocr import OcrUsability, run_ocr_baseline
from PIL import Image


def _encode_png(array: np.ndarray) -> bytes:
    buffer = BytesIO()
    Image.fromarray(array, mode="RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _synthetic_label_scene() -> np.ndarray:
    """Synthetic high-contrast label with barcode-like bars and a text band."""
    image = np.full((240, 360, 3), 40, dtype=np.uint8)
    # label plate
    image[40:200, 40:320] = 245
    # text band (filled glyphs later as dark blocks forming a pseudo line)
    image[55:95, 60:300] = 255
    # simple block digits "0 1" as rectangles — OCR stubbed in unit path; geometry path only here
    image[60:90, 80:100] = 0
    image[60:90, 120:130] = 0
    image[85:90, 80:130] = 0
    # barcode-like vertical bars
    x = 60
    toggle = True
    while x < 300:
        width = 2 if toggle else 3
        image[120:180, x : min(x + width, 300)] = 0 if toggle else 255
        x += width
        toggle = not toggle
    return image


class _StubOcr:
    def run(self, image: np.ndarray, config) -> str:  # noqa: ANN001
        assert image.ndim == 3
        return "00123"


def test_decode_propose_roi_ocr_smoke_end_to_end() -> None:
    scene = _synthetic_label_scene()
    encoded = _encode_png(scene)
    canonical = decode_image(encoded, DEFAULT_DECODE_CONFIG)
    assert canonical.mode == "RGB"

    array = np.frombuffer(canonical.to_pillow().tobytes(), dtype=np.uint8).reshape(
        canonical.canonical_size[1], canonical.canonical_size[0], 3
    )
    localization = propose_classical_regions(array, orientation_transform=canonical.transform)
    assert localization.recipe_version == "classical-localization-recipe-v1"
    summary = select_localization_summary(localization)
    assert summary.outcome in {
        LocalizationOutcome.TRUSTWORTHY,
        LocalizationOutcome.MULTIPLE_LABELS,
        LocalizationOutcome.UNCERTAIN,
    }
    # Prefer barcode or label box for ROI
    box = None
    if summary.primary is not None and summary.primary.box is not None:
        box = summary.primary.box
    else:
        for proposal in localization.proposals:
            if proposal.box is not None and proposal.kind in {
                ProposalKind.BARCODE_LANDMARK,
                ProposalKind.LABEL_REGION,
                ProposalKind.TEXT_REGION,
            }:
                box = proposal.box
                break
    assert box is not None, f"expected a proposal box, outcome={localization.outcome}"

    roi = extract_roi_box(array, box)
    assert roi.width * roi.height > 0
    evidence = run_ocr_baseline(roi, engine=_StubOcr())
    assert evidence.raw_string == "00123"
    assert evidence.usability is OcrUsability.USABLE
    assert evidence.recipe_version == "paddleocr-baseline-v1"

    # Content-free metrics shape for experiment harness consumers
    metrics = {
        "localization_outcome": localization.outcome.value,
        "proposal_count": len(localization.proposals),
        "proposal_kinds": sorted({p.kind.value for p in localization.proposals}),
        "roi_width": roi.width,
        "roi_height": roi.height,
        "ocr_usability": evidence.usability.value,
        "ocr_raw_length": len(evidence.raw_string),
        "ocr_elapsed_ms": evidence.elapsed_ms,
        "localization_elapsed_ms": localization.elapsed_ms,
    }
    serialized = json.dumps(metrics)
    assert "00123" not in serialized  # metrics stay content-free by policy in harness path
    assert metrics["proposal_count"] >= 1
    assert metrics["ocr_raw_length"] == 5
