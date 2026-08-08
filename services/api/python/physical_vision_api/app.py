from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from physical_vision_barcode import (
    DEFAULT_BARCODE_FRAME_CONFIG,
    BarcodeFrameEvidence,
    BarcodeFrameFailure,
    analyze_barcode_frame,
)
from physical_vision_image import (
    DEFAULT_DECODE_CONFIG,
    DecodeConfig,
    DecodeFailure,
    FailureCode,
    decode_image,
)
from starlette.datastructures import UploadFile as StarletteUploadFile

# Default ~4 MiB encoded frame budget for live samples (tighter than full B06 upload).
DEFAULT_MAX_BODY_BYTES = 4_000_000
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
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
        "http://127.0.0.1:8080",
        "http://localhost:8080",
        "null",  # file:// origin for static open
    )


class BodyTooLarge(Exception):
    pass


def _error_payload(message_key: str, *, code: str, category: str) -> dict[str, str]:
    return {
        "error": code,
        "category": category,
        "message_key": message_key,
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
    return {
        "count_status": evidence.count_status.value,
        "barcode_box": box,
        "proposal_sources": list(evidence.proposal_sources),
        "elapsed_ms": evidence.elapsed_ms,
        "recipe_version": evidence.recipe_version,
    }


def _read_limited(data: bytes, max_body_bytes: int) -> bytes:
    if len(data) > max_body_bytes:
        raise BodyTooLarge
    return data


async def _extract_image_bytes(request: Request, max_body_bytes: int) -> bytes:
    content_type = (request.headers.get("content-type") or "").lower()
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_body_bytes:
                raise BodyTooLarge
        except ValueError:
            pass

    if "multipart/form-data" in content_type:
        form = await request.form()
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
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = await upload.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_body_bytes:
                raise BodyTooLarge
            chunks.append(chunk)
        return b"".join(chunks)

    body = await request.body()
    return _read_limited(body, max_body_bytes)


def create_app(
    *,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    analyzer: Callable[..., BarcodeFrameEvidence] | None = None,
    settings: ApiSettings | None = None,
) -> FastAPI:
    cfg = settings if settings is not None else ApiSettings(max_body_bytes=max_body_bytes)
    run_analyze = analyzer or analyze_barcode_frame

    app = FastAPI(title="physical-vision-api", version="0.1.0", docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

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

        try:
            evidence = run_analyze(image, DEFAULT_BARCODE_FRAME_CONFIG)
        except BarcodeFrameFailure as exc:
            status = 413 if "BUDGET" in exc.code.name else 400
            return JSONResponse(
                status_code=status,
                content=_error_payload(
                    exc.message_key,
                    code=exc.code.value,
                    category=exc.category,
                ),
            )

        return JSONResponse(status_code=200, content=_evidence_json(evidence))

    return app


def create_default_app() -> FastAPI:
    return create_app()


# ASGI entry for `uvicorn physical_vision_api.app:app`
app = create_default_app()
