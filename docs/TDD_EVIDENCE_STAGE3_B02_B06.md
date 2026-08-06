# TDD evidence — Stage 3 B02 + B06

This file records commands and representative output observed during implementation. It is not reconstructed evidence for unobserved runs.

## B06 vertical RED → GREEN slices

### Supported JPEG/PNG canonical boundary

RED:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_image_decode.py::test_decode_accepts_supported_single_frame_stills -v
E   ModuleNotFoundError: No module named 'physical_vision_image'
```

After adding the narrow package and pytest path, the first GREEN attempt exposed a test-fixture assumption: JPEG decoded `(12, 34, 57)` rather than the source `(12, 34, 56)`. The assertion was corrected to tolerate one lossy-codec unit. Observed GREEN:

```text
2 passed in 0.08s
```

### Encoded-byte boundary and stable typed failure

RED:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_image_decode.py::test_encoded_byte_guard_accepts_boundary_and_rejects_one_byte_over -v
E   ImportError: cannot import name 'DecodeFailure' from 'physical_vision_image'
```

GREEN after adding the typed outcome and inclusive byte guard:

```text
1 passed in 0.05s
```

### Corrupt-image mapping

RED showed raw Pillow exceptions escaping (`PIL.UnidentifiedImageError` and `OSError: Truncated File Read`). GREEN after mapping parser failures:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_image_decode.py::test_malformed_input_returns_stable_corrupt_image_failure -q
2 passed in 0.10s
```

### EXIF-once canonicalization and reversible transforms

RED for all eight orientations:

```text
E   AttributeError: 'CanonicalImage' object has no attribute 'orientation'
8 failed in 0.15s
```

GREEN after applying `ImageOps.exif_transpose`, detaching RGB bytes, neutralizing metadata, and adding normalized reversible transforms:

```text
8 passed in 1.01s
```

### Dimension, pixel, and decoded-memory guards

RED failed during test collection because the new codes did not exist:

```text
E   AttributeError: IMAGE_DIMENSIONS_UNSUPPORTED
```

GREEN at the exact boundaries and one unit over:

```text
4 passed in 0.10s
```

### Multi-frame and unsupported decoded types

RED observed APNG accepted and raw `KeyError` for GIF/BMP:

```text
E   Failed: DID NOT RAISE <class 'physical_vision_image.DecodeFailure'>
E   KeyError: 'GIF'
E   KeyError: 'BMP'
3 failed in 0.19s
```

GREEN after checking decoder-observed frame count before format acceptance:

```text
3 passed in 0.08s
```

### Metadata work and trailing payloads

Metadata RED:

```text
E   AttributeError: 'CanonicalImage' object has no attribute 'metadata_bytes'
2 failed in 0.14s
```

Metadata boundary GREEN:

```text
2 passed in 0.11s
```

Trailing-payload RED observed both JPEG and PNG accepted appended data (`Failed: DID NOT RAISE`). GREEN after format-aware terminal parsing:

```text
2 passed in 0.06s
```

Compressed PNG metadata RED observed a 5,000-byte expansion pass a 100-byte policy (`Failed: DID NOT RAISE`). GREEN after bounded zlib expansion through `remaining + 1`:

```text
1 passed in 0.06s
```

### Stream detachment, deadlines, cancellation, and Pillow bomb handling

Bounded-stream RED:

```text
E   TypeError: object of type '_io.BytesIO' has no len()
```

GREEN after bounded stream admission and detached output:

```text
1 passed in 0.06s
```

Time/cancellation RED:

```text
E   TypeError: decode_image() got an unexpected keyword argument 'cancelled'
```

GREEN after cooperative checkpoints:

```text
1 passed in 0.10s
```

Decompression-bomb RED showed raw `PIL.Image.DecompressionBombError` for a synthetic 400,000,000-pixel declaration. GREEN after locally converting warnings to errors without changing Pillow globals and mapping both warning/error classes:

```text
1 passed in 0.07s
```

### Configuration, invalid dimensions, and bounded fuzz

Invalid-config RED: `Failed: DID NOT RAISE <class 'ValueError'>`. GREEN after exact frozen configuration validation: `1 passed in 0.08s`.

Zero-dimension RED returned `INVALID_OR_CORRUPT_IMAGE` instead of `IMAGE_DIMENSIONS_UNSUPPORTED`. GREEN after pre-open PNG dimension admission: `1 passed in 0.06s`.

The first deterministic fuzz run found late-truncated PNGs that Pillow accepted without IEND (`PNG-56/75` through `PNG-72/75`). Requiring the format terminal closed the gap. Final fuzz GREEN:

```text
1 passed in 0.13s
```

Final focused B06 suite at that point:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_image_decode.py -q
32 passed in 0.29s
```

Review then added two security regressions. Compressed iTXt metadata initially passed a 100-byte policy and corrupt zTXt raised raw `zlib.error`; after parsing both compressed text forms with bounded expansion, the focused run reported `3 passed in 0.07s`. Canonical result `repr()` initially exposed `_pixels`; marking that field non-representable produced `1 passed in 0.09s`. The final focused decoder suite reported `36 passed in 0.28s`.

## B02 resource harness vertical RED → GREEN slices

Initial RED:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_resource_measurement.py -v
E   ModuleNotFoundError: No module named 'physical_vision_resources'
```

The first implementation then reproduced a Windows-specific process-observation failure:

```text
E   OSError: process memory observation unavailable
```

Root cause was the default ctypes return type truncating the pseudo-handle from `GetCurrentProcess`. Declaring exact `restype`/`argtypes` made the measurement test GREEN:

```text
1 passed in 0.34s
```

CLI RED:

```text
can't open file '.../scripts/measure_decode_resources.py': [Errno 2] No such file or directory
```

GREEN after adding the bounded JSON-only wrapper:

```text
1 passed in 0.40s
2 passed in 0.62s
```

Combined focused decoder/resource suite:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_image_decode.py tests/python/test_resource_measurement.py -q
39 passed in 1.03s
```

## Final acceptance gates (observed 2026-08-06 resume)

```text
uvx --from uv==0.11.31 uv run ruff format --check .
11 files already formatted

uvx --from uv==0.11.31 uv run ruff check .
All checks passed!

uvx --from uv==0.11.31 uv run pytest -q
239 passed in 3.25s

npm run contracts:check
generated contract types are in sync

npm run typecheck
(pass)

npm run test:ts
141 pass, 0 fail

npm run format:check
All matched files use Prettier code style!

npm audit --audit-level=moderate
found 0 vulnerabilities

uvx --from uv==0.11.31 uv run python scripts/check_sensitive_files.py
sensitive-file check passed for 210 tracked files

git diff --check
(pass, no output)

uvx --from uv==0.11.31 uv run python scripts/measure_decode_resources.py --iterations 10 --width 1024 --height 768
successful_decodes=20 failed_decodes=0 wall_ms≈147.8 process_cpu_ms≈140.6
maximum_decode_elapsed_ms=16.0 maximum_encoded_bytes=12916
maximum_decoded_estimate_bytes=2359296 cancellation/deadline probes=DECODE_BUDGET_EXCEEDED
```

Static scan of the working tree diff found no hardcoded secrets, shell=True, eval/exec, or pickle loads.
