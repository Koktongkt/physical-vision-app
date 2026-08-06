from __future__ import annotations

import zlib
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from io import BytesIO

import pytest
from physical_vision_image import (
    DEFAULT_DECODE_CONFIG,
    DecodeFailure,
    FailureCode,
    decode_image,
)
from PIL import Image, ImageOps, PngImagePlugin


def encoded_image(format_name: str, *, size: tuple[int, int] = (3, 2)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, (12, 34, 56)).save(output, format=format_name)
    return output.getvalue()


def oriented_jpeg(orientation: int) -> bytes:
    image = Image.new("RGB", (4, 3))
    image.putdata(
        [
            (255, 0, 0),
            (0, 255, 0),
            (0, 0, 255),
            (255, 255, 0),
            (255, 0, 255),
            (0, 255, 255),
            (64, 64, 64),
            (192, 192, 192),
            (10, 20, 30),
            (40, 50, 60),
            (70, 80, 90),
            (100, 110, 120),
        ]
    )
    exif = Image.Exif()
    exif[274] = orientation
    output = BytesIO()
    image.save(output, format="JPEG", quality=100, subsampling=0, exif=exif)
    return output.getvalue()


def animated_image(format_name: str) -> bytes:
    output = BytesIO()
    frames = [Image.new("RGB", (2, 2), color) for color in ("red", "blue")]
    frames[0].save(
        output,
        format=format_name,
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
    )
    return output.getvalue()


def image_with_metadata(format_name: str) -> bytes:
    output = BytesIO()
    image = Image.new("RGB", (2, 2), "green")
    if format_name == "PNG":
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("synthetic", "x" * 32)
        image.save(output, format="PNG", pnginfo=metadata)
    else:
        exif = Image.Exif()
        exif[270] = "x" * 32
        image.save(output, format="JPEG", exif=exif)
    return output.getvalue()


def png_with_compressed_metadata(expanded_size: int, *, international: bool = False) -> bytes:
    output = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    if international:
        metadata.add_itxt("synthetic", "x" * expanded_size, zip=True)
    else:
        metadata.add_text("synthetic", "x" * expanded_size, zip=True)
    Image.new("RGB", (2, 2), "green").save(output, format="PNG", pnginfo=metadata)
    return output.getvalue()


def png_with_corrupt_compressed_metadata() -> bytes:
    encoded = bytearray(png_with_compressed_metadata(5_000))
    chunk_offset = encoded.index(b"zTXt") - 4
    chunk_length = int.from_bytes(encoded[chunk_offset : chunk_offset + 4], "big")
    payload_start = chunk_offset + 8
    compressed_start = encoded.index(0, payload_start, payload_start + chunk_length) + 2
    encoded[compressed_start : payload_start + chunk_length] = b"\0" * (
        payload_start + chunk_length - compressed_start
    )
    crc_input = encoded[chunk_offset + 4 : payload_start + chunk_length]
    encoded[payload_start + chunk_length : payload_start + chunk_length + 4] = zlib.crc32(
        crc_input
    ).to_bytes(4, "big")
    return bytes(encoded)


def png_with_compressed_icc_profile(expanded_size: int) -> bytes:
    encoded = encoded_image("PNG", size=(2, 2))
    payload = b"synthetic\0\0" + zlib.compress(b"x" * expanded_size)
    chunk_type = b"iCCP"
    chunk = (
        len(payload).to_bytes(4, "big")
        + chunk_type
        + payload
        + zlib.crc32(chunk_type + payload).to_bytes(4, "big")
    )
    ihdr_end = 8 + 12 + 13
    return encoded[:ihdr_end] + chunk + encoded[ihdr_end:]


def png_with_declared_dimensions(width: int, height: int) -> bytes:
    encoded = bytearray(encoded_image("PNG", size=(1, 1)))
    encoded[16:20] = width.to_bytes(4, "big")
    encoded[20:24] = height.to_bytes(4, "big")
    encoded[29:33] = zlib.crc32(encoded[12:29]).to_bytes(4, "big")
    return bytes(encoded)


