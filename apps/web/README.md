# apps/web — Stage 6 live barcode framing client

Minimal localhost browser UI for **B21 + B22 wiring**:

- camera permission + live `<video>` preview
- Analyze button and optional auto-sample capped at **5 Hz**
- overlay box when API returns `count_status=one`
- status text for searching / one / multiple (abstain) / none
- **Shutter** freezes the current frame on a canvas (keeps last result)
- **Retake** returns to live preview
- **never** displays decode payloads or serial strings

## Prerequisites

1. Python API running on loopback (default `http://127.0.0.1:8000`).
2. A desktop browser with camera access (Chrome/Edge recommended).

## Run the API

From the repository root (after `uv sync --group dev`):

```bash
uvx --from uv==0.11.31 uv run uvicorn physical_vision_api.app:app --host 127.0.0.1 --port 8000
```

`PYTHONPATH` is configured via `pyproject.toml` for tests; for uvicorn, prefer:

```bash
cd services/api/python
uvx --from uv==0.11.31 uv run --project ../../.. uvicorn physical_vision_api.app:app --host 127.0.0.1 --port 8000
```

Or from repo root with explicit path:

```bash
PYTHONPATH=packages/vision/python;services/api/python uv run uvicorn physical_vision_api.app:app --app-dir services/api/python --host 127.0.0.1 --port 8000
```

On Windows (git-bash):

```bash
cd /path/to/repo
PYTHONPATH="packages/vision/python:services/api/python" uvx --from uv==0.11.31 uv run uvicorn physical_vision_api.app:app --host 127.0.0.1 --port 8000
```

Health check: `GET http://127.0.0.1:8000/health` → `{"status":"ok"}`.

## Run this web client

Static files only — no build step.

```bash
# from repo root
npx --yes serve apps/web -l 5173
# or
python -m http.server 5173 --directory apps/web
```

Open **`http://127.0.0.1:5173`** (not `file://`). Confirm the API base field matches the uvicorn origin. Click **Start camera**, allow permission, then **Analyze** (or enable auto-sample).

### Black preview?

A black rectangle is **not** the intended “empty stub” UI — the stage background is black until real camera frames paint. If it stays black after Start camera:

1. Use `http://127.0.0.1:5173` or `http://localhost:5173` (secure context). `file://` often breaks `getUserMedia`.
2. Allow camera permission for that origin in the browser.
3. Windows: **Settings → Privacy & security → Camera** — allow desktop apps / browser; close Zoom/Teams/etc. that may lock the device.
4. Laptop lid privacy shutter / Fn camera key.
5. Status line should move to **Live — searching…** when frames arrive; if you see **Live — black/no frames**, the track opened without dimensions (device/driver).
6. API being down only affects **Analyze**, not the live preview.

## Notes

- CI cannot open a camera; Python unit/API tests cover detect wiring without hardware.
- Ready/green quality gates (B23) and multi-action guidance (B24) are out of Stage 6 scope.
- Preview frames are not written to disk by this client.
