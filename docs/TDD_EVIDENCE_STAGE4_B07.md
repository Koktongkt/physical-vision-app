# TDD evidence — Stage 4 B07

This file records commands and representative output observed during implementation. It is not reconstructed evidence for unobserved runs.

## Coordinate / config vertical slices

### Package surface missing (initial RED)

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_geometry.py -v --tb=line
ImportError: cannot import name 'DEFAULT_GEOMETRY_CONFIG' from 'physical_vision_geometry' (unknown location)
ERROR tests/python/test_geometry.py
```

### After adding `physical_vision_geometry` + pinned OpenCV/numpy (GREEN for coordinate suite)

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_geometry.py -v
18 passed in 0.18s
```

(Config freeze/version rejection, normalized↔pixel round trips, half-open box bounds, quad cardinality, EXIF 1–8 composition.)

## ROI / rectification / quality / overlay slices

Added synthetic-fixture tests for detached ROI crops, well-conditioned rectification, degenerate/ill-conditioned rejection, directional quality pairs, motion not-determinable pathway, overlay immutability, deadline/cancel content-free failures, and content-free quality dicts.

### Intermediate RED — OpenCV Laplacian dtype

```text
cv2.error: ... Unsupported combination of source format (=5), and destination format (=6)
4 failed, 23 passed
```

GREEN after using float64 luminance for derivative filters:

```text
27 passed in 0.23s
```

### Intermediate RED — solid-white ROI sharpness fixture

```text
assert sharp_q.blur.value > blur_q.blur.value
AssertionError: assert 0.0 > 1810.21...
```

Root cause: ROI was entirely interior white (no edges). Fixture corrected to a checkerboard so Laplacian variance is informative. Observed GREEN:

```text
27 passed, 1 warning in 0.23s
```

Saturation divide warning removed by guarded saturation math; re-run expected pristine.

## Dependency pin

```text
opencv-python-headless==4.12.0.88
numpy==2.2.6
```

Locked via `uv lock`. Provenance recorded in `docs/PROVENANCE.md`. No OCR engines, model runtimes, GUI OpenCV, or Ultralytics added.
