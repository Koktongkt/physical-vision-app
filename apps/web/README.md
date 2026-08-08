# apps/web — Stage 7 live barcode framing client

Minimal localhost browser UI for **B21–B24**:

- camera permission + live `<video>` preview
- Analyze button and optional auto-sample capped at **5 Hz**
- readiness-driven status chrome:
  - **ready** → green “Ready — you may take the picture”
  - **guidance** → exactly one English camera-referent cue from `guidance_action`
  - **abstain** → none/multiple/unknown copy (no directional action)
- overlay: green box when ready; accent when guidance; none when abstain
- **Shutter** freezes the current frame on a canvas (keeps last result; human-only, no auto-capture)
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

- CI cannot open a camera; Python unit/API tests cover detect + readiness without hardware.
- Decode remains off. Thresholds are VT seeds, not calibrated production ready rates.
- Preview frames are not written to disk by this client.
