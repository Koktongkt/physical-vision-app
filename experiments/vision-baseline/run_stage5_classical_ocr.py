#!/usr/bin/env python3
"""Experiment-only Stage 5 harness: decode → classical localize → ROI → OCR baseline.

Emits content-free JSON metrics by default (timings, counts, enums, string lengths).
Not a production API endpoint.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

# Repo-local packages are not installed as site packages; mirror pytest pythonpath.
_ROOT = Path(__file__).resolve().parents[2]
_VISION = _ROOT / "packages" / "vision" / "python"
if str(_VISION) not in sys.path:
    sys.path.insert(0, str(_VISION))

from physical_vision_geometry import extract_roi_box  # noqa: E402
from physical_vision_image import DEFAULT_DECODE_CONFIG, decode_image  # noqa: E402
from physical_vision_localization import (  # noqa: E402
    propose_classical_regions,
    select_localization_summary,
)
from physical_vision_ocr import OcrFailure, OcrFailureCode, run_tesseract_baseline  # noqa: E402


def _synthetic_scene() -> np.ndarray:
    image = np.full((240, 360, 3), 40, dtype=np.uint8)
    image[40:200, 40:320] = 245
    image[55:95, 60:300] = 255
    x = 60
    toggle = True
    while x < 300:
        width = 2 if toggle else 3
        image[120:180, x : min(x + width, 300)] = 0 if toggle else 255
        x += width
        toggle = not toggle
    return image


def _load_rgb(path: Path | None) -> np.ndarray:
    if path is None:
        return _synthetic_scene()
    encoded = path.read_bytes()
    if len(encoded) > DEFAULT_DECODE_CONFIG.max_encoded_bytes:
        raise SystemExit("input exceeds decode encoded-byte budget")
    canonical = decode_image(encoded, DEFAULT_DECODE_CONFIG)
    return np.frombuffer(canonical.to_pillow().tobytes(), dtype=np.uint8).reshape(
        canonical.canonical_size[1], canonical.canonical_size[0], 3
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image",
        type=Path,
        default=None,
        help="Optional PNG/JPEG path (synthetic fixture used when omitted)",
    )
    parser.add_argument(
        "--skip-ocr",
        action="store_true",
        help="Run localization only",
    )
    parser.add_argument(
        "--include-raw-length-only",
        action="store_true",
        default=True,
        help="Kept for clarity: metrics never include raw OCR strings",
    )
    args = parser.parse_args(argv)

    array = _load_rgb(args.image)
    localization = propose_classical_regions(array)
    summary = select_localization_summary(localization)

    metrics: dict = {
        "localization_outcome": localization.outcome.value,
        "summary_outcome": summary.outcome.value,
        "proposal_count": len(localization.proposals),
        "proposal_kinds": sorted({p.kind.value for p in localization.proposals}),
        "localization_elapsed_ms": localization.elapsed_ms,
        "recipe_localization": localization.recipe_version,
        "has_primary": summary.primary is not None,
    }

    if summary.primary is not None and summary.primary.box is not None and not args.skip_ocr:
        roi = extract_roi_box(array, summary.primary.box)
        metrics["roi_width"] = roi.width
        metrics["roi_height"] = roi.height
        try:
            evidence = run_tesseract_baseline(roi)
            metrics["ocr_usability"] = evidence.usability.value
            metrics["ocr_raw_length"] = len(evidence.raw_string)
            metrics["ocr_elapsed_ms"] = evidence.elapsed_ms
            metrics["recipe_ocr"] = evidence.recipe_version
            metrics["ocr_status"] = "ok"
        except OcrFailure as failure:
            metrics["ocr_status"] = "failure"
            metrics["ocr_failure_code"] = failure.code.value
            metrics["ocr_failure_category"] = failure.category
            metrics["ocr_failure_message_key"] = failure.message_key
            if failure.code is OcrFailureCode.DEPENDENCY_UNAVAILABLE:
                metrics["ocr_dependency"] = "unavailable"
    elif not args.skip_ocr:
        metrics["ocr_status"] = "skipped_no_primary_region"

    json.dump(metrics, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
