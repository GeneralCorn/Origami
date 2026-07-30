"""Screenshot source adapter: VLM output to Item plus SegmentDrafts.

One VLM call already returns both the readable text and a description of
the image. ARCHITECTURE_V2 section 2 keeps those apart, because one came
out of the artifact and the other is a model's guess about it, so they
become two Segments of one Item rather than one blended string.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from services.chroma import hash_bytes
from services.indexing import SegmentDraft, index_item
from services.ingest import text_splitter
from services.schema import Item, data_relative, provenance_for_screenshot
from services.text_utils import as_text

logger = logging.getLogger(__name__)

CAPTION_ORDINAL = 0
FIRST_OCR_ORDINAL = 1

DEFAULT_TITLE = "Untitled Screenshot"


def screenshot_item(path: Path, vision_result: dict) -> Item:
    """The Item for one screenshot on disk.

    id is the full filename rather than the stem. Two files whose names
    differ only by extension share a stem, and a shared id means the
    second one's segments address the first one's records: one screenshot
    silently overwrote the other, and deleting either took both.

    created_at is empty on purpose. write_bytes resets mtime to upload
    time, so mtime would encode ingest time wearing a capture-time label,
    and migrate._backfill_record states the house rule: an empty string is
    honest, a plausible wrong value is not.
    """
    return Item(
        id=path.name,
        source_type="screenshot",
        source_id=hash_bytes(path.read_bytes()),
        title=as_text(vision_result.get("title")) or DEFAULT_TITLE,
        created_at="",
        ingested_at=datetime.now(timezone.utc).isoformat(),
        provenance=provenance_for_screenshot(),
        raw_ref=data_relative(path),
    )


def extracted_text(vision_result: dict) -> str:
    """The readable text the VLM reported, whatever shape it answered in.

    "Any readable text visible in the screenshot" is a field a model
    answers with a list of lines about as readily as with a string, and
    coercing anything non-string to "" dropped the OCR segment outright:
    the screenshot then counted as processed on the strength of its
    caption alone, so the text never came back. A list of scalars is
    joined; anything else is logged rather than discarded in silence,
    because the surviving record would otherwise be a model's guess about
    a screenshot whose actual contents Origami had read and thrown away.
    """
    raw = vision_result.get("extracted_text")
    if raw is None or isinstance(raw, str):
        return as_text(raw)
    if isinstance(raw, (list, tuple)):
        lines = [as_text(part) or (str(part) if isinstance(part, (int, float)) else "") for part in raw]
        joined = "\n".join(line for line in lines if line).strip()
        if joined:
            return joined
    logger.warning(
        "Discarding extracted_text of unusable type %s from the VLM", type(raw).__name__
    )
    return ""


def screenshot_drafts(vision_result: dict) -> list[SegmentDraft]:
    """One Item, two kinds of epistemic object, kept apart per section 2.

    The caption takes ordinal 0 and is always present, because an Item
    with no segments would never enter Chroma and would therefore stay
    pending forever. The OCR text follows from ordinal 1 and is split by
    the shared text_splitter: the embedder's window is 512 tokens, so an
    unsplit page of screenshotted text embedded only its first ~3,200
    characters and the rest was stored but unreachable by search.
    """
    caption = (
        as_text(vision_result.get("description"))
        or as_text(vision_result.get("title"))
        or DEFAULT_TITLE
    )
    drafts = [SegmentDraft(
        ordinal=CAPTION_ORDINAL,
        modality="caption",
        content=caption,
        content_source="generated",
    )]

    ocr = extracted_text(vision_result)
    for offset, chunk in enumerate(text_splitter.split_text(ocr) if ocr else []):
        drafts.append(SegmentDraft(
            ordinal=FIRST_OCR_ORDINAL + offset,
            modality="ocr",
            content=chunk,
            content_source="extracted",
        ))
    return drafts


async def index_screenshot(path: Path, vision_result: dict) -> int:
    """Write one analysed screenshot to the knowledge base."""
    item = screenshot_item(path, vision_result)
    return await index_item(item, screenshot_drafts(vision_result))
