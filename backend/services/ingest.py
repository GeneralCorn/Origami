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
from datetime import datetime, timezone
from pathlib import Path

import pymupdf
from langchain_ollama import ChatOllama
from langchain_text_splitters import RecursiveCharacterTextSplitter

from prompts import CONTEXTUALIZER_PROMPT
from services.chroma import get_collection
from config import OLLAMA_MODEL, CHUNK_SIZE, CHUNK_OVERLAP
from services.text_utils import strip_think_tags

logger = logging.getLogger(__name__)

CONTEXT_MODEL = OLLAMA_MODEL

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


async def contextualize_chunk(
    llm: ChatOllama,
    whole_document: str,
    chunk_content: str,
) -> str:
    """
    Generate a contextual prefix for a chunk using the local LLM.

    The LLM reads the whole document + the specific chunk and produces
    a short blurb situating the chunk. This is prepended to the chunk
    before embedding.
    """
    # Truncate the whole document if it's extremely long to fit in context
    # 7B models typically have 4-8k context; reserve room for the chunk + response
    max_doc_chars = 12000
    truncated_doc = whole_document[:max_doc_chars]
    if len(whole_document) > max_doc_chars:
        truncated_doc += "\n\n[... document truncated for context window ...]"

    prompt = CONTEXTUALIZER_PROMPT.format(
        whole_document=truncated_doc,
        chunk_content=chunk_content,
    )

    response = await llm.ainvoke(prompt)

    context = response.content
    if isinstance(context, str):
        context = strip_think_tags(context)

    return context


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
    file_id: str,
    filename: str,
    tags: list[str] | None = None,
    content_hash: str | None = None,
    title: str = "",
    publish_date: str | None = None,
) -> int:
    """
    Full contextual retrieval ingestion pipeline for a single PDF.

    1. Extract text from PDF (with page offsets)
    2. Split into chunks
    3. For each chunk, generate contextual prefix via local LLM
    4. Prepend context to chunk
    5. Store contextualized chunks in ChromaDB with metadata

    Returns the number of chunks ingested.
    """
    logger.info(f"Ingesting PDF: {filename} (id={file_id})")

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
    llm = ChatOllama(model=CONTEXT_MODEL, temperature=0, num_predict=100)
    chunk_tags = tags or []
    ingested = 0

    # Semaphore limits concurrent Ollama requests to avoid overwhelming the server
    sem = asyncio.Semaphore(4)

    async def _contextualize_and_insert(i: int, chunk: str) -> None:
        nonlocal ingested
        async with sem:
            try:
                context = await contextualize_chunk(llm, full_text, chunk)
                contextualized = f"{context}\n\n{chunk}"
            except Exception as e:
                logger.warning(f"Contextualization failed for chunk {i+1}: {e}")
                contextualized = chunk

            # Compute page range for this chunk
            c_start, c_end = chunk_positions[i]
            p_start, p_end = _page_range(c_start, c_end, page_offsets)

            # Insert immediately so frontend progress bar updates in real time
            collection.add(
                ids=[f"{file_id}-{i}"],
                documents=[contextualized],
                metadatas=[{
                    "file_id": file_id,
                    "filename": filename,
                    "title": title or filename,
                    "chunk_index": i,
                    "original_chunk": chunk,
                    "tags": chunk_tags,
                    "content_hash": content_hash or "",
                    "publish_date": publish_date or "",
                    "page_start": p_start,
                    "page_end": p_end,
                }],
            )
            ingested += 1
            logger.info(f"Ingested chunk {ingested}/{len(chunks)} for {filename}")

    await asyncio.gather(*[
        _contextualize_and_insert(i, chunk) for i, chunk in enumerate(chunks)
    ])

    logger.info(f"Finished ingesting {ingested} contextualized chunks for {filename}")
    return ingested
