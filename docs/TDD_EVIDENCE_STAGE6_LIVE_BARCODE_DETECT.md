# TDD evidence — Stage 6 live barcode detect framing (B21+B22)

Observed RED/GREEN commands only (no fabricated output).

## Base

- Base commit: `8bc091ddd88f7874cf245a75439e21192f54ea52`
- Branch: `feat/stage6-live-barcode-detect-framing`

## A. `physical_vision_barcode` unit tests

### RED (missing package)

Command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_barcode_frame.py -v --tb=line
```

Observed:

```text
ModuleNotFoundError: No module named 'physical_vision_barcode'
10 failed
```

### GREEN

Command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_barcode_frame.py -v --tb=short
```

Observed:

```text
10 passed in 0.31s
```

Coverage includes: blank → none; injectable one/multiple boxes; label-only ignored;
immutability / no payload fields in repr; buffer not mutated; synthetic barcode-like
via classical path; config version reject; image budget failure.

## B. Localhost API tests

### RED (missing API module)

Command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_barcode_api.py -v --tb=line
```

Observed:

```text
ModuleNotFoundError: No module named 'physical_vision_api'
6 failed
```

### GREEN (after FastAPI pin + app)

Command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_barcode_api.py -v --tb=short
```

Observed:

```text
6 passed
```

Coverage includes: `/health`; multipart PNG analyze JSON without decode fields;
multiple → null box; oversize body 413; raw JPEG body; invalid bytes content-free error.

## C. Web client

Static `apps/web` (HTML/CSS/JS) — no Node unit suite required for Stage 6. Manual
smoke requires camera hardware; automated gates stay camera-free via Python tests.

## Recipe pins

- `barcode-frame-analyze-v1` (compose `classical-localization-recipe-v1`)
- Decode payload: off
- Auto-sample cap in UI: ≤5 Hz
