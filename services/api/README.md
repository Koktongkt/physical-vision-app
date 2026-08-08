# services/api — localhost barcode analyze boundary (Stage 7)

Thin FastAPI app exposing:

- `GET /health` → `{"status":"ok"}`
- `POST /v1/barcode/analyze` — multipart field `image` or raw JPEG/PNG body

Returns JSON evidence only (Stage 6 fields retained; Stage 7 readiness added):

```json
{
  "count_status": "none|one|multiple|unknown",
  "barcode_box": { "x0": 0.1, "y0": 0.2, "x1": 0.9, "y1": 0.5 },
  "proposal_sources": ["opencv_barcode_detect"],
  "elapsed_ms": 12.3,
  "recipe_version": "barcode-frame-ready-v1",
  "readiness": "abstain|guidance|ready",
  "guidance_action": "none|camera_closer|camera_farther|camera_left|camera_right|camera_up|camera_down|camera_steady|reduce_glare",
  "failing_gates": ["min_area"],
  "quality": {
    "area_normalized": 0.18,
    "short_side_px": 90.0,
    "margin_left": 0.2,
    "margin_right": 0.2,
    "margin_top": 0.35,
    "margin_bottom": 0.35,
    "laplacian_variance": 120.0,
    "aspect_ratio": 2.0,
    "exposure_mean": 128.0
  }
}
```

When `count_status` is not `one`, `barcode_box` and `quality` are null, `readiness` is `abstain`, and `guidance_action` is `none`. No payload/decode fields.

No auth (G5 personal test). CORS limited to localhost static origins. Body size capped. Uses `physical_vision_image.decode_image` + `physical_vision_barcode.analyze_barcode_frame` (decode payload off).

## Run

From repository root:

```bash
uvx --from uv==0.11.31 uv run python scripts/run_local_barcode_api.py
```

## Tests

```bash
uvx --from uv==0.11.31 uv run pytest tests/python/test_barcode_api.py -q
```