@pytest.mark.parametrize(
    ("format_name", "media_type"),
    (("JPEG", "image/jpeg"), ("PNG", "image/png")),
)
def test_decode_accepts_supported_single_frame_stills(
    format_name: str,
    media_type: str,
) -> None:
    decoded = decode_image(encoded_image(format_name), DEFAULT_DECODE_CONFIG)

    assert decoded.media_type == media_type
    assert decoded.source_size == (3, 2)
    assert decoded.canonical_size == (3, 2)
    assert decoded.frame_count == 1
    assert decoded.mode == "RGB"
    pixel = decoded.to_pillow().getpixel((0, 0))
    assert all(
        abs(actual - expected) <= 1 for actual, expected in zip(pixel, (12, 34, 56), strict=False)
    )


def test_encoded_byte_guard_accepts_boundary_and_rejects_one_byte_over() -> None:
    encoded = encoded_image("PNG")
    at_boundary = replace(DEFAULT_DECODE_CONFIG, max_encoded_bytes=len(encoded))
    over_boundary = replace(DEFAULT_DECODE_CONFIG, max_encoded_bytes=len(encoded) - 1)

    assert decode_image(encoded, at_boundary).encoded_size == len(encoded)
    with pytest.raises(DecodeFailure) as caught:
        decode_image(encoded, over_boundary)

    assert caught.value.code is FailureCode.INPUT_TOO_LARGE
    assert caught.value.category == "local-resource"
    assert str(caught.value) == "IMAGE_INPUT_TOO_LARGE"


@pytest.mark.parametrize("encoded", (b"not an image", b"\x89PNG\r\n\x1a\ntruncated"))
def test_malformed_input_returns_stable_corrupt_image_failure(encoded: bytes) -> None:
    with pytest.raises(DecodeFailure) as caught:
        decode_image(encoded, DEFAULT_DECODE_CONFIG)

    assert caught.value.code is FailureCode.INVALID_OR_CORRUPT_IMAGE
    assert caught.value.category == "unsupported-input"
    assert caught.value.message_key == "IMAGE_INVALID_OR_CORRUPT"


@pytest.mark.parametrize("orientation", range(1, 9))
def test_exif_orientation_is_applied_once_with_reversible_normalized_transform(
    orientation: int,
) -> None:
    encoded = oriented_jpeg(orientation)
    with Image.open(BytesIO(encoded)) as source:
        expected = ImageOps.exif_transpose(source).convert("RGB")
        expected.load()

    decoded = decode_image(encoded, DEFAULT_DECODE_CONFIG)

    assert decoded.orientation == orientation
    assert decoded.source_size == (4, 3)
    assert decoded.canonical_size == expected.size
    assert decoded.to_pillow().tobytes() == expected.tobytes()
    assert decoded.to_pillow().getexif().get(274, 1) == 1
    expected_origin = {
        1: (0.0, 0.0),
        2: (1.0, 0.0),
        3: (1.0, 1.0),
        4: (0.0, 1.0),
        5: (0.0, 0.0),
        6: (1.0, 0.0),
        7: (1.0, 1.0),
        8: (0.0, 1.0),
    }
    assert decoded.transform.source_to_canonical((0.0, 0.0)) == expected_origin[orientation]
    for point in ((0.0, 0.0), (0.2, 0.7), (1.0, 1.0)):
        canonical = decoded.transform.source_to_canonical(point)
        restored = decoded.transform.canonical_to_source(canonical)
        assert restored == pytest.approx(point)


def test_canonical_dimension_guard_is_rechecked_after_orientation_swap() -> None:
    encoded = oriented_jpeg(6)
    source_only_fit = replace(DEFAULT_DECODE_CONFIG, max_width=4, max_height=3)

    with pytest.raises(DecodeFailure) as caught:
        decode_image(encoded, source_only_fit)

    assert caught.value.code is FailureCode.IMAGE_DIMENSIONS_UNSUPPORTED


@pytest.mark.parametrize(
    ("field", "boundary", "failure_code"),
    (
        ("max_width", 4, FailureCode.IMAGE_DIMENSIONS_UNSUPPORTED),
        ("max_height", 3, FailureCode.IMAGE_DIMENSIONS_UNSUPPORTED),
        ("max_pixels", 12, FailureCode.IMAGE_DIMENSIONS_UNSUPPORTED),
        ("max_decoded_bytes", 36, FailureCode.DECODE_BUDGET_EXCEEDED),
    ),
)
def test_dimension_pixel_and_memory_guards_are_inclusive_at_the_boundary(
    field: str,
    boundary: int,
    failure_code: FailureCode,
) -> None:
    encoded = encoded_image("PNG", size=(4, 3))

    assert decode_image(encoded, replace(DEFAULT_DECODE_CONFIG, **{field: boundary}))
    with pytest.raises(DecodeFailure) as caught:
        decode_image(encoded, replace(DEFAULT_DECODE_CONFIG, **{field: boundary - 1}))

    assert caught.value.code is failure_code


