from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any

from physical_vision_image import (
    DEFAULT_DECODE_CONFIG,
    DecodeFailure,
    decode_image,
)
from PIL import Image


def _host_memory() -> tuple[int, int]:
    if os.name == "nt":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise OSError("host memory observation unavailable")
        return int(status.total_physical), int(status.available_physical)

    page_size = os.sysconf("SC_PAGE_SIZE")
    total_pages = os.sysconf("SC_PHYS_PAGES")
    total = int(page_size * total_pages)
    available = total
    try:
        fields = {}
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            key, value = line.split(":", 1)
            fields[key] = int(value.strip().split()[0]) * 1024
        available = fields.get("MemAvailable", total)
    except (OSError, ValueError, KeyError):
        pass
    return total, available


def _process_memory() -> tuple[int, int]:
    if os.name == "nt":

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("page_fault_count", ctypes.c_ulong),
                ("peak_working_set_size", ctypes.c_size_t),
                ("working_set_size", ctypes.c_size_t),
                ("quota_peak_paged_pool_usage", ctypes.c_size_t),
                ("quota_paged_pool_usage", ctypes.c_size_t),
                ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
                ("quota_non_paged_pool_usage", ctypes.c_size_t),
                ("pagefile_usage", ctypes.c_size_t),
                ("peak_pagefile_usage", ctypes.c_size_t),
                ("private_usage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        get_current_process = ctypes.windll.kernel32.GetCurrentProcess
        get_current_process.restype = ctypes.c_void_p
        get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ProcessMemoryCounters),
            ctypes.c_ulong,
        ]
        get_process_memory_info.restype = ctypes.c_int
        process = get_current_process()
        if not get_process_memory_info(
            process,
            ctypes.byref(counters),
            counters.cb,
        ):
            raise OSError("process memory observation unavailable")
        return int(counters.working_set_size), int(counters.peak_working_set_size)

    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    scale = 1 if platform.system() == "Darwin" else 1024
    return int(peak * scale), int(peak * scale)


def _nvidia_observation() -> dict[str, Any] | None:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return None
    completed = subprocess.run(
        [
            executable,
            "--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=3,
    )
    if completed.returncode != 0:
        return None
    devices = []
    for line in completed.stdout.splitlines():
        values = [value.strip() for value in line.split(",")]
        if len(values) != 5:
            continue
        name, total_mib, used_mib, utilization_percent, temperature_c = values
        try:
            devices.append(
                {
                    "name": name,
                    "total_vram_bytes": int(total_mib) * 1024 * 1024,
                    "used_vram_bytes": int(used_mib) * 1024 * 1024,
                    "utilization_percent": int(utilization_percent),
                    "temperature_c": int(temperature_c),
                }
            )
        except ValueError:
            continue
    return {"devices": devices, "decode_gpu_used": False} if devices else None


def _encode_synthetic(format_name: str, size: tuple[int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, (17, 34, 51)).save(output, format=format_name)
    return output.getvalue()


def _failure_code(**kwargs: Any) -> str:
    try:
        decode_image(_encode_synthetic("PNG", (1, 1)), DEFAULT_DECODE_CONFIG, **kwargs)
    except DecodeFailure as failure:
        return failure.code.value
    raise RuntimeError("resource probe unexpectedly succeeded")


def measure_synthetic_decode_workload(
    *,
    iterations: int = 5,
    size: tuple[int, int] = (512, 384),
) -> dict[str, Any]:
    if type(iterations) is not int or not 1 <= iterations <= 100:
        raise ValueError("iterations must be an integer in [1, 100]")
    if (
        type(size) is not tuple
        or len(size) != 2
        or any(type(value) is not int or not 1 <= value <= 2_048 for value in size)
        or size[0] * size[1] > 4_000_000
    ):
        raise ValueError("synthetic dimensions exceed the measurement harness bound")

    total_memory, available_before = _host_memory()
    process_rss_before, process_peak_before = _process_memory()
    temporary_free_before = shutil.disk_usage(tempfile.gettempdir()).free
    retained_free_before = shutil.disk_usage(Path.cwd()).free
    gpu_before = _nvidia_observation()
    encoded = {format_name: _encode_synthetic(format_name, size) for format_name in ("JPEG", "PNG")}

    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    successful_decodes = 0
    failed_decodes = 0
    decode_elapsed_values = []
    encoded_sizes = []
    decoded_estimates = []
    metadata_sizes = []
    for _ in range(iterations):
        for format_name in ("JPEG", "PNG"):
            try:
                decoded = decode_image(encoded[format_name], DEFAULT_DECODE_CONFIG)
            except DecodeFailure:
                failed_decodes += 1
                continue
            successful_decodes += 1
            decode_elapsed_values.append(decoded.decode_elapsed_ms)
            encoded_sizes.append(decoded.encoded_size)
            decoded_estimates.append(decoded.estimated_decoded_bytes)
            metadata_sizes.append(decoded.metadata_bytes)
    process_cpu_ms = (time.process_time() - started_cpu) * 1000
    wall_ms = (time.perf_counter() - started_wall) * 1000

    _, available_after = _host_memory()
    process_rss_after, process_peak_after = _process_memory()
    temporary_free_after = shutil.disk_usage(tempfile.gettempdir()).free
    retained_free_after = shutil.disk_usage(Path.cwd()).free
    gpu_after = _nvidia_observation()

    return {
        "schema_version": "resource-observation-v1",
        "policy_version": DEFAULT_DECODE_CONFIG.version,
        "scope": "provisional-engineering-measurement-not-product-slo",
        "workload": {
            "fixture_kind": "synthetic-solid-color",
            "formats": ["JPEG", "PNG"],
            "width": size[0],
            "height": size[1],
            "iterations_per_format": iterations,
        },
        "host": {
            "operating_system": platform.system(),
            "operating_system_release": platform.release(),
            "machine": platform.machine(),
            "cpu_model": platform.processor()
            or os.environ.get("PROCESSOR_IDENTIFIER")
            or "unknown",
            "logical_cpu_count": os.cpu_count() or 1,
            "total_memory_bytes": total_memory,
            "minimum_available_memory_bytes": min(available_before, available_after),
            "temporary_storage_free_bytes": min(temporary_free_before, temporary_free_after),
            "retained_storage_free_bytes": min(retained_free_before, retained_free_after),
            "gpu_before": gpu_before,
            "gpu_after": gpu_after,
            "cpu_thermal": {"status": "unavailable-with-stdlib-harness"},
        },
        "observation": {
            "successful_decodes": successful_decodes,
            "failed_decodes": failed_decodes,
            "wall_ms": round(wall_ms, 3),
            "process_cpu_ms": round(process_cpu_ms, 3),
            "process_rss_before_bytes": process_rss_before,
            "process_rss_after_bytes": process_rss_after,
            "process_peak_rss_bytes": max(process_peak_before, process_peak_after),
            "maximum_decode_elapsed_ms": round(max(decode_elapsed_values, default=0.0), 3),
            "maximum_encoded_bytes": max(encoded_sizes, default=0),
            "maximum_decoded_estimate_bytes": max(decoded_estimates, default=0),
            "maximum_metadata_bytes": max(metadata_sizes, default=0),
            "temporary_storage_delta_bytes": temporary_free_after - temporary_free_before,
            "retained_storage_delta_bytes": retained_free_after - retained_free_before,
            "cancellation_probe_code": _failure_code(cancelled=lambda: True),
            "deadline_probe_code": _failure_code(deadline=-1.0),
        },
    }
