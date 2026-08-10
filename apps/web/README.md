# apps/web — Stage 8 live barcode framing client

Minimal localhost browser UI for **B21–B25**:

- camera permission + live `<video>` preview
- Analyze button and optional auto-sample capped at **5 Hz**
- readiness-driven status chrome:
  - **ready** → green “Ready — you may take the picture”
  - **guidance** → exactly one English camera-referent cue from `guidance_action`
  - **abstain** → none/multiple/unknown copy (no directional action)
- overlay: green box when ready; accent when guidance; none when abstain
- **Shutter** freezes the current frame on a canvas (keeps last result; human-only, no auto-capture)
- **Retake** releases the prior track/buffers and starts a fresh live preview
- **Stop camera** releases tracks, timers, in-flight analysis, and canvases
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

Static files only — no build step. Use the canonical launcher so the web server cannot bind to LAN interfaces:

```bash
# from repo root; binds exactly 127.0.0.1:5173 and opens the approved URL
uvx --from uv==0.11.31 uv run python scripts/run_local_barcode_web.py
```

The launcher opens `http://127.0.0.1:5173/`; the client calls only `http://127.0.0.1:8000`. Click **Start camera**, allow permission, then **Analyze** (or enable auto-sample).

## Notes

- CI cannot open a camera; Python unit/API tests cover detect + readiness without hardware.
- Decode remains off. Thresholds are VT seeds, not calibrated production ready rates.
- Preview frames are not written to disk by this client. Scratch pixels are cleared after blob creation.
- Stop, Retake, hidden-page, page exit, and camera track-ended paths release browser resources. Returning from a hidden page requires **Start camera** again.
