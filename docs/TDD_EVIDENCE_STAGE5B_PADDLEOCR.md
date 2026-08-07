# TDD evidence — Stage 5b PaddleOCR OCR baseline

Observed RED/GREEN commands only (no fabricated output).

## Base

- Base commit: `32044503d6762e7cfbe9f48884260ad27a2692a9`
- Branch: `feat/stage5b-paddleocr-baseline`

## Initial RED (missing public API)

Command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_ocr.py::test_default_ocr_config_is_frozen_paddle_recipe -v --tb=short
```

Observed:

```text
ImportError: cannot import name 'run_ocr_baseline' from 'physical_vision_ocr'
ERROR tests/python/test_ocr.py
```

## GREEN (stub-first unit + integration smoke)

Command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_ocr.py tests/python/test_stage5_integration.py -v --tb=short
```

Observed:

```text
18 passed, 1 skipped
```

Skipped: `test_optional_real_paddleocr_on_synthetic_digits` when the optional
`paddle-ocr` extra (`paddleocr`/`paddlepaddle`) is not installed, or when
`PHYSICAL_VISION_PADDLE_OCR=0`.

## CI strategy

- Default dependencies do **not** install PaddleOCR/PaddlePaddle (keeps Ubuntu/Windows CI reliable).
- Optional extra: `paddle-ocr` pins `paddleocr==3.7.0` and `paddlepaddle==3.3.1` (CPU).
- Unit tests always use injectable stub engines.
- Integration marker skips when stack absent or env disables it.
- `pytesseract` removed from default dependencies and package source.

## Recipe pin

- `paddleocr-baseline-v1`
- `lang=en`
- `ocr_version=PP-OCRv5`
- `text_detection_model_name=PP-OCRv5_mobile_det`
- `text_recognition_model_name=PP-OCRv5_mobile_rec`
- `device=cpu`
