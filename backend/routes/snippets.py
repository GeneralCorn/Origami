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
from services.chroma import find_by_hash, hash_bytes
from services.indexing import SegmentDraft, index_item
from services.ingest import text_splitter
from services.schema import Item, data_relative, provenance_for_snippet

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_TITLE_CHARS = 80


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


@router.post("/snippets")
async def create_snippet(req: CreateSnippetRequest, background_tasks: BackgroundTasks):
    """Capture pasted text as an Item and start ingesting it."""
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Snippet is empty")

    content_hash = hash_bytes(text.encode("utf-8"))
    existing = find_by_hash(content_hash)
    if existing:
        return {"id": existing["file_id"], "duplicate": True, "status": "duplicate"}

    snippet_id = str(uuid.uuid4())
    # The raw bytes are what the user captured, verbatim: raw_ref is a
    # handle to the original, so a title header written into the file
    # would make the stored bytes differ from the captured ones.
    _snippet_path(snippet_id).write_text(text, encoding="utf-8")
    title = req.title.strip() or derive_title(text)
    chunks = text_splitter.split_text(text)

    background_tasks.add_task(_process_snippet, snippet_id, text, title, req.tags)
    return {
        "id": snippet_id,
        "title": title,
        "total_chunks": len(chunks),
        "tags": req.tags,
        "status": "processing",
    }


@router.get("/snippets/{snippet_id}")
async def get_snippet(snippet_id: str):
    """Read a captured snippet's original bytes."""
    path = _snippet_path(snippet_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Snippet not found")
    return {"id": snippet_id, "content": path.read_text(encoding="utf-8")}
