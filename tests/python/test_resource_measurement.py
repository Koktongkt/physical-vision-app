from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from physical_vision_resources import measure_synthetic_decode_workload

ROOT = Path(__file__).parents[2]


def test_synthetic_resource_measurement_is_bounded_and_content_free() -> None:
    report = measure_synthetic_decode_workload(iterations=2, size=(32, 24))

    assert report["schema_version"] == "resource-observation-v1"
    assert report["policy_version"] == "decode-resource-policy-v1"
    assert report["workload"] == {
        "fixture_kind": "synthetic-solid-color",
        "formats": ["JPEG", "PNG"],
        "width": 32,
        "height": 24,
        "iterations_per_format": 2,
    }
    assert report["observation"]["successful_decodes"] == 4
    assert report["observation"]["failed_decodes"] == 0
    assert report["observation"]["cancellation_probe_code"] == "DECODE_BUDGET_EXCEEDED"
    assert report["observation"]["deadline_probe_code"] == "DECODE_BUDGET_EXCEEDED"
    assert report["host"]["logical_cpu_count"] >= 1
    assert report["host"]["total_memory_bytes"] > 0
    assert report["host"]["retained_storage_free_bytes"] > 0
    serialized = json.dumps(report, sort_keys=True)
    for forbidden in ("image_bytes", "ocr", "serial", "fixture_path", "input_path"):
        assert forbidden not in serialized.lower()


def test_measurement_cli_emits_only_json_report() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/measure_decode_resources.py",
            "--iterations",
            "1",
            "--width",
            "16",
            "--height",
            "12",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["workload"]["width"] == 16
    assert report["observation"]["successful_decodes"] == 2
