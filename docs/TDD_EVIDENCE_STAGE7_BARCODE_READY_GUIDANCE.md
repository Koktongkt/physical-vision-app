# TDD evidence — Stage 7 barcode ready gates + one-action guidance (B23+B24)

Observed RED/GREEN commands only (no fabricated output).

## Base

- Base commit: `e8d2e05629dee34e4085bbd8d0d7acf7270b7f4d`
- Branch: `feat/stage7-barcode-ready-guidance`

## A. `physical_vision_barcode` readiness unit tests

### RED (missing readiness types / fields)

Command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_barcode_frame.py -v --tb=line
```

Observed:

```text
ImportError: cannot import name 'BarcodeGuidanceAction' from 'physical_vision_barcode'
AssertionError: assert 'barcode-frame-analyze-v1' == 'barcode-frame-ready-v1'
9 failed, 11 passed
```

### GREEN

Command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_barcode_frame.py -v --tb=short
```

Observed:

```text
20 passed in 0.30s
```

Coverage includes: none/multiple → abstain + action none; one + all gates → ready;
tiny area → camera_closer; left-clipped → camera_right; low blur → camera_steady;
exactly one action; priority when two gates fail; no payload fields; recipe
`barcode-frame-ready-v1`.

## B. Localhost API tests

### RED (JSON missing readiness fields)

Command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_barcode_api.py -v --tb=line
```

Observed:

```text
KeyError: 'readiness'
4 failed, 3 passed
```

### GREEN

Command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_barcode_api.py tests/python/test_barcode_frame.py -q --tb=line
```

Observed:

```text
27 passed
```

Coverage includes: ready + quality scalars; multiple → abstain; guidance
`camera_right` + failing_gates; no decode fields.

## C. Web client

Static `apps/web` updates for ready green chrome, single guidance string map, and
abstain copy. No browser automation in CI (camera unavailable). Manual smoke:
Start camera → Analyze → observe ready/guidance/abstain; shutter remains human.

## Gate priority + VT seeds (frozen config)

Recipe: `barcode-frame-ready-v1`

Priority (first failing wins):

1. `min_area`
2. `min_short_side_px`
3. `margin_left`
4. `margin_right`
5. `margin_top`
6. `margin_bottom`
7. `blur`
8. `aspect`
9. `exposure`

VT seeds (not calibrated production rates):

| Gate                   | Seed                                            |
| ---------------------- | ----------------------------------------------- |
| min_area               | 0.002 (classical `min_barcode_area_normalized`) |
| min_short_side_px      | 48                                              |
| margin_frac            | 0.04                                            |
| min_laplacian_variance | 50.0                                            |
| aspect                 | 1.8 … 25.0 (classical barcode aspect)           |
| exposure_high / low    | 245.0 / 12.0                                    |

Margin → camera mapping (camera-referent): left-clipped → `camera_right`;
right → `camera_left`; top → `camera_down`; bottom → `camera_up`.

Aspect rule: below min → `camera_closer`; above max → `camera_farther`.
Exposure high → `reduce_glare`; low → `camera_steady`.

## Explicit non-claims

- Decode remains off.
- Thresholds are VT seeds only — not live pilot ready-rate validation.
- No multi-barcode pick-largest; multi/none/unknown abstain.
