from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from math import isfinite
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from physical_vision_barcode import (
    DEFAULT_BARCODE_FRAME_CONFIG,
    BarcodeFrameEvidence,
    BarcodeFrameFailure,
    BarcodeFrameFailureCode,
    analyze_barcode_frame,
)
from physical_vision_image import (
    DEFAULT_DECODE_CONFIG,
    DecodeConfig,
    DecodeFailure,
    FailureCode,
    decode_image,
)
from physical_vision_resources import observe_live_resources
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.formparsers import MultiPartParser
from starlette.types import ASGIApp, Receive, Scope, Send

# Default ~4 MiB encoded frame budget for live samples (tighter than full B06 upload).
DEFAULT_MAX_BODY_BYTES = 4_000_000
DEFAULT_ALLOWED_HOSTS = ("127.0.0.1:8000", "localhost:8000", "[::1]:8000")
DEFAULT_CORS_ORIGINS = tuple(
    f"http://{host}:{port}"
    for port in (5173, 4173, 8080)
    for host in ("127.0.0.1", "localhost", "[::1]")
)
_API_DECODE_CONFIG = DecodeConfig(
    version=DEFAULT_DECODE_CONFIG.version,
    max_encoded_bytes=DEFAULT_MAX_BODY_BYTES,
    max_width=min(DEFAULT_DECODE_CONFIG.max_width, 4096),
    max_height=min(DEFAULT_DECODE_CONFIG.max_height, 4096),
    max_pixels=min(DEFAULT_DECODE_CONFIG.max_pixels, 8_000_000),
    max_metadata_bytes=DEFAULT_DECODE_CONFIG.max_metadata_bytes,
    max_decoded_bytes=min(DEFAULT_DECODE_CONFIG.max_decoded_bytes, 48_000_000),
    max_frames=1,
    max_decode_seconds=min(DEFAULT_DECODE_CONFIG.max_decode_seconds, 2.0),
)


@dataclass(frozen=True, slots=True)
class ApiSettings:
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    max_in_flight: int = 1
    analysis_timeout_seconds: float = 2.0
    resource_probe_timeout_seconds: float = 0.2
    allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS

    def __post_init__(self) -> None:
        if type(self.max_body_bytes) is not int or self.max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be a positive integer")
        if type(self.max_in_flight) is not int or not 1 <= self.max_in_flight <= 4:
            raise ValueError("max_in_flight must be an integer in [1, 4]")
        if (
            type(self.analysis_timeout_seconds) is not float
            or not 0.0 < self.analysis_timeout_seconds <= 10.0
        ):
            raise ValueError("analysis_timeout_seconds must be a float in (0, 10]")
        if (
            type(self.resource_probe_timeout_seconds) is not float
            or not 0.0 < self.resource_probe_timeout_seconds <= 0.5
        ):
            raise ValueError("resource_probe_timeout_seconds must be a float in (0, 0.5]")
        if not self.allowed_hosts or not all(
            _is_loopback_authority(host) for host in self.allowed_hosts
        ):
            raise ValueError(
                "allowed_hosts must contain only explicit loopback host and port values"
            )
        if not self.cors_origins or not all(
            _is_loopback_origin(origin) for origin in self.cors_origins
        ):
            raise ValueError("cors_origins must contain only exact HTTP loopback origins")


class _AnalyzerCapacity:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self._in_flight = 0
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        with self._lock:
            if self._in_flight >= self.maximum:
                return False
            self._in_flight += 1
            return True

    def release(self) -> None:
        with self._lock:
            self._in_flight -= 1

    def snapshot(self) -> int:
        with self._lock:
            return self._in_flight


class BodyTooLarge(Exception):
    pass


def _is_loopback_authority(authority: str) -> bool:
    if not authority or any(character.isspace() for character in authority):
        return False
    if authority.startswith("["):
        closing_bracket = authority.find("]")
        if closing_bracket < 0:
            return False
        host = authority[1:closing_bracket]
        separator = authority[closing_bracket + 1 : closing_bracket + 2]
        port_text = authority[closing_bracket + 2 :]
    else:
        host, separator, port_text = authority.rpartition(":")
        if ":" in host:
            return False
    if separator != ":" or host not in {"127.0.0.1", "localhost", "::1"}:
        return False
    if not port_text.isascii() or not port_text.isdecimal():
        return False
    return 1 <= int(port_text) <= 65535


