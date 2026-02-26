"""API routes for managing documents in ChromaDB."""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.chroma import get_collection, get_document_meta, set_tags, set_title, delete_chunks

_BACKEND_DIR = Path(__file__).resolve().parent.parent
PDFS_DIR = _BACKEND_DIR / "pdfs"

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
                "chunk_count": 0,
                "tags": meta.get("tags", []),
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
    """Delete everything for a document: ChromaDB chunks and PDF file."""
    # 1. Look up filename before deleting chunks
    meta = get_document_meta(file_id)

    # 2. Delete ChromaDB chunks
    deleted_chunks = delete_chunks(file_id)
    if deleted_chunks:
        logger.info(f"Deleted {deleted_chunks} chunks for file_id={file_id}")

    # 3. Delete PDF file from disk
    if meta:
        pdf_path = PDFS_DIR / meta["filename"]
        if pdf_path.exists():
            pdf_path.unlink()
            logger.info(f"Deleted PDF file: {meta['filename']}")

    return {"deleted_chunks": deleted_chunks}
