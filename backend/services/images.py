"""Pillow helpers for the screenshot path.

Kept apart from the OCR engines because two callers need them: the OCR
adapters want the pixel size to normalise boxes, and the VLM wants a
smaller copy of the image than the OCR read. Neither needs OpenCV.
"""

import io
import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

# iPhone photos are HEIC; iPhone screenshots are PNG. The opener is optional
# because pillow-heif ships native libheif and lives in the ocr-fallback
# extra. Without it a HEIC upload is refused at the route, not at decode.
try:  # pragma: no cover - depends on the optional extra being installed
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:  # pragma: no cover
    HEIF_SUPPORTED = False


def image_size(path: Path) -> tuple[int, int]:
    """(width, height) in pixels, or (0, 0) for anything Pillow cannot open.

    Zero rather than raising: the size only normalises OCR boxes, and an
    engine that can decode a format Pillow cannot (Vision reads HEIC
    natively) should not lose its text over a missing dimension.
    """
    try:
        with Image.open(path) as im:
            return im.size
    except Exception as exc:
        logger.debug("Could not read image size of %s: %s", path.name, exc)
        return 0, 0


def downscaled_jpeg(path: Path, max_side: int, *, quality: int = 88) -> bytes:
    """The image re-encoded as JPEG with its longest side at most max_side.

    A retina iPhone capture is 1179x2556 and base64 of the PNG runs past a
    megabyte; the caption a VLM writes does not need those pixels, and the
    OCR has already read them at full resolution. Alpha is flattened onto
    white because JPEG has no alpha and a transparent screenshot region is
    visually white on the device anyway.
    """
    with Image.open(path) as im:
        im.load()
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            flat = Image.new("RGB", rgba.size, "white")
            flat.paste(rgba, mask=rgba.getchannel("A"))
            im = flat
        elif im.mode != "RGB":
            im = im.convert("RGB")
        width, height = im.size
        longest = max(width, height)
        if longest > max_side:
            scale = max_side / longest
            im = im.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.LANCZOS)
        buffer = io.BytesIO()
        im.save(buffer, format="JPEG", quality=quality, optimize=True)
        return buffer.getvalue()
