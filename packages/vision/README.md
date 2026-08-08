# Bounded image decode and geometry packages

## `physical_vision_image` (B06)

`physical_vision_image` is the Stage 3 B06 internal boundary for JPEG/PNG admission and canonicalization.

The package accepts encoded bytes or a bounded binary stream plus an explicit frozen `DecodeConfig`. `decode_image` returns an immutable `CanonicalImage` containing non-sensitive media/resource facts, detached RGB pixels, and a reversible source/canonical `OrientationTransform`. `to_pillow()` creates a new independent Pillow image each time; no lazy input stream or encoded source bytes escape.

The decoder validates the decoder-observed format and frame count rather than filename, extension, MIME, magic bytes, or caller claims. Its API intentionally has no filename/MIME claim parameter. It applies Pillow EXIF transpose once, emits orientation/coordinate metadata separately from any future browser display transform, and strips metadata by constructing the canonical image from detached RGB bytes.

Stable `DecodeFailure` outcomes cover unsupported media, animation/multiple frames, malformed/corrupt/trailing media, dimensions, encoded bytes, metadata/decode work, decompression bombs, memory estimate, elapsed time, deadlines, and cancellation. Messages contain only allowlisted keys.

The numeric settings in `decode-resource-policy-v1` are provisional safety guards, not product-quality upload limits. See `docs/RESOURCE_POLICY_STAGE3.md` for exact values, observations, and deferred B12/B13/B17 responsibilities.

## `physical_vision_geometry` (B07)

`physical_vision_geometry` is the Stage 4 B07 internal boundary for deterministic OpenCV geometry on already-canonical RGB images.

It provides:

- frozen `geometry-resource-policy-v1` / `raw-quality-recipe-v1` configuration;
- immutable normalized points, axis-aligned boxes, and ordered quadrilaterals (top-left origin, x right, y down, unit square);
- normalized↔pixel conversion with half-open box pixel bounds for slicing;
- composition with B06 `OrientationTransform` for source↔canonical↔pixel consistency;
- detached ROI box extraction and perspective rectification of caller-provided convex quads when numerically well-conditioned;
- raw quality measurements (crop/edge-contact, scale, center, blur/Tenengrad, exposure, contrast, glare candidate, occlusion unknown, perspective proxies) with explicit `unknown` / `not_determinable` pathways (motion is not determinable from a single still unless synthetic-labeled as unknown);
- overlay primitives (box, polygon/quad, directional arrow) in canonical normalized coordinates without prose or UI frameworks.

Rectified crops are labeled `evidence_kind=rectified_derivative` and do not replace unrectified source ROI identity. Rectification does not claim recovery of hidden wraparound content. Failures are content-free typed codes/categories/message keys.

This package is not a learned localizer, OCR engine, or policy decision boundary.

## `physical_vision_localization` (Stage 5 / Phase 2 code baseline)

Classical barcode/contour localization baseline. Frozen recipe
`classical-localization-recipe-v1` proposes `barcode_landmark`, `label_region`,
and optional near-barcode `text_region` geometry in canonical normalized
coordinates. OpenCV barcode detector APIs may contribute geometry only —
**payload strings/bytes are dropped at the boundary** and never appear on public
results, logs, or metrics. Morphological gradient proposals cover synthetic
high-contrast fixtures when the detector finds nothing. Deterministic
`select_localization_summary` maps zero/one/many proposals to
`trustworthy | no_label | multiple_labels | uncertain`.

Not an open-world robust localizer and not a bake-off winner claim. Physical
corpus work remains B08; classical-vs-learned bake-off remains B09.

## `physical_vision_ocr` (Stage 5 / Stage 5b code baseline)

PaddleOCR single-line / ROI OCR baseline on a caller-provided detached ROI
(`ExtractedRoi`, array, or Pillow image). Frozen recipe `paddleocr-baseline-v1`
(`en`, PP-OCRv5 mobile det/rec, CPU-only). Returns immutable evidence with **verbatim**
`raw_string` (no silent repair, case folding, checksum/format “helpfulness”).
Usability labels `usable | unreadable | ambiguous` are **uncalibrated heuristics**.
Missing PaddleOCR/PaddlePaddle import or model runtime → typed
`DEPENDENCY_UNAVAILABLE` (no interpreter crash). CI keeps stubbed engine tests
always-on; optional `@pytest.mark.integration` real-engine test skips when the
optional `paddle-ocr` extra is absent or `PHYSICAL_VISION_PADDLE_OCR=0`.

Not a B10 bake-off completion, not production-validated OCR, and not a
policy/completion boundary. Tesseract is no longer the default runtime path.

## `physical_vision_barcode` (Stage 6–7 / B22–B24 framing + ready/guidance)

Live-framing barcode **count + box + readiness** boundary. Frozen recipe
`barcode-frame-ready-v1` composes Stage 5 `propose_classical_regions` and
**filters to `barcode_landmark` proposals only** (label/text proposals do not
affect count policy). Maps:

- 0 barcodes → `count_status=none`, `barcode_box=null`, `readiness=abstain`
- 1 barcode → `one` + that normalized box; quality gates → `ready` or `guidance`
- 2+ barcodes → `multiple`, `barcode_box=null`, `readiness=abstain` (no pick-largest)

When `count==one`, geometry/quality gates (min area, short side px, margins,
blur/Laplacian, aspect, optional exposure) run under a fixed priority list. All
pass → `readiness=ready`, `guidance_action=none`. Any fail → `readiness=guidance`
with **exactly one** camera-referent action from the dominant failing gate.
Thresholds are VT seeds in frozen config — not calibrated production rates.

OpenCV barcode detector geometry may contribute via localization; **payload
strings/bytes are dropped at the localization boundary** and never appear on
`BarcodeFrameEvidence`. Injectable `propose_regions` supports unit tests without
relying on detector behavior on synthetic noise.

Not B25 privacy/SBOM hardening, not B26 live pilot validation, not a decode UX,
and not a policy/completion boundary.
