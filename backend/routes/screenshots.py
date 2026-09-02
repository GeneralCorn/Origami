"""Screenshot upload, processing, status, and digest API routes."""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from starlette.responses import FileResponse, PlainTextResponse

from config import SCREENSHOTS_DIR, SCREENSHOT_AUTO_PROCESS
from services import screenshot_pipeline as pipeline
from services.chroma import delete_chunks, get_document_meta, hash_bytes, indexed_file_ids
from services.collections import normalize_collection_id
from services.digest import digest_filenames, get_digest, list_digests
from services.images import HEIF_SUPPORTED
from services.ocr import engine_name, load_record
from services.vision import check_ollama_health

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
if HEIF_SUPPORTED:
    ALLOWED_EXTENSIONS |= {".heic", ".heif"}

MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".heic": "image/heic",
    ".heif": "image/heif",
}


def _safe_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return ext if ext in ALLOWED_EXTENSIONS else ".png"


def _screenshot_path(name: str) -> Path:
    """A path inside SCREENSHOTS_DIR, or a 400 for anything that tries to leave it."""
    if not name or Path(name).name != name:
        raise HTTPException(status_code=400, detail="Invalid screenshot name")
    return SCREENSHOTS_DIR / name


def _existing_by_hash(content_hash: str) -> Path | None:
    """The screenshot already on disk holding these exact bytes, if any.

    Uploads are named after their content hash, so this is a lookup rather
    than a scan. It has to be a disk check: the store only learns about a
    screenshot once it is processed, so a Chroma lookup leaves every
    screenshot still pending outside the dedup window, which is the entire
    window that matters for a capture the user just took twice. The
    extension is not part of the identity, because the same bytes saved as
    .png and as .jpg are still one screenshot.
    """
    for ext in ALLOWED_EXTENSIONS:
        path = SCREENSHOTS_DIR / f"{content_hash}{ext}"
        if path.exists():
            return path
    return None


def _processed_names() -> set[str]:
    """Filenames of screenshots that must not be analysed again.

    The union of the two records that exist. indexed_file_ids() is the
    store, authoritative for anything this branch ingested;
    digest_filenames() covers the history that predates it, where the
    digest was the only record kept.
    """
    return indexed_file_ids() | digest_filenames()


