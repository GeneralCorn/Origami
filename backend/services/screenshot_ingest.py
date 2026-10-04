"""Screenshot source adapter: OCR plus VLM output to an Item and SegmentDrafts.

ARCHITECTURE_V2 section 2 keeps two kinds of text apart, because one came
out of the artifact and the other is a model's guess about it. Before
on-device OCR both came from the same VLM call; now they come from
different engines, which makes the separation literal rather than
bookkeeping. The OCR segment records which engine read it, so a
transcription the VLM produced on a machine with no OCR engine is
distinguishable from one the Vision framework read.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from config import OCR_MIN_LINE_CHARS, OLLAMA_VLM_MODEL
from services.chroma import hash_bytes
from services.indexing import SegmentDraft, index_item
from services.ingest import text_splitter
from services.ocr import VLM_ENGINE, OcrResult
from services.rag import invalidate_line_frequency
from services.schema import Item, data_relative, provenance_for_screenshot
from services.screen_text import content_lines, derive_title
from services.text_utils import as_text

logger = logging.getLogger(__name__)

CAPTION_ORDINAL = 0
FIRST_OCR_ORDINAL = 1

DEFAULT_TITLE = "Untitled Screenshot"


def screenshot_title(vision_result: dict | None, ocr: OcrResult | None) -> str:
    """The VLM's title when it wrote one, else the first content line of the OCR.

    The OCR fallback is what lets a screenshot land with a real name in the
    two seconds before the caption pass, or forever on a machine with no
    VLM.
    """
    title = as_text((vision_result or {}).get("title"))
    if title and title != DEFAULT_TITLE:
        return title
    if ocr is not None:
        derived = derive_title(ocr.line_texts)
        if derived:
            return derived
    return DEFAULT_TITLE


def screenshot_item(path: Path, title: str) -> Item:
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
        title=title or DEFAULT_TITLE,
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


def ocr_from_vision(vision_result: dict) -> OcrResult | None:
    """The VLM's transcription wrapped as an OcrResult, engine "vlm".

    The fallback for a machine with no OCR engine. Confidence is zero and
    there are no boxes, and the record says so.
    """
    text = extracted_text(vision_result)
    return OcrResult.from_text(text, engine=VLM_ENGINE) if text else None


def screenshot_drafts(
    vision_result: dict | None,
    ocr: OcrResult | None,
    *,
    title: str = "",
) -> list[SegmentDraft]:
    """One Item, two kinds of epistemic object, kept apart per section 2.

    The caption takes ordinal 0 when the VLM wrote one. The OCR text
    follows from ordinal 1: the status bar and control labels are dropped
    (services.screen_text), and the rest is split by the shared
    text_splitter, because the embedder's window is 512 tokens and an
    unsplit page of screenshotted text embedded only its first ~3,200
    characters. Absence never renumbers: a caption pass that arrives after
    the OCR pass upserts "{item}-0" and leaves the OCR ids alone.

    An Item with no segments would never enter Chroma and would stay
    pending forever, so a screenshot with neither caption nor text gets a
    placeholder caption carrying its title.
    """
    drafts: list[SegmentDraft] = []

    caption = as_text((vision_result or {}).get("description"))
    if caption:
        drafts.append(SegmentDraft(
            ordinal=CAPTION_ORDINAL,
            modality="caption",
            content=caption,
            content_source="generated",
            span={"generated_by": OLLAMA_VLM_MODEL},
        ))

    if ocr is not None:
        text = "\n".join(content_lines(ocr.line_texts, min_chars=OCR_MIN_LINE_CHARS))
        for offset, chunk in enumerate(text_splitter.split_text(text) if text else []):
            drafts.append(SegmentDraft(
                ordinal=FIRST_OCR_ORDINAL + offset,
                modality="ocr",
                content=chunk,
                content_source="extracted",
                span={"ocr_engine": ocr.engine, "ocr_confidence": ocr.mean_confidence},
            ))

    if not drafts:
        drafts.append(SegmentDraft(
            ordinal=CAPTION_ORDINAL,
            modality="caption",
            content=title or DEFAULT_TITLE,
            content_source="generated",
        ))
    return drafts


async def index_screenshot(
    path: Path,
    *,
    vision_result: dict | None,
    ocr: OcrResult | None,
    collection_id: str,
    title: str = "",
) -> int:
    """Write one analysed screenshot to the knowledge base.

    Called twice per screenshot on the normal path: once with the OCR the
    moment it exists, once more when the caption arrives. index_item
    upserts by segment id, so the second call replaces the placeholder or
    adds the caption without touching the OCR segments.
    """
    title = title or screenshot_title(vision_result, ocr)
    item = screenshot_item(path, title)
    source_app = as_text((vision_result or {}).get("source_app"))
    extra = {
        "collection": collection_id,
        "source_app": source_app if source_app and source_app != "unknown" else "",
        "ocr_engine": ocr.engine if ocr else "",
    }
    written = await index_item(item, screenshot_drafts(vision_result, ocr, title=title), extra=extra)
    invalidate_line_frequency()
    return written
