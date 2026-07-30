"""
Contextual Retrieval ingestion pipeline.

Implements Anthropic's "Contextual Retrieval" method:
for every chunk, a local LLM generates a short context blurb
situating the chunk within the whole document, then that context
is prepended before embedding. This dramatically improves retrieval
accuracy for RAG on chunked documents.
"""

import asyncio
import bisect
import logging
import re
from datetime import datetime
from pathlib import Path

import pymupdf
from langchain_text_splitters import RecursiveCharacterTextSplitter

from prompts import CONTEXTUALIZER_PROMPT
from services.chroma import get_collection
from config import CHUNK_SIZE, CHUNK_OVERLAP, CONTEXT_DOC_CHARS
from services.embeddings import current_embedding_model_id
from services.llm import Budget, ModelResult, Prompt, Purpose, complete
from services.schema import Item, Segment, segment_id, segment_metadata

logger = logging.getLogger(__name__)

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
    length_function=len,
)


def extract_text_from_pdf(pdf_path: Path) -> tuple[str, list[int]]:
    """Extract all text from a PDF using PyMuPDF.

    Returns:
        (full_text, page_offsets) where page_offsets[i] is the character
        offset in full_text where page i begins.
    """
    doc = pymupdf.open(str(pdf_path))
    pages = []
    page_offsets: list[int] = []
    offset = 0
    for page in doc:
        page_offsets.append(offset)
        text = page.get_text()
        pages.append(text)
        # +2 for the "\n\n" separator between pages
        offset += len(text) + 2
    doc.close()
    return "\n\n".join(pages), page_offsets


def _parse_pdf_date(date_str: str) -> str | None:
    """Parse a PDF metadata date string (D:YYYYMMDDHHmmSS...) to ISO format."""
    if not date_str:
        return None
    # Strip the D: prefix
    s = date_str
    if s.startswith("D:"):
        s = s[2:]
    # Remove timezone offset suffix (e.g. +05'30', -08'00', Z)
    s = re.sub(r"[Z+-].*$", "", s)
    # Try progressively shorter formats
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y%m%d", "%Y%m", "%Y"):
        try:
            dt = datetime.strptime(s[:len(fmt.replace("%", ""))], fmt)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, IndexError):
            continue
    return None


def extract_publish_date(pdf_path: Path) -> str | None:
    """Extract a publish/creation date from PDF metadata.

    Checks creationDate first, then modDate. Returns an ISO date string
    (YYYY-MM-DD) or None if not available.
    """
    try:
        doc = pymupdf.open(str(pdf_path))
        meta = doc.metadata or {}
        doc.close()
        # Try creation date first, then modification date
        for key in ("creationDate", "modDate"):
            raw = meta.get(key, "")
            if raw:
                parsed = _parse_pdf_date(raw)
                if parsed:
                    return parsed
    except Exception:
        pass
    return None


def _page_range(chunk_start: int, chunk_end: int, page_offsets: list[int]) -> tuple[int, int]:
    """Determine which pages a chunk spans (1-indexed).

    Args:
        chunk_start: character offset of chunk start in full_text
        chunk_end: character offset of chunk end in full_text
        page_offsets: list of character offsets where each page begins
    """
    # bisect_right gives index of first page AFTER chunk_start
    page_start = bisect.bisect_right(page_offsets, chunk_start) - 1
    page_end = bisect.bisect_right(page_offsets, chunk_end - 1) - 1
    # Clamp to valid range and convert to 1-indexed
    page_start = max(0, page_start) + 1
    page_end = max(0, page_end) + 1
    return page_start, page_end


def document_prefix(whole_document: str) -> str:
    """The document text prepended to every chunk request for this document.

    Byte-identical across a document's chunks, which is what makes it
    cacheable. Truncated because it is sent once per chunk.
    """
    truncated = whole_document[:CONTEXT_DOC_CHARS]
    if len(whole_document) > CONTEXT_DOC_CHARS:
        truncated += "\n\n[... document truncated for context window ...]"
    return truncated


async def contextualize_chunk(
    whole_document: str,
    chunk_content: str,
    budget: Budget,
) -> ModelResult:
    """
    Generate a contextual prefix for a chunk.

    The model reads the whole document + the specific chunk and produces
    a short blurb situating the chunk. This is prepended to the chunk
    before embedding.
    """
    # The document prefix is byte-identical across every chunk of this
    # document and is roughly 88% of each request, so it is sent as a
    # cacheable block. The prompt text itself is unchanged, only the message
    # structure, so the bytes the model sees are the same and there is no
    # quality risk. CONTEXTUALIZER_PROMPT is already document-first, which
    # is what makes the prefix reusable.
    prompt = Prompt.render(
        CONTEXTUALIZER_PROMPT,
        {
            "whole_document": document_prefix(whole_document),
            "chunk_content": chunk_content,
        },
        cache_after="whole_document",
    )
    return await complete(Purpose.CONTEXTUALIZE, prompt, budget)


def _pick_subtitle(title: str) -> str:
    """If the title has a colon/dash separator, return the part after it."""
    for sep in [":", " - ", " — ", " – "]:
        if sep in title:
            after = title.split(sep, 1)[1].strip()
            if after:
                return after
    return title


