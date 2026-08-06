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

This package is not a learned localizer, OCR engine, or policy decision boundary. Classical localization bake-off work remains B08/B09.
