"""
Contextual Retrieval ingestion pipeline.

Implements Anthropic's "Contextual Retrieval" method:
for every chunk, a local LLM generates a short context blurb
situating the chunk within the whole document, then that context
is prepended before embedding. This dramatically improves retrieval
accuracy for RAG on chunked documents.
"""

import asyncio
import logging
from pathlib import Path

import pymupdf
from langchain_ollama import ChatOllama
from langchain_text_splitters import RecursiveCharacterTextSplitter

from prompts import CONTEXTUALIZER_PROMPT
from services.chroma import get_collection
from services.text_utils import strip_think_tags

logger = logging.getLogger(__name__)

CONTEXT_MODEL = "deepseek-r1:7b"

# Splitter tuned for a 16GB Mac running 7B models
# ~800 tokens per chunk with 200 token overlap keeps context dense
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1200,
    chunk_overlap=300,
    separators=["\n\n", "\n", ". ", " ", ""],
    length_function=len,
)


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract all text from a PDF using PyMuPDF."""
    doc = pymupdf.open(str(pdf_path))
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n\n".join(pages)


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
) -> int:
    """
    Full contextual retrieval ingestion pipeline for a single PDF.

    1. Extract text from PDF
    2. Split into chunks
    3. For each chunk, generate contextual prefix via local LLM
    4. Prepend context to chunk
    5. Store contextualized chunks in ChromaDB

    Returns the number of chunks ingested.
    """
    logger.info(f"Ingesting PDF: {filename} (id={file_id})")

    # Step 1: Extract text
    full_text = extract_text_from_pdf(pdf_path)
    if not full_text.strip():
        logger.warning(f"No text extracted from {filename}")
        return 0

    # Step 2: Split into chunks
    chunks = text_splitter.split_text(full_text)
    logger.info(f"Split into {len(chunks)} chunks")

    # Step 3-5: Contextualize chunks and insert into ChromaDB incrementally
    collection = get_collection()
    llm = ChatOllama(model=CONTEXT_MODEL, temperature=0)
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

            # Insert immediately so frontend progress bar updates in real time
            collection.add(
                ids=[f"{file_id}_chunk_{i}"],
                documents=[contextualized],
                metadatas=[{
                    "file_id": file_id,
                    "filename": filename,
                    "chunk_index": i,
                    "original_chunk": chunk,
                    "tags": chunk_tags,
                    "content_hash": content_hash or "",
                }],
            )
            ingested += 1
            logger.info(f"Ingested chunk {ingested}/{len(chunks)} for {filename}")

    await asyncio.gather(*[
        _contextualize_and_insert(i, chunk) for i, chunk in enumerate(chunks)
    ])

    logger.info(f"Finished ingesting {ingested} contextualized chunks for {filename}")
    return ingested
