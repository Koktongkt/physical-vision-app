# services/api — localhost barcode analyze boundary (Stage 6)

Thin FastAPI app exposing:

- `GET /health` → `{"status":"ok"}`
- `POST /v1/barcode/analyze` — multipart field `image` or raw JPEG/PNG body

Returns JSON evidence only:

```json
{
  "count_status": "none|one|multiple|unknown",
  "barcode_box": {"x0":0.1,"y0":0.2,"x1":0.9,"y1":0.5} | null,
  "proposal_sources": ["opencv_barcode_detect"],
  "elapsed_ms": 12.3,
  "recipe_version": "barcode-frame-analyze-v1"
}
```

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
