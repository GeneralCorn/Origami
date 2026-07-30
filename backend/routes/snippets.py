"""Snippet capture: the simplest source, per ARCHITECTURE_V2 section 7 step 5.

No third party and no permissions, which is the point: it is the first
source written natively against the schema rather than migrated onto it,
and it exercises the whole ingest path end to end.
"""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from config import SNIPPETS_DIR
from services.chroma import find_by_hash, hash_bytes, item_completion
from services.indexing import SegmentDraft, index_item
from services.ingest import text_splitter
from services.schema import Item, data_relative, provenance_for_snippet

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_TITLE_CHARS = 80

# A capture is a passage, not a corpus. The bound is on the route rather
# than on the ingest because everything downstream is per-character: the
# title is copied onto every segment, the segment count sets how long the
# store is being written to, and neither had any ceiling at all.
MAX_TEXT_CHARS = 500_000
MAX_TAGS = 32
MAX_TAG_CHARS = 64


class CreateSnippetRequest(BaseModel):
    text: str
    title: str = ""
    tags: list[str] = []


def _snippet_path(snippet_id: str) -> Path:
    path = (SNIPPETS_DIR / f"{snippet_id}.md").resolve()
    if path.parent != SNIPPETS_DIR.resolve():
        raise HTTPException(status_code=400, detail="Invalid snippet id")
    return path


# -- Importable helpers -----------------------------------------------------


def derive_title(text: str) -> str:
    """First non-empty line, truncated. Mirrors notes._extract_title's role."""
    for line in text.split("\n"):
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:MAX_TITLE_CHARS]
    return "Untitled Snippet"


def snippet_drafts(text: str) -> list[SegmentDraft]:
    """content_source is "extracted": the content is the captured bytes."""
    return [
        SegmentDraft(ordinal=i, modality="text", content=chunk, content_source="extracted")
        for i, chunk in enumerate(text_splitter.split_text(text))
    ]


def snippet_item(snippet_id: str, text: str, title: str) -> Item:
    """created_at is empty: the text came into existence elsewhere, at a
    time Origami does not know. Same rule as the screenshot adapter."""
    return Item(
        id=snippet_id,
        source_type="snippet",
        source_id=hash_bytes(text.encode("utf-8")),
        title=title or derive_title(text),
        created_at="",
        ingested_at=datetime.now(timezone.utc).isoformat(),
        provenance=provenance_for_snippet(),
        raw_ref=data_relative(SNIPPETS_DIR / f"{snippet_id}.md"),
    )


async def _process_snippet(snippet_id: str, text: str, title: str, tags: list[str]) -> None:
    try:
        item = snippet_item(snippet_id, text, title)
        count = await index_item(item, snippet_drafts(text), tags=tags, whole_text=text)
        logger.info("Finished ingesting snippet %s: %d segments", snippet_id, count)
    except Exception as exc:
        logger.exception("Ingestion failed for snippet %s: %s", snippet_id, exc)


def _reject_unencodable(field: str, value: str) -> None:
    """Fail a string that cannot survive a round trip to UTF-8.

    A lone surrogate is legal JSON per RFC 8259 and parses into a str
    Python is happy to hold, and it only raises when something encodes
    it. Left to reach the response, that is a 500 raised while rendering,
    which is after the handler has returned and therefore after the raw
    .md file has been written and after nothing can unlink it. Checking
    here turns an orphaned file plus an unexplained 500 into a 400.
    """
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise HTTPException(
            status_code=400, detail=f"{field} contains text that is not valid UTF-8"
        ) from exc


@router.post("/snippets")
async def create_snippet(req: CreateSnippetRequest, background_tasks: BackgroundTasks):
    """Capture pasted text as an Item and start ingesting it."""
    _reject_unencodable("text", req.text)
    _reject_unencodable("title", req.title)
    for tag in req.tags:
        _reject_unencodable("tags", tag)

    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Snippet is empty")
    if len(text) > MAX_TEXT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Snippet is {len(text)} characters; the limit is {MAX_TEXT_CHARS}",
        )

    title = req.title.strip()[:MAX_TITLE_CHARS] or derive_title(text)
    tags = [tag.strip()[:MAX_TAG_CHARS] for tag in req.tags[:MAX_TAGS] if tag.strip()]

    content_hash = hash_bytes(text.encode("utf-8"))
    existing = find_by_hash(content_hash)
    snippet_id = str(uuid.uuid4())
    if existing:
        stored, expected = item_completion(existing["file_id"])
        # An ingest is not transactional, so a quit mid-capture leaves a
        # truncated Item whose hash still matches. Reporting that as a
        # duplicate stranded the missing segments permanently, with no
        # path to a retry; re-running the ingest under the same id
        # completes it instead, and upsert makes the segments already
        # present a no-op rather than a second copy.
        if expected and stored < expected:
            snippet_id = existing["file_id"]
            logger.warning(
                "Snippet %s holds %d of %d segments; resuming the ingest",
                snippet_id, stored, expected,
            )
        else:
            return {"id": existing["file_id"], "duplicate": True, "status": "duplicate"}

    # The raw bytes are what the user captured, verbatim: raw_ref is a
    # handle to the original, so a title header written into the file
    # would make the stored bytes differ from the captured ones.
    path = _snippet_path(snippet_id)
    path.write_text(text, encoding="utf-8")
    try:
        chunks = text_splitter.split_text(text)
    except Exception:
        # Nothing downstream will ever look at this file again, and no API
        # path lists the snippets directory, so leaving it behind makes it
        # unreachable and uncollectable.
        path.unlink(missing_ok=True)
        raise

    background_tasks.add_task(_process_snippet, snippet_id, text, title, tags)
    return {
        "id": snippet_id,
        "title": title,
        "total_chunks": len(chunks),
        "tags": tags,
        "status": "processing",
    }


@router.get("/snippets/{snippet_id}")
async def get_snippet(snippet_id: str):
    """Read a captured snippet's original bytes."""
    path = _snippet_path(snippet_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Snippet not found")
    return {"id": snippet_id, "content": path.read_text(encoding="utf-8")}