def _is_loopback_origin(origin: str) -> bool:
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "http"
        and parsed.netloc != ""
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        and parsed.username is None
        and parsed.password is None
        and port is not None
        and parsed.path == ""
        and parsed.query == ""
        and parsed.fragment == ""
        and origin == f"http://{parsed.netloc}"
    )


class LocalRequestBoundaryMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_hosts: tuple[str, ...],
        allowed_origins: tuple[str, ...],
    ) -> None:
        self.app = app
        self.allowed_hosts = frozenset(allowed_hosts)
        self.allowed_origins = frozenset(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", [])
        hosts = [value.decode("latin-1") for key, value in headers if key.lower() == b"host"]
        if len(hosts) != 1 or hosts[0] not in self.allowed_hosts:
            response = JSONResponse(
                status_code=403,
                content=_error_payload(
                    "API_HOST_NOT_ALLOWED",
                    code="HOST_NOT_ALLOWED",
                    category="local-security",
                ),
            )
            await response(scope, receive, send)
            return

        origins = [value.decode("latin-1") for key, value in headers if key.lower() == b"origin"]
        if len(origins) > 1 or (origins and origins[0] not in self.allowed_origins):
            response = JSONResponse(
                status_code=403,
                content=_error_payload(
                    "API_ORIGIN_NOT_ALLOWED",
                    code="ORIGIN_NOT_ALLOWED",
                    category="local-security",
                ),
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def _error_payload(message_key: str, *, code: str, category: str) -> dict[str, str]:
    return {
        "error": code,
        "category": category,
        "message_key": message_key,
    }


def _nonnegative_int(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _consume_future_exception(future: asyncio.Future[Any]) -> None:
    if not future.cancelled():
        with suppress(Exception):
            future.exception()


def _resource_payload(
    observation: Any,
    *,
    in_flight: int,
    max_in_flight: int,
) -> dict[str, Any]:
    source = observation if type(observation) is dict else {}
    elapsed = source.get("elapsed_ms")
    if type(elapsed) not in {int, float} or not isfinite(elapsed) or elapsed < 0:
        elapsed = 0.0

    gpu_source = source.get("gpu")
    gpu: dict[str, Any] = {"status": "unavailable"}
    if type(gpu_source) is dict and gpu_source.get("status") == "observed":
        device_count = _nonnegative_int(gpu_source.get("device_count"))
        total_vram = _nonnegative_int(gpu_source.get("total_vram_bytes"))
        used_vram = _nonnegative_int(gpu_source.get("used_vram_bytes"))
        utilization = _nonnegative_int(gpu_source.get("maximum_utilization_percent"))
        temperature = gpu_source.get("maximum_temperature_c")
        if (
            device_count is not None
            and device_count >= 1
            and total_vram is not None
            and used_vram is not None
            and used_vram <= total_vram
            and utilization is not None
            and utilization <= 100
            and type(temperature) is int
            and -100 <= temperature <= 300
        ):
            gpu = {
                "status": "observed",
                "device_count": device_count,
                "total_vram_bytes": total_vram,
                "used_vram_bytes": used_vram,
                "maximum_utilization_percent": utilization,
                "maximum_temperature_c": temperature,
            }

    return {
        "schema_version": "live-resource-observation-v1",
        "policy_version": "live-resource-policy-v1",
        "elapsed_ms": elapsed,
        "process_rss_bytes": _nonnegative_int(source.get("process_rss_bytes")),
        "host_available_memory_bytes": _nonnegative_int(source.get("host_available_memory_bytes")),
        "in_flight": in_flight,
        "max_in_flight": max_in_flight,
        "gpu": gpu,
    }


def _evidence_json(evidence: BarcodeFrameEvidence) -> dict[str, Any]:
    box = None
    if evidence.barcode_box is not None:
        box = {
            "x0": evidence.barcode_box.x0,
            "y0": evidence.barcode_box.y0,
            "x1": evidence.barcode_box.x1,
            "y1": evidence.barcode_box.y1,
        }
    quality = None
    if evidence.quality is not None:
        quality = {
            "area_normalized": evidence.quality.area_normalized,
            "short_side_px": evidence.quality.short_side_px,
            "margin_left": evidence.quality.margin_left,
            "margin_right": evidence.quality.margin_right,
            "margin_top": evidence.quality.margin_top,
            "margin_bottom": evidence.quality.margin_bottom,
            "laplacian_variance": evidence.quality.laplacian_variance,
            "aspect_ratio": evidence.quality.aspect_ratio,
            "exposure_mean": evidence.quality.exposure_mean,
        }
    return {
        "count_status": evidence.count_status.value,
        "barcode_box": box,
        "proposal_sources": list(evidence.proposal_sources),
        "elapsed_ms": evidence.elapsed_ms,
        "recipe_version": evidence.recipe_version,
        "readiness": evidence.readiness.value,
        "guidance_action": evidence.guidance_action.value,
        "failing_gates": list(evidence.failing_gates),
        "quality": quality,
    }


async def _read_request_body_limited(request: Request, max_body_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_body_bytes:
            raise BodyTooLarge
        chunks.append(chunk)
    return b"".join(chunks)


async def _extract_image_bytes(request: Request, max_body_bytes: int) -> bytes:
    content_type = (request.headers.get("content-type") or "").lower()
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_body_bytes:
                raise BodyTooLarge
        except ValueError:
            pass

    body = await _read_request_body_limited(request, max_body_bytes)

    if "multipart/form-data" in content_type:

        async def body_stream():
            yield body

        parser = MultiPartParser(
            headers=request.headers,
            stream=body_stream(),
            max_files=1,
            max_fields=1,
            max_part_size=max_body_bytes,
        )
        # The entire multipart body has already passed the stricter global bound.
        # Keep parser scratch in memory so preview frames never become temp-file copies.
        parser.spool_max_size = max_body_bytes
        form = None
        try:
            form = await parser.parse()
            upload = form.get("image")
            if upload is None:
                for value in form.values():
                    if isinstance(value, StarletteUploadFile):
                        upload = value
                        break
            if not isinstance(upload, StarletteUploadFile):
                raise DecodeFailure(
                    FailureCode.INVALID_OR_CORRUPT_IMAGE,
                    "unsupported-input",
                    "API_IMAGE_FIELD_MISSING",
                )
            encoded = await upload.read(max_body_bytes + 1)
            if len(encoded) > max_body_bytes:
                raise BodyTooLarge
            return encoded
        except (BodyTooLarge, DecodeFailure):
            raise
        except Exception:
            raise DecodeFailure(
                FailureCode.INVALID_OR_CORRUPT_IMAGE,
                "unsupported-input",
                "API_MULTIPART_INVALID",
            ) from None
        finally:
            if form is not None:
                await form.close()
            else:
                for scratch in parser._files_to_close_on_error:
                    scratch.close()

    return body


def create_app(
    *,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    analyzer: Callable[..., BarcodeFrameEvidence] | None = None,
    resource_probe: Callable[..., dict[str, Any]] | None = None,
    settings: ApiSettings | None = None,
) -> FastAPI:
    cfg = settings if settings is not None else ApiSettings(max_body_bytes=max_body_bytes)
    run_analyze = analyzer or analyze_barcode_frame
    run_resource_probe = resource_probe or observe_live_resources
    capacity = _AnalyzerCapacity(cfg.max_in_flight)
    executor = ThreadPoolExecutor(
        max_workers=cfg.max_in_flight,
        thread_name_prefix="barcode-analyzer",
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(
        title="physical-vision-api",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(
        LocalRequestBoundaryMiddleware,
        allowed_hosts=cfg.allowed_hosts,
        allowed_origins=cfg.cors_origins,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/system/resources")
    def resources() -> dict[str, Any]:
        in_flight = capacity.snapshot()
        try:
            observation = run_resource_probe(
                in_flight=in_flight,
                max_in_flight=cfg.max_in_flight,
                gpu_timeout_seconds=cfg.resource_probe_timeout_seconds,
            )
        except Exception:
            observation = None
        return _resource_payload(
            observation,
            in_flight=in_flight,
            max_in_flight=cfg.max_in_flight,
        )

    @app.post("/v1/barcode/analyze")
    async def barcode_analyze(request: Request) -> JSONResponse:
        try:
            encoded = await _extract_image_bytes(request, cfg.max_body_bytes)
        except BodyTooLarge:
            return JSONResponse(
                status_code=413,
                content=_error_payload(
                    "API_BODY_TOO_LARGE",
                    code="BODY_TOO_LARGE",
                    category="local-resource",
                ),
            )
        except DecodeFailure as exc:
            return JSONResponse(
                status_code=400,
                content=_error_payload(
                    exc.message_key,
                    code=exc.code.value,
                    category=exc.category,
                ),
            )

        if not encoded:
            return JSONResponse(
                status_code=400,
                content=_error_payload(
                    "API_IMAGE_EMPTY",
                    code="INVALID_IMAGE",
                    category="unsupported-input",
                ),
            )

        try:
            image = decode_image(encoded, _API_DECODE_CONFIG)
        except DecodeFailure as exc:
            return JSONResponse(
                status_code=400,
                content=_error_payload(
                    exc.message_key,
                    code=exc.code.value,
                    category=exc.category,
                ),
            )

        if not capacity.try_acquire():
            return JSONResponse(
                status_code=503,
                content=_error_payload(
                    "API_ANALYZER_BUSY",
                    code="LOCAL_BUSY",
                    category="local-resource",
                ),
            )

        cancellation = threading.Event()
        deadline = monotonic() + cfg.analysis_timeout_seconds
        try:
            future: Future[BarcodeFrameEvidence] = executor.submit(
                run_analyze,
                image,
                DEFAULT_BARCODE_FRAME_CONFIG,
                deadline=deadline,
                cancelled=cancellation.is_set,
            )
        except Exception:
            capacity.release()
            return JSONResponse(
                status_code=500,
                content=_error_payload(
                    "API_ANALYZER_FAILED",
                    code="ANALYZER_FAILED",
                    category="internal",
                ),
            )

        future.add_done_callback(lambda _: capacity.release())
        wrapped = asyncio.wrap_future(future)
        wrapped.add_done_callback(_consume_future_exception)
        try:
            evidence = await asyncio.wait_for(
                asyncio.shield(wrapped), timeout=cfg.analysis_timeout_seconds
            )
        except TimeoutError:
            cancellation.set()
            with suppress(Exception):
                await asyncio.wait_for(asyncio.shield(wrapped), timeout=0.1)
            return JSONResponse(
                status_code=504,
                content=_error_payload(
                    "API_ANALYZER_TIMEOUT",
                    code="LOCAL_TIMEOUT",
                    category="timeout",
                ),
            )
        except asyncio.CancelledError:
            cancellation.set()
            with suppress(Exception):
                await asyncio.wait_for(asyncio.shield(wrapped), timeout=0.1)
            raise
        except BarcodeFrameFailure as exc:
            if exc.code is BarcodeFrameFailureCode.ANALYZE_BUDGET_EXCEEDED:
                return JSONResponse(
                    status_code=504,
                    content=_error_payload(
                        "API_ANALYZER_TIMEOUT",
                        code="LOCAL_TIMEOUT",
                        category="timeout",
                    ),
                )
            is_resource_budget = exc.code is BarcodeFrameFailureCode.IMAGE_BUDGET_EXCEEDED
            return JSONResponse(
                status_code=413 if is_resource_budget else 400,
                content=_error_payload(
                    f"API_{exc.code.value}",
                    code=exc.code.value,
                    category="local-resource" if is_resource_budget else "unsupported-input",
                ),
            )
        except Exception:
            return JSONResponse(
                status_code=500,
                content=_error_payload(
                    "API_ANALYZER_FAILED",
                    code="ANALYZER_FAILED",
                    category="internal",
                ),
            )

        return JSONResponse(status_code=200, content=_evidence_json(evidence))

    return app


def create_default_app() -> FastAPI:
    return create_app()


# ASGI entry for `uvicorn physical_vision_api.app:app`
app = create_default_app()
