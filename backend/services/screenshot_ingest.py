"""Screenshot source adapter: VLM output to Item plus SegmentDrafts.

One VLM call already returns both the readable text and a description of
the image. ARCHITECTURE_V2 section 2 keeps those apart, because one came
out of the artifact and the other is a model's guess about it, so they
become two Segments of one Item rather than one blended string.
"""

from datetime import datetime, timezone
from pathlib import Path

from services.chroma import hash_bytes
from services.indexing import SegmentDraft, index_item
from services.schema import Item, data_relative, provenance_for_screenshot
from services.text_utils import as_text

OCR_ORDINAL = 0
CAPTION_ORDINAL = 1

DEFAULT_TITLE = "Untitled Screenshot"


def screenshot_item(path: Path, vision_result: dict) -> Item:
    """The Item for one screenshot on disk.

    id is the file stem, which upload_screenshots minted as a uuid4, so
    re-processing the same file addresses the same segment ids instead of
    creating a second copy under a fresh id.

    created_at is empty on purpose. write_bytes resets mtime to upload
    time, so mtime would encode ingest time wearing a capture-time label,
    and migrate._backfill_record states the house rule: an empty string is
    honest, a plausible wrong value is not.
    """
    return Item(
        id=path.stem,
        source_type="screenshot",
        source_id=hash_bytes(path.read_bytes()),
        title=as_text(vision_result.get("title")) or DEFAULT_TITLE,
        created_at="",
        ingested_at=datetime.now(timezone.utc).isoformat(),
        provenance=provenance_for_screenshot(),
        raw_ref=data_relative(path),
    )


def screenshot_drafts(vision_result: dict) -> list[SegmentDraft]:
    """One Item, two epistemic objects, kept apart per section 2.

    The OCR draft is omitted rather than embedded empty when the image has
    no readable text. The caption draft is always present, because an Item
    with no segments would never enter Chroma and would therefore stay
    pending forever.
    """
    drafts: list[SegmentDraft] = []

    ocr = as_text(vision_result.get("extracted_text"))
    if ocr:
        drafts.append(SegmentDraft(
            ordinal=OCR_ORDINAL,
            modality="ocr",
            content=ocr,
            content_source="extracted",
        ))

    caption = (
        as_text(vision_result.get("description"))
        or as_text(vision_result.get("title"))
        or DEFAULT_TITLE
    )
    drafts.append(SegmentDraft(
        ordinal=CAPTION_ORDINAL,
        modality="caption",
        content=caption,
        content_source="generated",
    ))
    return drafts


async def index_screenshot(path: Path, vision_result: dict) -> int:
    """Write one analysed screenshot to the knowledge base."""
    item = screenshot_item(path, vision_result)
    return await index_item(item, screenshot_drafts(vision_result))
