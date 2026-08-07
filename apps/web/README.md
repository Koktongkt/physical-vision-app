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

Open `http://127.0.0.1:5173`. Confirm the API base field matches the uvicorn origin. Click **Start camera**, allow permission, then **Analyze** (or enable auto-sample).

## Notes

- CI cannot open a camera; Python unit/API tests cover detect wiring without hardware.
- Ready/green quality gates (B23) and multi-action guidance (B24) are out of Stage 6 scope.
- Preview frames are not written to disk by this client.
