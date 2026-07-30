"""The converge half of ARCHITECTURE_V2 section 4.

A source adapter emits an Item plus SegmentDrafts. Everything after that
is shared: gate contextualisation, stamp the embedding model, flatten to
Chroma metadata, write. ingest.py keeps its own writer because the PDF
path owns chunking, page spans and incremental progress that no other
source has.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

from config import CONTEXTUALIZE_MIN_CHARS
from services.chroma import get_collection
from services.embeddings import current_embedding_model_id
from services.ingest import contextualize_chunk
from services.llm import Budget
from services.schema import (
    ContentSource,
    Item,
    Modality,
    Segment,
    segment_id,
    segment_metadata,
)

logger = logging.getLogger(__name__)

CONTEXTUALIZE_MODALITIES: frozenset[str] = frozenset({"text"})


@dataclass(frozen=True)
class SegmentDraft:
    """A Segment before the pipeline decides its embedding and context status.

    ordinal is caller-supplied and never renumbered. A screenshot's OCR
    segment is always ordinal 0 and its caption always ordinal 1, so a
    re-run that finds no text leaves id "{item}-0" absent rather than
    shifting the caption onto it.
    """

    ordinal: int
    modality: Modality
    content: str
    content_source: ContentSource
    span: dict[str, int | str] = field(default_factory=dict)


def _should_contextualize(draft: SegmentDraft, draft_count: int, whole_text: str) -> bool:
    """ARCHITECTURE_V2 section 4: gate on segment length and modality.

    draft_count is the third clause and the load-bearing one.
    Contextualisation situates a chunk within a larger whole; when the Item
    has one segment, the segment is the whole, and the call asks a model to
    situate a text inside itself. COST_MODEL section 4 also rules out the
    prompt-cache saving here: the cacheable prefix is only amortised across
    a document's many chunks, so a one-segment Item would pay full price.
    """
    return (
        draft_count > 1
        and bool(whole_text)
        and draft.modality in CONTEXTUALIZE_MODALITIES
        and len(draft.content) >= CONTEXTUALIZE_MIN_CHARS
    )


def _drop_stale_segments(collection, item: Item, live_ids: set[str]) -> None:
    """Delete records of this Item that the current draft set no longer covers.

    A re-index whose draft count shrank would otherwise leave the tail of
    the previous run addressable and retrievable, citing an Item whose
    content has since changed.
    """
    existing = set(collection.get(where={"file_id": item.id}, include=[])["ids"])
    stale = sorted(existing - live_ids)
    if stale:
        collection.delete(ids=stale)
        logger.info("Dropped %d stale segments for %s %s", len(stale), item.source_type, item.id)


async def index_item(
    item: Item,
    drafts: list[SegmentDraft],
    *,
    tags: list[str] | None = None,
    whole_text: str = "",
) -> int:
    """Write one Item's segments to Chroma. Returns the number written.

    Idempotent by segment id. `upsert` rather than `add` because
    `collection.add` on an id that already exists is a silent no-op in
    chromadb: it raised nothing, so a re-index reported a segment count it
    had not written, and a corrected VLM result could never replace a bad
    first one.

    Every record carries `segment_total`, the number of segments this Item
    is supposed to have. Writes are not transactional, so an ingest killed
    part-way leaves a truncated Item behind; without the expected count on
    the records themselves, a truncated Item is indistinguishable from a
    complete one and its content_hash makes it look like a duplicate
    forever.
    """
    if not drafts:
        return 0

    collection = get_collection()
    filename = Path(item.raw_ref).name
    embedding_model = current_embedding_model_id()
    item_tags = tags or []
    eligible = sum(1 for d in drafts if _should_contextualize(d, len(drafts), whole_text))
    budget = Budget.background("index", max_calls=eligible)
    written = 0
    sem = asyncio.Semaphore(4)

    async def _write(draft: SegmentDraft) -> None:
        nonlocal written
        async with sem:
            content = draft.content
            context_status = "skipped"
            if _should_contextualize(draft, len(drafts), whole_text):
                try:
                    result = await contextualize_chunk(whole_text, draft.content, budget)
                    content = f"{result.text}\n\n{draft.content}"
                    context_status = "ok"
                except Exception as exc:
                    logger.warning(
                        "Contextualization failed for %s-%d: %s", item.id, draft.ordinal, exc
                    )
                    context_status = "failed"

            segment = Segment(
                ordinal=draft.ordinal,
                modality=draft.modality,
                content=content,
                content_source=draft.content_source,
                embedding_model=embedding_model,
                context_status=context_status,
                span=draft.span,
            )
            # Embedding runs inside collection.upsert and is CPU-bound, so
            # calling it directly from this coroutine stalled every other
            # request on the process for the length of the ingest.
            await asyncio.to_thread(
                collection.upsert,
                ids=[segment_id(item.id, draft.ordinal)],
                documents=[segment.content],
                metadatas=[segment_metadata(item, segment, extra={
                    "filename": filename,
                    "original_chunk": draft.content,
                    "tags": item_tags,
                    "content_hash": item.source_id,
                    "publish_date": item.created_at,
                    "segment_total": len(drafts),
                })],
            )
            written += 1

    await asyncio.gather(*[_write(draft) for draft in drafts])
    live_ids = {segment_id(item.id, draft.ordinal) for draft in drafts}
    await asyncio.to_thread(_drop_stale_segments, collection, item, live_ids)
    logger.info("Indexed %s %s: %d segments", item.source_type, item.id, written)
    return written
