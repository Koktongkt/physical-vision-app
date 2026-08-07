# TDD evidence — Stage 5 classical localization + Tesseract OCR baseline

This file records commands and representative output observed during implementation.
It is not reconstructed evidence for unobserved runs.

## Localization package surface missing (initial RED)

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_localization.py -v --tb=line
ImportError: No module named 'physical_vision_localization'
ERROR tests/python/test_localization.py
```

## Localization after `physical_vision_localization` implementation (GREEN)

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_localization.py -v
17 passed in 0.31s
```

Covered: frozen `classical-localization-recipe-v1`, barcode-like synthetic bars →
`barcode_landmark`, label rectangle → `label_region`, noise → `no_label`/`uncertain`,
multi-region → `multiple_labels` deterministic, payload drop at detector boundary,
EXIF orientation metadata, cancel/deadline typed failures, ROI composition with B07.

## OCR package surface missing (initial RED)

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_ocr.py -v --tb=line
ImportError: No module named 'physical_vision_ocr'
ERROR tests/python/test_ocr.py
```

## Intermediate RED — unregistered pytest marker

```text
Failed: 'integration' not found in `markers` configuration option
```

GREEN after registering `integration` in `pyproject.toml` `[tool.pytest.ini_options].markers`.

## OCR after `physical_vision_ocr` + pinned `pytesseract` (GREEN)

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_ocr.py -v
14 passed, 1 skipped in 0.23s
```

Skipped test: `test_optional_real_tesseract_on_synthetic_digits` when the system
Tesseract binary is not on `PATH`. Stubbed engine tests cover verbatim passthrough,
leading zeros, multiline→ambiguous, blank→unreadable, dependency unavailable,
timeout/cancel, immutability, and B07 `ExtractedRoi` acceptance.

## Integration smoke (GREEN)

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_stage5_integration.py tests/python/test_localization.py tests/python/test_ocr.py -q
32 passed, 1 skipped in 0.45s
```

## Experiment harness smoke (observed)

```text
uvx --from uv==0.11.31 uv run python experiments/vision-baseline/run_stage5_classical_ocr.py --skip-ocr
```

Emitted content-free JSON with `localization_outcome=trustworthy`, proposal kinds
including `barcode_landmark` / `label_region` / `text_region`, and no OCR payload fields.

## Dependency pins

```text
pytesseract==0.3.13
opencv-python-headless==4.12.0.88  (reused)
numpy==2.2.6  (reused)
pillow==12.3.0  (reused)
```

Locked via `uv lock` / `uv add`. System Tesseract binary is **not** installed by CI;
integration tests skip when absent. Provenance in `docs/PROVENANCE.md`.