@pytest.mark.parametrize("format_name", ("PNG", "GIF"))
def test_animated_and_multiframe_media_is_rejected_before_format_acceptance(
    format_name: str,
) -> None:
    with pytest.raises(DecodeFailure) as caught:
        decode_image(animated_image(format_name), DEFAULT_DECODE_CONFIG)

    assert caught.value.code is FailureCode.ANIMATED_OR_MULTIFRAME_UNSUPPORTED


def test_decoded_static_format_outside_jpeg_png_allowlist_is_unsupported() -> None:
    with pytest.raises(DecodeFailure) as caught:
        decode_image(encoded_image("BMP"), DEFAULT_DECODE_CONFIG)

    assert caught.value.code is FailureCode.UNSUPPORTED_MEDIA_TYPE


@pytest.mark.parametrize("format_name", ("JPEG", "PNG"))
def test_metadata_budget_is_measured_and_inclusive_at_boundary(format_name: str) -> None:
    encoded = image_with_metadata(format_name)
    measured = decode_image(encoded, DEFAULT_DECODE_CONFIG).metadata_bytes

    assert measured > 0
    assert decode_image(encoded, replace(DEFAULT_DECODE_CONFIG, max_metadata_bytes=measured))
    with pytest.raises(DecodeFailure) as caught:
        decode_image(
            encoded,
            replace(DEFAULT_DECODE_CONFIG, max_metadata_bytes=measured - 1),
        )

    assert caught.value.code is FailureCode.DECODE_BUDGET_EXCEEDED


@pytest.mark.parametrize("format_name", ("JPEG", "PNG"))
def test_trailing_alternate_payload_is_rejected(format_name: str) -> None:
    polyglot = encoded_image(format_name) + b"synthetic-alternate-payload"

    with pytest.raises(DecodeFailure) as caught:
        decode_image(polyglot, DEFAULT_DECODE_CONFIG)

    assert caught.value.code is FailureCode.INVALID_OR_CORRUPT_IMAGE


def test_binary_stream_is_bounded_and_canonical_pixels_survive_stream_close() -> None:
    encoded = encoded_image("PNG")
    stream = BytesIO(encoded)

    decoded = decode_image(stream, DEFAULT_DECODE_CONFIG)
    stream.close()

    assert decoded.to_pillow().size == (3, 2)
    assert decoded.encoded_size == len(encoded)


class SequenceClock:
    def __init__(self, values: tuple[float, ...]) -> None:
        self._values = iter(values)
        self._last = values[-1]

    def __call__(self) -> float:
        return next(self._values, self._last)


def test_cancellation_deadline_and_elapsed_decode_budget_fail_cooperatively() -> None:
    encoded = encoded_image("PNG")
    cases = (
        {"cancelled": lambda: True},
        {"deadline": 9.0, "clock": SequenceClock((10.0,))},
        {
            "clock": SequenceClock((1.0, 1.0, 1.6)),
            "config": replace(DEFAULT_DECODE_CONFIG, max_decode_seconds=0.5),
        },
    )

    for case in cases:
        config = case.pop("config", DEFAULT_DECODE_CONFIG)
        with pytest.raises(DecodeFailure) as caught:
            decode_image(encoded, config, **case)
        assert caught.value.code is FailureCode.DECODE_BUDGET_EXCEEDED


def test_decode_time_and_deadline_guards_are_inclusive_at_exact_boundary() -> None:
    encoded = encoded_image("PNG")
    config = replace(DEFAULT_DECODE_CONFIG, max_decode_seconds=0.5)

    decoded = decode_image(
        encoded,
        config,
        deadline=1.5,
        clock=SequenceClock((1.0, 1.0, 1.0, 1.0, 1.0, 1.5)),
    )

    assert decoded.decode_elapsed_ms == 500.0


