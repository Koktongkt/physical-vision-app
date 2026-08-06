from __future__ import annotations

import warnings
import zlib
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO
from math import isfinite
from time import monotonic
from typing import BinaryIO

from PIL import Image, ImageOps, UnidentifiedImageError


class FailureCode(str, Enum):
    ANIMATED_OR_MULTIFRAME_UNSUPPORTED = "ANIMATED_OR_MULTIFRAME_UNSUPPORTED"
    DECODE_BUDGET_EXCEEDED = "DECODE_BUDGET_EXCEEDED"
    IMAGE_DIMENSIONS_UNSUPPORTED = "IMAGE_DIMENSIONS_UNSUPPORTED"
    INVALID_OR_CORRUPT_IMAGE = "INVALID_OR_CORRUPT_IMAGE"
    INPUT_TOO_LARGE = "INPUT_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"


class DecodeFailure(ValueError):
    def __init__(self, code: FailureCode, category: str, message_key: str) -> None:
        super().__init__(message_key)
        self.code = code
        self.category = category
        self.message_key = message_key


@dataclass(frozen=True, slots=True)
class DecodeConfig:
    version: str
    max_encoded_bytes: int
    max_width: int
    max_height: int
    max_pixels: int
    max_metadata_bytes: int
    max_decoded_bytes: int
    max_frames: int
    max_decode_seconds: float


DEFAULT_DECODE_CONFIG = DecodeConfig(
    version="decode-resource-policy-v1",
    max_encoded_bytes=20_000_000,
    max_width=12_000,
    max_height=12_000,
    max_pixels=40_000_000,
    max_metadata_bytes=1_000_000,
    max_decoded_bytes=160_000_000,
    max_frames=1,
    max_decode_seconds=5.0,
)


@dataclass(frozen=True, slots=True)
class OrientationTransform:
    orientation: int

    def source_to_canonical(self, point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        transforms = {
            1: (x, y),
            2: (1.0 - x, y),
            3: (1.0 - x, 1.0 - y),
            4: (x, 1.0 - y),
            5: (y, x),
            6: (1.0 - y, x),
            7: (1.0 - y, 1.0 - x),
            8: (y, 1.0 - x),
        }
        return transforms[self.orientation]

    def canonical_to_source(self, point: tuple[float, float]) -> tuple[float, float]:
        inverse_orientation = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 8, 7: 7, 8: 6}
        return OrientationTransform(inverse_orientation[self.orientation]).source_to_canonical(
            point
        )


@dataclass(frozen=True, slots=True)
class CanonicalImage:
    media_type: str
    source_size: tuple[int, int]
    canonical_size: tuple[int, int]
    frame_count: int
    mode: str
    encoded_size: int
    estimated_decoded_bytes: int
    metadata_bytes: int
    decode_elapsed_ms: float
    orientation: int
    transform: OrientationTransform
    _pixels: bytes = field(repr=False)

    def to_pillow(self) -> Image.Image:
        return Image.frombytes(self.mode, self.canonical_size, self._pixels)


def _bounded_zlib_size(compressed: bytes, remaining_budget: int) -> int:
    decompressor = zlib.decompressobj()
    expanded = decompressor.decompress(compressed, max(0, remaining_budget) + 1)
    if decompressor.unconsumed_tail or len(expanded) > remaining_budget:
        return remaining_budget + 1
    if not decompressor.eof:
        raise zlib.error("incomplete compressed PNG metadata")
    return len(expanded)


def _compressed_png_metadata(payload: bytes, chunk_type: bytes) -> tuple[int, bytes] | None:
    if b"\0" not in payload:
        return None
    keyword, remainder = payload.split(b"\0", 1)
    if chunk_type in (b"zTXt", b"iCCP"):
        if not remainder or remainder[0] != 0:
            return None
        return len(keyword) + 2, remainder[1:]
    if chunk_type != b"iTXt" or len(remainder) < 2:
        return None
    compression_flag, compression_method = remainder[:2]
    if compression_flag != 1 or compression_method != 0:
        return None
    international_fields = remainder[2:]
    if b"\0" not in international_fields:
        return None
    language, translated_and_text = international_fields.split(b"\0", 1)
    if b"\0" not in translated_and_text:
        return None
    translated, compressed = translated_and_text.split(b"\0", 1)
    overhead = len(keyword) + len(language) + len(translated) + 5
    return overhead, compressed


