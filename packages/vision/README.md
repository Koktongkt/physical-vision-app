# Bounded image decode package

`physical_vision_image` is the Stage 3 B06 internal boundary for JPEG/PNG admission and canonicalization.

The package accepts encoded bytes or a bounded binary stream plus an explicit frozen `DecodeConfig`. `decode_image` returns an immutable `CanonicalImage` containing non-sensitive media/resource facts, detached RGB pixels, and a reversible source/canonical `OrientationTransform`. `to_pillow()` creates a new independent Pillow image each time; no lazy input stream or encoded source bytes escape.

The decoder validates the decoder-observed format and frame count rather than filename, extension, MIME, magic bytes, or caller claims. Its API intentionally has no filename/MIME claim parameter. It applies Pillow EXIF transpose once, emits orientation/coordinate metadata separately from any future browser display transform, and strips metadata by constructing the canonical image from detached RGB bytes.

Stable `DecodeFailure` outcomes cover unsupported media, animation/multiple frames, malformed/corrupt/trailing media, dimensions, encoded bytes, metadata/decode work, decompression bombs, memory estimate, elapsed time, deadlines, and cancellation. Messages contain only allowlisted keys.

The numeric settings in `decode-resource-policy-v1` are provisional safety guards, not product-quality upload limits. See `docs/RESOURCE_POLICY_STAGE3.md` for exact values, observations, and deferred B12/B13/B17 responsibilities.