def test_pillow_decompression_bomb_error_is_a_typed_budget_rejection() -> None:
    encoded = png_with_declared_dimensions(20_000, 20_000)
    permissive_local_guards = replace(
        DEFAULT_DECODE_CONFIG,
        max_width=30_000,
        max_height=30_000,
        max_pixels=500_000_000,
        max_decoded_bytes=1_500_000_000,
    )

    with pytest.raises(DecodeFailure) as caught:
        decode_image(encoded, permissive_local_guards)

    assert caught.value.code is FailureCode.DECODE_BUDGET_EXCEEDED
    assert caught.value.message_key == "IMAGE_DECOMPRESSION_BOMB_REJECTED"


def test_decode_configuration_is_frozen_and_rejects_invalid_semantics() -> None:
    with pytest.raises(FrozenInstanceError):
        DEFAULT_DECODE_CONFIG.max_pixels = 1

    invalid_configs = (
        replace(DEFAULT_DECODE_CONFIG, version=""),
        replace(DEFAULT_DECODE_CONFIG, max_encoded_bytes=0),
        replace(DEFAULT_DECODE_CONFIG, max_frames=2),
        replace(DEFAULT_DECODE_CONFIG, max_decode_seconds=0.0),
        replace(DEFAULT_DECODE_CONFIG, max_pixels=True),
    )
    for config in invalid_configs:
        with pytest.raises(ValueError, match="decode configuration"):
            decode_image(encoded_image("PNG"), config)


def test_zero_declared_dimension_is_rejected_as_unsupported_dimensions() -> None:
    with pytest.raises(DecodeFailure) as caught:
        decode_image(png_with_declared_dimensions(0, 1), DEFAULT_DECODE_CONFIG)

    assert caught.value.code is FailureCode.IMAGE_DIMENSIONS_UNSUPPORTED


@pytest.mark.parametrize("international", (False, True))
def test_compressed_metadata_expansion_is_bounded_before_pillow_decode(
    international: bool,
) -> None:
    encoded = png_with_compressed_metadata(5_000, international=international)
    config = replace(DEFAULT_DECODE_CONFIG, max_metadata_bytes=100)

    with pytest.raises(DecodeFailure) as caught:
        decode_image(encoded, config)

    assert caught.value.code is FailureCode.DECODE_BUDGET_EXCEEDED
    assert caught.value.message_key == "IMAGE_METADATA_BUDGET_EXCEEDED"


def test_corrupt_compressed_metadata_returns_typed_corrupt_failure() -> None:
    with pytest.raises(DecodeFailure) as caught:
        decode_image(png_with_corrupt_compressed_metadata(), DEFAULT_DECODE_CONFIG)

    assert caught.value.code is FailureCode.INVALID_OR_CORRUPT_IMAGE


def test_compressed_icc_profile_expansion_is_bounded_before_pillow_decode() -> None:
    config = replace(DEFAULT_DECODE_CONFIG, max_metadata_bytes=100)

    with pytest.raises(DecodeFailure) as caught:
        decode_image(png_with_compressed_icc_profile(5_000), config)

    assert caught.value.code is FailureCode.DECODE_BUDGET_EXCEEDED


def test_canonical_result_is_immutable_deterministic_and_returns_detached_copies() -> None:
    encoded = oriented_jpeg(6)
    clock = SequenceClock((1.0,))

    first = decode_image(encoded, DEFAULT_DECODE_CONFIG, clock=clock)
    second = decode_image(encoded, DEFAULT_DECODE_CONFIG, clock=SequenceClock((1.0,)))
    mutable_copy = first.to_pillow()
    original_pixel = second.to_pillow().getpixel((0, 0))
    mutable_copy.putpixel((0, 0), (0, 0, 0))

    assert first == second
    assert first.to_pillow().getpixel((0, 0)) == original_pixel
    assert "_pixels" not in repr(first)
    with pytest.raises(FrozenInstanceError):
        first.mode = "L"
    assert not hasattr(first, "encoded_bytes")


def test_bounded_deterministic_fuzz_corpus_never_crashes_decoder() -> None:
    corpus = [sha256(str(seed).encode()).digest() * 4 for seed in range(64)]
    for format_name in ("JPEG", "PNG"):
        encoded = encoded_image(format_name, size=(2, 2))
        corpus.extend(encoded[:cut] for cut in range(0, len(encoded), max(1, len(encoded) // 16)))

    for payload in corpus:
        with pytest.raises(DecodeFailure):
            decode_image(payload, DEFAULT_DECODE_CONFIG)