def generate_title_from_pdf(pdf_path: Path) -> str:
    """Extract a suggested title from a PDF — fast, only reads metadata + page 1."""
    try:
        doc = pymupdf.open(str(pdf_path))

        # Try metadata title first (instant — no page rendering)
        meta_title = (doc.metadata or {}).get("title", "").strip()
        if meta_title and len(meta_title) > 3:
            doc.close()
            return _pick_subtitle(meta_title)

        # Heuristic: first non-empty short line from page 1
        if doc.page_count > 0:
            first_page = doc[0].get_text()
            doc.close()
            for line in first_page.split("\n")[:20]:
                candidate = line.strip()
                if not candidate or len(candidate) < 4 or candidate.isdigit():
                    continue
                if len(candidate) <= 120:
                    return _pick_subtitle(candidate)
        else:
            doc.close()
    except Exception:
        pass

    return pdf_path.stem


async def ingest_pdf(
    pdf_path: Path,
    item: Item,
    tags: list[str] | None = None,
) -> int:
    """
    Full contextual retrieval ingestion pipeline for a single PDF.

    1. Extract text from PDF (with page offsets)
    2. Split into chunks
    3. For each chunk, generate contextual prefix via local LLM
    4. Prepend context to chunk
    5. Store contextualized chunks in ChromaDB with metadata

    Takes an Item rather than loose PDF-shaped scalars: the adapter that
    knows where the bytes came from is the only thing that can state their
    provenance, and Item cannot be constructed without it.

    Returns the number of chunks ingested.
    """
    filename = Path(item.raw_ref).name
    logger.info(f"Ingesting PDF: {filename} (id={item.id})")

    # Step 1: Extract text with page boundaries
    full_text, page_offsets = extract_text_from_pdf(pdf_path)
    if not full_text.strip():
        logger.warning(f"No text extracted from {filename}")
        return 0

    # Step 2: Split into chunks and track their positions in full_text
    chunks = text_splitter.split_text(full_text)
    logger.info(f"Split into {len(chunks)} chunks")

    # Build chunk start offsets by finding each chunk in the full text
    chunk_positions: list[tuple[int, int]] = []
    search_start = 0
    for chunk in chunks:
        pos = full_text.find(chunk, search_start)
        if pos == -1:
            # Fallback: if exact match fails (due to overlap trimming), use last known position
            pos = search_start
        chunk_positions.append((pos, pos + len(chunk)))
        # Advance past the start of this chunk for next search
        search_start = pos + 1

    # Step 3-5: Contextualize chunks and insert into ChromaDB incrementally
    collection = get_collection()
    # Ingest is background work: it may process the document it was handed
    # and may not reach into a live session's state. Budget.background is
    # what makes that structural rather than a convention.
    budget = Budget.background("ingest", max_calls=len(chunks))
    chunk_tags = tags or []
    embedding_model = current_embedding_model_id()
    ingested = 0
    failed = 0
    doc_input_tokens = 0
    doc_output_tokens = 0
    doc_cache_read_tokens = 0
    doc_cost_usd = 0.0

    # Semaphore limits concurrent API requests
    sem = asyncio.Semaphore(4)

    async def _contextualize_and_insert(i: int, chunk: str) -> None:
        nonlocal ingested, failed
        nonlocal doc_input_tokens, doc_output_tokens, doc_cache_read_tokens, doc_cost_usd
        async with sem:
            try:
                result = await contextualize_chunk(full_text, chunk, budget)
                contextualized = f"{result.text}\n\n{chunk}"
                context_status = "ok"
                doc_input_tokens += result.input_tokens
                doc_output_tokens += result.output_tokens
                doc_cache_read_tokens += result.cache_read_tokens
                doc_cost_usd += result.cost_usd
            except Exception as e:
                # A failed contextualization is billed and buys nothing, so
                # it is counted rather than only logged per chunk.
                logger.warning(f"Contextualization failed for chunk {i+1}: {e}")
                contextualized = chunk
                context_status = "failed"
                failed += 1

            # Compute page range for this chunk
            c_start, c_end = chunk_positions[i]
            p_start, p_end = _page_range(c_start, c_end, page_offsets)

            # content_source describes the citable text, which is the
            # chunk verbatim: original_chunk below, and what services.rag
            # returns as `text`. Contextualisation prepends a blurb to the
            # embedded string only, and context_status is what records
            # that. See the Segment docstring for why the two cannot share
            # one field.
            segment = Segment(
                ordinal=i,
                modality="text",
                content=contextualized,
                content_source="extracted",
                embedding_model=embedding_model,
                context_status=context_status,
                span={"page_start": p_start, "page_end": p_end},
            )

            # Insert immediately so frontend progress bar updates in real time
            collection.add(
                ids=[segment_id(item.id, i)],
                documents=[segment.content],
                metadatas=[segment_metadata(item, segment, extra={
                    "filename": filename,
                    "original_chunk": chunk,
                    "tags": chunk_tags,
                    "content_hash": item.source_id,
                    "publish_date": item.created_at,
                })],
            )
            ingested += 1
            logger.info(f"Ingested chunk {ingested}/{len(chunks)} for {filename}")

    await asyncio.gather(*[
        _contextualize_and_insert(i, chunk) for i, chunk in enumerate(chunks)
    ])

    logger.info(f"Finished ingesting {ingested} contextualized chunks for {filename}")
    logger.info(
        "[COST] ingest %s: %d chunks (%d failed), %d in (%d cache read) / %d out, $%.4f",
        filename, ingested, failed, doc_input_tokens, doc_cache_read_tokens,
        doc_output_tokens, doc_cost_usd,
    )
    return ingested
