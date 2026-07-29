"""Screenshot upload, VLM processing, and digest API routes."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from starlette.responses import FileResponse

from config import SCREENSHOTS_DIR
from services.chroma import hash_bytes
from services.vision import check_ollama_health, analyze_screenshot
from services.digest import (
    append_to_digest,
    get_digest,
    list_digests,
    move_from_review,
    get_processed_filenames,
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
        file_id = str(uuid.uuid4())
        ext = _safe_ext(file.filename or "image.png")
        filename = f"{file_id}{ext}"
        file_path = SCREENSHOTS_DIR / filename

        content = await file.read()
        file_path.write_bytes(content)

        content_hash = hash_bytes(content)
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
    """List screenshots that haven't been processed by the VLM yet."""
    processed = get_processed_filenames()
    pending = []
    for path in SCREENSHOTS_DIR.iterdir():
        if path.suffix.lower() in ALLOWED_EXTENSIONS and path.name not in processed:
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

    processed_names = get_processed_filenames()
    pending_paths = [
        p for p in SCREENSHOTS_DIR.iterdir()
        if p.suffix.lower() in ALLOWED_EXTENSIONS and p.name not in processed_names
    ]

    if not pending_paths:
        return {"processed": 0, "needs_review": 0, "results": []}

    results = []
    needs_review = 0

    # Process sequentially to avoid overwhelming Ollama
    for path in pending_paths:
        try:
            vision_result = await analyze_screenshot(path)
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
    """Delete a screenshot file."""
    path = SCREENSHOTS_DIR / name
    if path.exists():
        path.unlink()
        logger.info(f"Deleted screenshot: {name}")
    return {"deleted": True}
