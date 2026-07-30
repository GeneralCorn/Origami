"""Screenshot upload, VLM processing, and digest API routes."""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from starlette.responses import FileResponse

from config import SCREENSHOTS_DIR
from services.chroma import delete_chunks, find_by_hash, hash_bytes, indexed_file_ids
from services.screenshot_ingest import index_screenshot
from services.vision import check_ollama_health, analyze_screenshot
from services.digest import (
    append_to_digest,
    get_digest,
    list_digests,
    move_from_review,
)

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _safe_ext(filename: str) -> str:
    """Extract and validate file extension."""
    ext = Path(filename).suffix.lower()
    return ext if ext in ALLOWED_EXTENSIONS else ".png"


# ── Upload ────────────────────────────────────────────────────────


@router.post("/screenshots/upload")
async def upload_screenshots(files: list[UploadFile] = File(...)):
    """Upload one or more screenshots. Saves to disk, no Ollama needed."""
    results = []
    for file in files:
        content = await file.read()
        content_hash = hash_bytes(content)

        # Checked before the write, so a duplicate never lands on disk and
        # never becomes a pending item that re-processes to the same
        # segments. Mirrors the PDF path in routes/upload.py.
        existing = find_by_hash(content_hash)
        if existing:
            results.append({
                "id": existing["file_id"],
                "filename": existing["filename"],
                "original_name": file.filename,
                "size": len(content),
                "content_hash": content_hash,
                "status": "duplicate",
                "duplicate": True,
            })
            logger.info(f"Skipped duplicate screenshot: {existing['filename']}")
            continue

        file_id = str(uuid.uuid4())
        ext = _safe_ext(file.filename or "image.png")
        filename = f"{file_id}{ext}"
        (SCREENSHOTS_DIR / filename).write_bytes(content)

        results.append({
            "id": file_id,
            "filename": filename,
            "original_name": file.filename,
            "size": len(content),
            "content_hash": content_hash,
            "status": "pending",
        })
        logger.info(f"Saved screenshot: {filename} ({len(content)} bytes)")

    return results


# ── Pending ───────────────────────────────────────────────────────


@router.get("/screenshots/pending")
async def list_pending():
    """List screenshots that haven't been processed by the VLM yet.

    "Processed" means present in Chroma, not present in a digest file. The
    digest is a rendered view; deleting one must not silently re-index
    every screenshot it mentioned and duplicate their embeddings.
    """
    processed = indexed_file_ids()
    pending = []
    for path in SCREENSHOTS_DIR.iterdir():
        if path.suffix.lower() in ALLOWED_EXTENSIONS and path.stem not in processed:
            stat = path.stat()
            pending.append({
                "filename": path.name,
                "size": stat.st_size,
                "uploaded_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
            })
    pending.sort(key=lambda p: p["uploaded_at"], reverse=True)
    return pending


# ── Process ───────────────────────────────────────────────────────


@router.post("/screenshots/process")
async def process_screenshots():
    """Process all pending screenshots with the Ollama VLM.

    Returns a summary of processed items and any needing review.
    """
    healthy = await check_ollama_health()
    if not healthy:
        raise HTTPException(
            status_code=503,
            detail="Ollama is not running or the VLM model is not available. Start Ollama first.",
        )

    processed = indexed_file_ids()
    pending_paths = [
        p for p in SCREENSHOTS_DIR.iterdir()
        if p.suffix.lower() in ALLOWED_EXTENSIONS and p.stem not in processed
    ]

    if not pending_paths:
        return {"processed": 0, "needs_review": 0, "results": []}

    results = []
    needs_review = 0

    # Process sequentially to avoid overwhelming Ollama
    for path in pending_paths:
        try:
            vision_result = await analyze_screenshot(path)
            # Indexed before the digest append: Chroma is the store and the
            # digest is a view. If indexing raises, nothing is appended and
            # the file stays pending, so the retry is clean.
            await index_screenshot(path, vision_result)
            append_to_digest(vision_result, path.name)
            if vision_result.get("confidence") == "low":
                needs_review += 1
            results.append({
                "filename": path.name,
                "title": vision_result.get("title", ""),
                "category": vision_result.get("category", "other"),
                "confidence": vision_result.get("confidence", "low"),
            })
            logger.info(f"Processed {path.name}: {vision_result.get('category')} ({vision_result.get('confidence')})")
        except Exception as e:
            logger.error(f"Failed to process {path.name}: {e}")
            results.append({
                "filename": path.name,
                "error": str(e),
            })

    return {
        "processed": len([r for r in results if "error" not in r]),
        "needs_review": needs_review,
        "results": results,
    }


# ── Digests ───────────────────────────────────────────────────────


@router.get("/digests")
async def get_digests():
    """List all available weekly digests."""
    return list_digests()


@router.get("/digests/{week}")
async def get_digest_content(week: str):
    """Get the markdown content of a specific weekly digest."""
    content = get_digest(week)
    if content is None:
        raise HTTPException(status_code=404, detail="Digest not found")
    return {"week": week, "content": content}


class RecategorizeRequest(BaseModel):
    screenshot_name: str
    new_category: str


@router.patch("/digests/{week}/recategorize")
async def recategorize(week: str, req: RecategorizeRequest):
    """Move a screenshot from 'Needs Review' to a specific category."""
    success = move_from_review(week, req.screenshot_name, req.new_category)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Screenshot not found in Needs Review section",
        )
    return {"status": "moved", "new_category": req.new_category}


# ── File serving ──────────────────────────────────────────────────


@router.get("/screenshots/{name}/file")
async def get_screenshot_file(name: str):
    """Serve the raw screenshot image."""
    path = SCREENSHOTS_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    # Infer media type from extension
    ext = path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    return FileResponse(path, media_type=media_types.get(ext, "image/png"))


@router.delete("/screenshots/{name}")
async def delete_screenshot(name: str):
    """Delete a screenshot file and the segments derived from it.

    Without the segment delete, the knowledge base keeps OCR and caption
    records citing an image that is no longer on disk.
    """
    deleted_chunks = delete_chunks(Path(name).stem)
    path = SCREENSHOTS_DIR / name
    if path.exists():
        path.unlink()
        logger.info(f"Deleted screenshot: {name} ({deleted_chunks} segments)")
    return {"deleted": True, "deleted_chunks": deleted_chunks}