def _pending_paths() -> list[Path]:
    processed = _processed_names()
    return sorted(
        (p for p in SCREENSHOTS_DIR.iterdir() if p.suffix.lower() in ALLOWED_EXTENSIONS and p.name not in processed),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


# ── Upload ────────────────────────────────────────────────────────


@router.post("/screenshots/upload")
async def upload_screenshots(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    process: bool = Query(SCREENSHOT_AUTO_PROCESS),
):
    """Upload one or more screenshots and, by default, start processing them.

    The response returns as soon as the bytes are on disk; the pipeline
    runs behind it and /screenshots/status says how far it has got.
    """
    results = []
    for file in files:
        content = await file.read()
        content_hash = hash_bytes(content)

        existing = _existing_by_hash(content_hash)
        if existing:
            results.append({
                "id": existing.name,
                "filename": existing.name,
                "original_name": file.filename,
                "size": len(content),
                "content_hash": content_hash,
                "status": "duplicate",
                "duplicate": True,
            })
            logger.info(f"Skipped duplicate screenshot: {existing.name}")
            continue

        ext = _safe_ext(file.filename or "image.png")
        filename = f"{content_hash}{ext}"
        path = SCREENSHOTS_DIR / filename
        path.write_bytes(content)

        status = "pending"
        if process:
            background_tasks.add_task(pipeline.process_screenshot, path)
            status = "processing"
        results.append({
            "id": filename,
            "filename": filename,
            "original_name": file.filename,
            "size": len(content),
            "content_hash": content_hash,
            "status": status,
        })
        logger.info(f"Saved screenshot: {filename} ({len(content)} bytes)")

    return results


# ── Pending, status, process ──────────────────────────────────────


@router.get("/screenshots/pending")
async def list_pending():
    """Screenshots on disk that are not yet in the store, with their job stage if one is running."""
    pending = []
    for path in _pending_paths():
        stat = path.stat()
        job = pipeline.job_for(path.name)
        pending.append({
            "filename": path.name,
            "size": stat.st_size,
            "uploaded_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "stage": job.stage if job else None,
        })
    return pending


@router.get("/screenshots/status")
async def status():
    """What the pipeline is doing, and what it has to work with."""
    return {
        "jobs": pipeline.jobs(),
        "pending": len(_pending_paths()),
        "engines": {
            "ocr": engine_name(),
            "vision": await check_ollama_health(),
        },
    }


@router.post("/screenshots/process")
async def process_screenshots():
    """Process every pending screenshot now and wait for the batch.

    No longer a 503 when Ollama is down: the OCR engine and the local
    classifier do not need it, and a screenshot only fails when nothing on
    the machine can read it, which each result then says.
    """
    pending = [p for p in _pending_paths() if p.name not in pipeline.in_flight()]
    if not pending:
        return {"processed": 0, "failed": 0, "needs_review": 0, "results": []}

    jobs = await asyncio.gather(*[pipeline.process_screenshot(path) for path in pending])
    results = [job.to_dict() for job in jobs]
    return {
        "processed": sum(1 for job in jobs if job.stage == pipeline.Stage.DONE),
        "failed": sum(1 for job in jobs if job.stage == pipeline.Stage.ERROR),
        "needs_review": sum(1 for job in jobs if job.stage == pipeline.Stage.DONE and job.collection == "inbox"),
        "results": results,
    }


# ── One screenshot ────────────────────────────────────────────────


@router.get("/screenshots/{name}/file")
async def get_screenshot_file(name: str):
    path = _screenshot_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(path, media_type=MEDIA_TYPES.get(path.suffix.lower(), "image/png"))


@router.get("/screenshots/{name}/text")
async def get_screenshot_text(name: str):
    """The text read out of the screenshot, as plain text."""
    _screenshot_path(name)
    record = load_record(name)
    if record is None:
        raise HTTPException(status_code=404, detail="No text has been extracted for this screenshot")
    return PlainTextResponse(record.get("text", ""))


@router.get("/screenshots/{name}")
async def get_screenshot(name: str):
    """Everything known about one screenshot: the record, the store's view, the job."""
    path = _screenshot_path(name)
    record = load_record(name)
    meta = get_document_meta(name)
    job = pipeline.job_for(name)
    if record is None and meta is None and job is None and not path.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return {
        "filename": name,
        "on_disk": path.exists(),
        "record": record,
        "indexed": meta is not None,
        "collection": (record or {}).get("collection") or (meta or {}).get("collection"),
        "title": (record or {}).get("title") or (meta or {}).get("title"),
        "job": job.to_dict() if job else None,
    }


class CollectionChange(BaseModel):
    collection_id: str


@router.patch("/screenshots/{name}/collection")
async def change_collection(name: str, req: CollectionChange):
    """File a screenshot under a different collection, in the store, the notes and the digest."""
    path = _screenshot_path(name)
    if not path.exists() and load_record(name) is None and get_document_meta(name) is None:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    try:
        record = await pipeline.recategorize(name, req.collection_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No collection {req.collection_id!r}")
    return {"status": "moved", "collection": record["collection"], "note_id": record.get("note_id", "")}


@router.delete("/screenshots/{name}")
async def delete_screenshot(name: str):
    """Delete a screenshot and every trace of it: segments, record, note entry, digest line."""
    path = _screenshot_path(name)
    deleted_chunks = delete_chunks(name)
    await pipeline.forget(name)
    if path.exists():
        path.unlink()
        logger.info(f"Deleted screenshot: {name} ({deleted_chunks} segments)")
    return {"deleted": True, "deleted_chunks": deleted_chunks}


# ── Digests ───────────────────────────────────────────────────────


@router.get("/digests")
async def get_digests():
    return list_digests()


@router.get("/digests/{week}")
async def get_digest_content(week: str):
    content = get_digest(week)
    if content is None:
        raise HTTPException(status_code=404, detail="Digest not found")
    return {"week": week, "content": content}


class RecategorizeRequest(BaseModel):
    screenshot_name: str
    new_category: str


@router.patch("/digests/{week}/recategorize")
async def recategorize(week: str, req: RecategorizeRequest):
    """Older clients move an entry by digest week; it is the same move as PATCH /screenshots/{name}/collection."""
    _screenshot_path(req.screenshot_name)
    collection_id = normalize_collection_id(req.new_category)
    record = await pipeline.recategorize(req.screenshot_name, collection_id)
    return {"status": "moved", "new_category": record["collection"], "collection": record["collection"]}
