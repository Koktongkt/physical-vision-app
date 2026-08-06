from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "packages/vision/python"))

from physical_vision_resources import measure_synthetic_decode_workload  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure a bounded synthetic decode workload")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=384)
    arguments = parser.parse_args()
    report = measure_synthetic_decode_workload(
        iterations=arguments.iterations,
        size=(arguments.width, arguments.height),
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
