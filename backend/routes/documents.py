"""API routes for managing documents in ChromaDB."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import DATA_DIR, PDFS_DIR
from services.chroma import get_collection, get_document_meta, set_tags, set_title, delete_chunks

router = APIRouter()
logger = logging.getLogger(__name__)


class TagsRequest(BaseModel):
    tags: list[str]


class TitleRequest(BaseModel):
    title: str


@router.get("/documents")
async def list_documents():
    """List unique documents stored in ChromaDB, grouped by file_id."""
    collection = get_collection()
    if collection.count() == 0:
        return []

    result = collection.get(include=["metadatas"])

    # Group chunks by file_id
    docs: dict[str, dict] = {}
    for meta in result["metadatas"] or []:
        fid = meta.get("file_id", "")
        if fid not in docs:
            docs[fid] = {
                "file_id": fid,
                "filename": meta.get("filename", "unknown"),
                "title": meta.get("title", meta.get("filename", "unknown")),
                # The list is no longer PDFs only, and the renderer has to
                # tell sources apart to know which ones the reader opens.
                "source_type": meta.get("source_type", "pdf"),
                "chunk_count": 0,
                "tags": meta.get("tags", []),
                "publish_date": meta.get("publish_date") or None,
            }
        docs[fid]["chunk_count"] += 1

    return list(docs.values())


@router.get("/documents/{file_id}/chunks")
async def get_document_chunks(file_id: str):
    """Return all chunks for a document, sorted by chunk_index."""
    collection = get_collection()
    result = collection.get(
        where={"file_id": file_id},
        include=["metadatas", "documents"],
    )
    if not result["ids"]:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = []
    for i, chunk_id in enumerate(result["ids"]):
        meta = result["metadatas"][i]
        chunks.append({
            "chunk_id": chunk_id,
            "chunk_index": meta.get("chunk_index", i),
            "text": result["documents"][i] if result["documents"] else "",
            "original_text": meta.get("original_chunk", ""),
            "page_start": meta.get("page_start"),
            "page_end": meta.get("page_end"),
        })
    chunks.sort(key=lambda c: c["chunk_index"])
    return chunks


@router.patch("/documents/{file_id}/tags")
async def update_tags(file_id: str, req: TagsRequest):
    """Set tags for a document (updates all its chunks)."""
    if not set_tags(file_id, req.tags):
        raise HTTPException(status_code=404, detail="Document not found")
    return {"file_id": file_id, "tags": req.tags}


@router.patch("/documents/{file_id}/title")
async def update_title(file_id: str, req: TitleRequest):
    """Set title for a document (updates all its chunks)."""
    if not set_title(file_id, req.title):
        raise HTTPException(status_code=404, detail="Document not found")
    return {"file_id": file_id, "title": req.title}


@router.delete("/documents/{file_id}")
async def delete_document(file_id: str):
    """Delete everything for a document: its segments and its raw bytes."""
    # 1. Look up the raw reference before deleting the segments
    meta = get_document_meta(file_id)

    # 2. Delete ChromaDB segments
    deleted_chunks = delete_chunks(file_id)
    if deleted_chunks:
        logger.info(f"Deleted {deleted_chunks} chunks for file_id={file_id}")

    # 3. Delete the raw file. Resolved through raw_ref, because the store
    # now holds screenshots and snippets whose bytes are not under PDFS_DIR;
    # the filename fallback only serves v1 records, written before raw_ref
    # existed. raw_ref comes from stored metadata, so containment in
    # DATA_DIR is checked before anything is unlinked.
    if meta:
        raw_ref = meta.get("raw_ref", "")
        raw_path = (DATA_DIR / raw_ref).resolve() if raw_ref else PDFS_DIR / meta.get("filename", "")
        if raw_path.is_relative_to(DATA_DIR.resolve()) and raw_path.is_file():
            raw_path.unlink()
            logger.info(f"Deleted raw file: {raw_path.name}")

    return {"deleted_chunks": deleted_chunks}