def _png_metadata_bytes(encoded: bytes, max_metadata_bytes: int) -> int:
    if not encoded.startswith(b"\x89PNG\r\n\x1a\n"):
        return 0
    offset = 8
    total = 0
    while offset + 12 <= len(encoded):
        length = int.from_bytes(encoded[offset : offset + 4], "big")
        chunk_type = encoded[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(encoded):
            return total
        if chunk_type and chunk_type[0] & 0x20:
            payload = encoded[offset + 8 : offset + 8 + length]
            compressed_metadata = _compressed_png_metadata(payload, chunk_type)
            if compressed_metadata is not None:
                overhead, compressed = compressed_metadata
                remaining = max_metadata_bytes - total - overhead
                total += overhead + _bounded_zlib_size(compressed, remaining)
            else:
                total += length
        offset = end
        if chunk_type == b"IEND":
            break
    return total


def _png_declared_dimensions(encoded: bytes) -> tuple[int, int] | None:
    if len(encoded) < 24 or encoded[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR":
        return None
    return (
        int.from_bytes(encoded[16:20], "big"),
        int.from_bytes(encoded[20:24], "big"),
    )


def _jpeg_metadata_bytes(encoded: bytes) -> int:
    if not encoded.startswith(b"\xff\xd8"):
        return 0
    offset = 2
    total = 0
    while offset + 1 < len(encoded):
        if encoded[offset] != 0xFF:
            break
        while offset < len(encoded) and encoded[offset] == 0xFF:
            offset += 1
        if offset >= len(encoded):
            break
        marker = encoded[offset]
        offset += 1
        if marker in (0xD9, 0xDA):
            break
        if marker in range(0xD0, 0xD8) or marker == 0x01:
            continue
        if offset + 2 > len(encoded):
            break
        segment_length = int.from_bytes(encoded[offset : offset + 2], "big")
        if segment_length < 2 or offset + segment_length > len(encoded):
            break
        if 0xE0 <= marker <= 0xEF or marker == 0xFE:
            total += segment_length - 2
        offset += segment_length
    return total


def _metadata_bytes(encoded: bytes, max_metadata_bytes: int) -> int:
    return _png_metadata_bytes(encoded, max_metadata_bytes) + _jpeg_metadata_bytes(encoded)


def _png_end_offset(encoded: bytes) -> int | None:
    if not encoded.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    offset = 8
    while offset + 12 <= len(encoded):
        length = int.from_bytes(encoded[offset : offset + 4], "big")
        chunk_type = encoded[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(encoded):
            return None
        if chunk_type == b"IEND":
            return end
        offset = end
    return None


def _jpeg_end_offset(encoded: bytes) -> int | None:
    if not encoded.startswith(b"\xff\xd8"):
        return None
    offset = 2
    in_scan = False
    while offset < len(encoded):
        if in_scan:
            marker_start = encoded.find(b"\xff", offset)
            if marker_start < 0 or marker_start + 1 >= len(encoded):
                return None
            marker_offset = marker_start + 1
            while marker_offset < len(encoded) and encoded[marker_offset] == 0xFF:
                marker_offset += 1
            if marker_offset >= len(encoded):
                return None
            marker = encoded[marker_offset]
            if marker == 0x00 or marker in range(0xD0, 0xD8):
                offset = marker_offset + 1
                continue
            offset = marker_offset + 1
            in_scan = False
        else:
            if encoded[offset] != 0xFF:
                return None
            while offset < len(encoded) and encoded[offset] == 0xFF:
                offset += 1
            if offset >= len(encoded):
                return None
            marker = encoded[offset]
            offset += 1
        if marker == 0xD9:
            return offset
        if marker in range(0xD0, 0xD8) or marker == 0x01:
            continue
        if offset + 2 > len(encoded):
            return None
        segment_length = int.from_bytes(encoded[offset : offset + 2], "big")
        if segment_length < 2 or offset + segment_length > len(encoded):
            return None
        offset += segment_length
        if marker == 0xDA:
            in_scan = True
    return None


def _reject_trailing_payload(encoded: bytes) -> None:
    recognized_png = encoded.startswith(b"\x89PNG\r\n\x1a\n")
    recognized_jpeg = encoded.startswith(b"\xff\xd8")
    end_offset = _png_end_offset(encoded) if recognized_png else _jpeg_end_offset(encoded)
    if (recognized_png or recognized_jpeg) and end_offset != len(encoded):
        raise DecodeFailure(
            FailureCode.INVALID_OR_CORRUPT_IMAGE,
            "unsupported-input",
            (
                "IMAGE_INVALID_OR_CORRUPT"
                if end_offset is None
                else "IMAGE_TRAILING_PAYLOAD_REJECTED"
            ),
        )


def _read_encoded(encoded: bytes | BinaryIO, max_encoded_bytes: int) -> bytes:
    if isinstance(encoded, bytes):
        return encoded
    chunks: list[bytes] = []
    remaining = max_encoded_bytes + 1
    while remaining > 0:
        chunk = encoded.read(min(65_536, remaining))
        if not chunk:
            break
        if not isinstance(chunk, bytes):
            raise TypeError("binary image stream must return bytes")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


@contextmanager
def _decompression_bomb_warnings_are_errors():
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        yield


def _check_time_budget(
    config: DecodeConfig,
    started_at: float,
    deadline: float | None,
    cancelled: Callable[[], bool] | None,
    clock: Callable[[], float],
) -> float:
    if cancelled is not None and cancelled():
        raise DecodeFailure(
            FailureCode.DECODE_BUDGET_EXCEEDED,
            "local-resource",
            "IMAGE_DECODE_CANCELLED",
        )
    now = clock()
    if deadline is not None and now > deadline:
        raise DecodeFailure(
            FailureCode.DECODE_BUDGET_EXCEEDED,
            "timeout",
            "IMAGE_DECODE_DEADLINE_EXCEEDED",
        )
    if now - started_at > config.max_decode_seconds:
        raise DecodeFailure(
            FailureCode.DECODE_BUDGET_EXCEEDED,
            "timeout",
            "IMAGE_DECODE_TIME_BUDGET_EXCEEDED",
        )
    return now


def _validate_config(config: DecodeConfig) -> None:
    if type(config) is not DecodeConfig:
        raise ValueError("decode configuration must use the registered frozen type")
    if type(config.version) is not str or config.version != "decode-resource-policy-v1":
        raise ValueError("decode configuration version is not registered")
    integer_fields = (
        config.max_encoded_bytes,
        config.max_width,
        config.max_height,
        config.max_pixels,
        config.max_metadata_bytes,
        config.max_decoded_bytes,
        config.max_frames,
    )
    if any(type(value) is not int or value <= 0 for value in integer_fields):
        raise ValueError("decode configuration integer guards must be positive exact integers")
    if config.max_frames != 1:
        raise ValueError("decode configuration accepts exactly one frame")
    if (
        type(config.max_decode_seconds) is not float
        or not isfinite(config.max_decode_seconds)
        or config.max_decode_seconds <= 0.0
    ):
        raise ValueError("decode configuration time guard must be a positive finite float")


def decode_image(
    encoded: bytes | BinaryIO,
    config: DecodeConfig,
    *,
    deadline: float | None = None,
    cancelled: Callable[[], bool] | None = None,
    clock: Callable[[], float] = monotonic,
) -> CanonicalImage:
    _validate_config(config)
    started_at = clock()
    _check_time_budget(config, started_at, deadline, cancelled, clock)
    encoded = _read_encoded(encoded, config.max_encoded_bytes)
    _check_time_budget(config, started_at, deadline, cancelled, clock)
    if len(encoded) > config.max_encoded_bytes:
        raise DecodeFailure(
            FailureCode.INPUT_TOO_LARGE,
            "local-resource",
            "IMAGE_INPUT_TOO_LARGE",
        )
    try:
        metadata_bytes = _metadata_bytes(encoded, config.max_metadata_bytes)
    except zlib.error as error:
        raise DecodeFailure(
            FailureCode.INVALID_OR_CORRUPT_IMAGE,
            "unsupported-input",
            "IMAGE_INVALID_OR_CORRUPT",
        ) from error
    if metadata_bytes > config.max_metadata_bytes:
        raise DecodeFailure(
            FailureCode.DECODE_BUDGET_EXCEEDED,
            "local-resource",
            "IMAGE_METADATA_BUDGET_EXCEEDED",
        )
    _reject_trailing_payload(encoded)
    declared_dimensions = _png_declared_dimensions(encoded)
    if declared_dimensions is not None:
        width, height = declared_dimensions
        if (
            width <= 0
            or height <= 0
            or width > config.max_width
            or height > config.max_height
            or width * height > config.max_pixels
        ):
            raise DecodeFailure(
                FailureCode.IMAGE_DIMENSIONS_UNSUPPORTED,
                "unsupported-input",
                "IMAGE_DIMENSIONS_UNSUPPORTED",
            )
    try:
        with _decompression_bomb_warnings_are_errors(), Image.open(BytesIO(encoded)) as source:
            frame_count = getattr(source, "n_frames", 1)
            if frame_count > config.max_frames:
                raise DecodeFailure(
                    FailureCode.ANIMATED_OR_MULTIFRAME_UNSUPPORTED,
                    "unsupported-input",
                    "IMAGE_ANIMATED_OR_MULTIFRAME_UNSUPPORTED",
                )
            media_types = {"JPEG": "image/jpeg", "PNG": "image/png"}
            if source.format not in media_types:
                raise DecodeFailure(
                    FailureCode.UNSUPPORTED_MEDIA_TYPE,
                    "unsupported-input",
                    "IMAGE_MEDIA_TYPE_UNSUPPORTED",
                )
            _check_time_budget(config, started_at, deadline, cancelled, clock)
            width, height = source.size
            if (
                width <= 0
                or height <= 0
                or width > config.max_width
                or height > config.max_height
                or width * height > config.max_pixels
            ):
                raise DecodeFailure(
                    FailureCode.IMAGE_DIMENSIONS_UNSUPPORTED,
                    "unsupported-input",
                    "IMAGE_DIMENSIONS_UNSUPPORTED",
                )
            estimated_decoded_bytes = width * height * max(3, len(source.getbands()))
            if estimated_decoded_bytes > config.max_decoded_bytes:
                raise DecodeFailure(
                    FailureCode.DECODE_BUDGET_EXCEEDED,
                    "local-resource",
                    "IMAGE_DECODE_MEMORY_BUDGET_EXCEEDED",
                )
            source.load()
            _check_time_budget(config, started_at, deadline, cancelled, clock)
            orientation = int(source.getexif().get(274, 1))
            if orientation not in range(1, 9):
                orientation = 1
            canonical = ImageOps.exif_transpose(source).convert("RGB")
            canonical.load()
            canonical_width, canonical_height = canonical.size
            if (
                canonical_width > config.max_width
                or canonical_height > config.max_height
                or canonical_width * canonical_height > config.max_pixels
            ):
                raise DecodeFailure(
                    FailureCode.IMAGE_DIMENSIONS_UNSUPPORTED,
                    "unsupported-input",
                    "IMAGE_DIMENSIONS_UNSUPPORTED",
                )
            finished_at = _check_time_budget(
                config,
                started_at,
                deadline,
                cancelled,
                clock,
            )
            media_type = media_types[source.format]
            return CanonicalImage(
                media_type=media_type,
                source_size=source.size,
                canonical_size=canonical.size,
                frame_count=frame_count,
                mode=canonical.mode,
                encoded_size=len(encoded),
                estimated_decoded_bytes=estimated_decoded_bytes,
                metadata_bytes=metadata_bytes,
                decode_elapsed_ms=round((finished_at - started_at) * 1000, 3),
                orientation=orientation,
                transform=OrientationTransform(orientation),
                _pixels=canonical.tobytes(),
            )
    except DecodeFailure:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise DecodeFailure(
            FailureCode.DECODE_BUDGET_EXCEEDED,
            "local-resource",
            "IMAGE_DECOMPRESSION_BOMB_REJECTED",
        ) from error
    except (OSError, SyntaxError, UnidentifiedImageError, ValueError) as error:
        raise DecodeFailure(
            FailureCode.INVALID_OR_CORRUPT_IMAGE,
            "unsupported-input",
            "IMAGE_INVALID_OR_CORRUPT",
        ) from error
