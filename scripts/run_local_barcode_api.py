"""Run the Stage 6 localhost barcode analyze API on loopback.

Usage (from repo root):
  uvx --from uv==0.11.31 uv run python scripts/run_local_barcode_api.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for rel in ("packages/vision/python", "services/api/python"):
    path = ROOT / rel
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "physical_vision_api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
