"""Pillow helpers shared by the OCR adapters and the VLM call."""

import io

from PIL import Image

from config import SCREENSHOTS_DIR
from services.images import downscaled_jpeg, image_size


def _png(width: int, height: int, mode: str = "RGB", name: str = "size.png"):
    path = SCREENSHOTS_DIR / name
    Image.new(mode, (width, height), (200, 30, 30, 255) if mode == "RGBA" else "white").save(path)
    return path


def test_image_size_reads_pixels():
    assert image_size(_png(1179, 2556)) == (1179, 2556)


def test_image_size_is_zero_for_undecodable_bytes():
    path = SCREENSHOTS_DIR / "not-an-image.png"
    path.write_bytes(b"\x89PNG but not really")

    assert image_size(path) == (0, 0)


def test_downscale_caps_the_longest_side_and_keeps_aspect():
    data = downscaled_jpeg(_png(1179, 2556), max_side=1280)
    with Image.open(io.BytesIO(data)) as im:
        assert im.format == "JPEG"
        assert im.size == (590, 1280)


def test_downscale_never_upscales():
    data = downscaled_jpeg(_png(400, 300), max_side=1280)
    with Image.open(io.BytesIO(data)) as im:
        assert im.size == (400, 300)


def test_alpha_is_flattened_rather_than_rejected():
    """JPEG has no alpha; a transparent PNG must still encode."""
    data = downscaled_jpeg(_png(64, 64, mode="RGBA", name="alpha.png"), max_side=1280)
    with Image.open(io.BytesIO(data)) as im:
        assert im.mode == "RGB"
