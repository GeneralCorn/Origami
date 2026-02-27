import shutil
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException
from pydantic import BaseModel
from starlette.responses import FileResponse

from services.ingest import ingest_pdf, generate_title_from_pdf, extract_text_from_pdf, extract_publish_date, text_splitter
from services.chroma import hash_bytes, find_by_hash, list_all_tags, delete_chunks, get_collection
from services.text_utils import sanitize_filename

router = APIRouter()
logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent

UPLOAD_DIR = _BACKEND_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

PDFS_DIR = _BACKEND_DIR / "pdfs"
PDFS_DIR.mkdir(exist_ok=True)


class ConfirmRequest(BaseModel):
    id: str
    name: str
    tags: list[str] = []


async def _process_pdf(
    file_id: str, file_path: Path, filename: str,
    tags: list[str], content_hash: str, title: str = "",
) -> None:
    """Background task: run the contextual retrieval ingestion pipeline."""
    try:
        publish_date = extract_publish_date(file_path)
        count = await ingest_pdf(
            file_path, file_id, filename,
            tags=tags, content_hash=content_hash, title=title,
            publish_date=publish_date,
        )
        logger.info(f"Finished ingesting {filename}: {count} chunks (publish_date={publish_date})")
    except Exception as e:
        logger.error(f"Ingestion failed for {filename}: {e}")


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload a PDF and get a suggested name from the LLM.

    Does NOT start ingestion -- call /api/upload/confirm to finalize.
    """
    file_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{file_id}.pdf"

    content = await file.read()
    file_path.write_bytes(content)

    content_hash = hash_bytes(content)

    # Check for duplicate in ChromaDB
    existing = find_by_hash(content_hash)
    if existing:
        file_path.unlink()
        return {
            "id": existing["file_id"],
            "filename": existing["filename"],
            "duplicate": True,
            "status": "duplicate",
        }

    suggested_title = generate_title_from_pdf(file_path)
    safe_name = sanitize_filename(suggested_title)

    return {
        "id": file_id,
        "filename": file.filename,
        "suggested_name": safe_name,
        "suggested_title": suggested_title,
        "size": len(content),
        "content_hash": content_hash,
        "status": "pending_confirmation",
    }


@router.post("/upload/confirm")
async def confirm_upload(req: ConfirmRequest, background_tasks: BackgroundTasks):
    """Confirm the upload with a chosen name, copy to pdfs/, and start ingestion."""
    temp_path = UPLOAD_DIR / f"{req.id}.pdf"
    if not temp_path.exists():
        raise HTTPException(status_code=404, detail="Upload not found")

    safe_name = sanitize_filename(req.name)
    if not safe_name:
        safe_name = "untitled"

    # Handle name collisions
    final_path = PDFS_DIR / f"{safe_name}.pdf"
    counter = 1
    while final_path.exists():
        final_path = PDFS_DIR / f"{safe_name}-{counter}.pdf"
        counter += 1

    final_name = final_path.stem

    shutil.copy2(str(temp_path), str(final_path))
    temp_path.unlink()

    # Pre-compute chunk count so frontend can track real progress
    full_text, _page_offsets = extract_text_from_pdf(final_path)
    chunks = text_splitter.split_text(full_text) if full_text.strip() else []

    file_id = req.id
    content_hash = hash_bytes(final_path.read_bytes())

    # The user-facing title is the raw name before sanitization
    title = req.name.strip() or "Untitled"

    # Tags + hash are passed to ingest and stored on every chunk in ChromaDB
    background_tasks.add_task(
        _process_pdf, file_id, final_path, f"{final_name}.pdf",
        tags=req.tags, content_hash=content_hash, title=title,
    )

    return {
        "id": file_id,
        "filename": f"{final_name}.pdf",
        "size": final_path.stat().st_size,
        "total_chunks": len(chunks),
        "tags": req.tags,
        "status": "processing",
    }


@router.get("/tags")
async def get_tags():
    """Return all unique tags across all documents."""
    return list_all_tags()


@router.get("/pdfs")
async def list_pdfs():
    """List all persisted PDFs from the pdfs/ directory."""
    # Build filename -> metadata lookup from ChromaDB
    col = get_collection()
    all_meta = col.get(include=["metadatas"])["metadatas"] or [] if col.count() > 0 else []
    filename_map: dict[str, dict] = {}
    for meta in all_meta:
        fn = meta.get("filename", "")
        if fn and fn not in filename_map:
            filename_map[fn] = {
                "file_id": meta.get("file_id", ""),
                "title": meta.get("title", fn),
                "tags": meta.get("tags", []),
            }

    pdfs = []
    for path in PDFS_DIR.glob("*.pdf"):
        stat = path.stat()
        entry = {
            "name": path.stem,
            "filename": path.name,
            "size": stat.st_size,
            "uploaded_at": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
        }
        chroma_info = filename_map.get(path.name)
        if chroma_info:
            entry["file_id"] = chroma_info["file_id"]
            entry["title"] = chroma_info["title"]
            entry["tags"] = chroma_info["tags"]
        pdfs.append(entry)
    pdfs.sort(key=lambda p: p["uploaded_at"], reverse=True)
    return pdfs


@router.get("/pdfs/{name}/file")
async def get_pdf_file(name: str):
    """Serve the raw PDF file for the in-app reader."""
    pdf_path = PDFS_DIR / f"{name}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(pdf_path, media_type="application/pdf")


@router.delete("/pdfs/{name}")
async def delete_pdf(name: str):
    """Delete a PDF and its associated ChromaDB chunks."""
    pdf_filename = f"{name}.pdf"

    # Find file_id from ChromaDB by matching filename
    col = get_collection()
    deleted_chunks = 0
    if col.count() > 0:
        results = col.get(where={"filename": pdf_filename}, include=[])
        chunk_ids = results["ids"]
        if chunk_ids:
            col.delete(ids=chunk_ids)
            deleted_chunks = len(chunk_ids)
            logger.info(f"Deleted {deleted_chunks} chunks for {pdf_filename}")

    # Delete PDF file
    pdf_path = PDFS_DIR / pdf_filename
    if pdf_path.exists():
        pdf_path.unlink()
        logger.info(f"Deleted PDF: {pdf_filename}")

    return {"deleted": True, "deleted_chunks": deleted_chunks}
