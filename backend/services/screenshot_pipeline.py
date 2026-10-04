"""From a screenshot on disk to a filed, indexed, captioned Item.

The order is the point. A screenshot is useful the moment its text is in
the index and its entry is in a note, and both of those need only the OCR
engine and the local classifier: a couple of seconds, no network, no
model download beyond the embedder the index already uses. The caption is
worth having, but it costs a 7B vision model ten to thirty seconds per
image, so it runs second, over an Item that already exists, and rewrites
only what it improves: the caption segment, the title, and the collection
if the model saw something the text did not say.

    read text      OCR engine, or the VLM when there is no engine
    classify       keywords + embedding (+ the VLM's vote if it already ran)
    file           index, collection note, weekly digest, extraction record
    caption        VLM, optional, serialised because Ollama runs one model at a time
    re-file        only when the caption changed the title or the collection

Every stage reports into an in-memory job table the renderer polls, and
the last state of every screenshot survives in its record under DATA_DIR/ocr.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from config import VLM_ENRICH
from services import collections as collections_store
from services import digest
from services import ocr as ocr_service
from services.chroma import set_collection
from services.classify_screenshot import Classification, Embedder, classify, default_embedder
from services.collections import INBOX_ID, Collection, Entry, find_entry_collection, move_entry, remove_entry, upsert_entry
from services.ocr import OcrResult, delete_record, load_record, save_record
from services.screen_text import content_lines
from services.screenshot_ingest import index_screenshot, ocr_from_vision, screenshot_title
from services.text_utils import as_text
from services.vision import analyze_screenshot, check_ollama_health

logger = logging.getLogger(__name__)


class Stage(StrEnum):
    QUEUED = "queued"
    READING = "reading"
    CLASSIFYING = "classifying"
    INDEXING = "indexing"
    CAPTIONING = "captioning"
    DONE = "done"
    ERROR = "error"


FINISHED = frozenset({Stage.DONE, Stage.ERROR})
# Finished jobs stay visible this long so the renderer can show what just
# happened to a batch, then drop out of the table.
JOB_TTL_S = 900.0


class NoTextSource(RuntimeError):
    """Nothing on this machine can read the screenshot right now."""


@dataclass
class Job:
    filename: str
    stage: str = Stage.QUEUED
    title: str = ""
    collection: str = ""
    confidence: float = 0.0
    method: str = ""
    ocr_engine: str = ""
    captioned: bool = False
    error: str = ""
    started_at: str = ""
    updated_at: str = ""
    finished_monotonic: float = 0.0

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("finished_monotonic")
        data["confidence"] = round(self.confidence, 3)
        return data

    def advance(self, stage: Stage) -> None:
        self.stage = stage
        self.updated_at = _now()
        if stage in FINISHED:
            self.finished_monotonic = asyncio.get_event_loop().time()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_jobs: dict[str, Job] = {}
# Ollama serves one model at a time; two concurrent VLM requests queue on
# its side anyway, and serialising here keeps the timeout honest.
_vlm_lock = asyncio.Lock()


def _embedder_or_none() -> Embedder | None:
    try:
        return default_embedder()
    except Exception as exc:  # pragma: no cover - fastembed import failure
        logger.warning("No embedder for the classifier; keywords only: %s", exc)
        return None


# Swapped by tests. Production resolves the corpus embedder lazily.
_embedder_factory: Callable[[], Embedder | None] = _embedder_or_none


def _prune() -> None:
    now = asyncio.get_event_loop().time()
    for name in [n for n, j in _jobs.items() if j.stage in FINISHED and now - j.finished_monotonic > JOB_TTL_S]:
        del _jobs[name]


def jobs() -> list[dict]:
    _prune()
    return [job.to_dict() for job in sorted(_jobs.values(), key=lambda j: j.started_at, reverse=True)]


def job_for(filename: str) -> Job | None:
    return _jobs.get(filename)


def in_flight() -> set[str]:
    return {name for name, job in _jobs.items() if job.stage not in FINISHED}


def reset_jobs() -> None:
    _jobs.clear()


def _entry(path: Path, title: str, vision: dict | None, ocr: OcrResult | None, captured_at: str) -> Entry:
    return Entry(
        screenshot=path.name,
        title=title,
        captured_at=captured_at,
        source_app=as_text((vision or {}).get("source_app")),
        description=as_text((vision or {}).get("description")),
        lines=tuple(content_lines(ocr.line_texts)) if ocr else (),
    )


def _vlm_vote(vision: dict | None) -> str | None:
    chosen = as_text((vision or {}).get("collection"))
    return chosen if chosen and chosen != INBOX_ID else None


async def _file(
    path: Path,
    *,
    title: str,
    vision: dict | None,
    ocr: OcrResult | None,
    classification: Classification,
    captured_at: str,
    previous_collection: str | None = None,
) -> dict:
    """Index, note, digest, record. Idempotent, so the caption pass calls it again."""
    collection_id = classification.collection_id
    await index_screenshot(path, vision_result=vision, ocr=ocr, collection_id=collection_id, title=title)

    entry = _entry(path, title, vision, ocr, captured_at)
    if previous_collection and previous_collection != collection_id:
        note_id = await asyncio.to_thread(move_entry, path.name, collection_id, entry)
    else:
        note_id = await asyncio.to_thread(upsert_entry, collection_id, entry)
    week = await asyncio.to_thread(
        digest.append_to_digest,
        screenshot_filename=path.name,
        title=title,
        collection_id=collection_id,
        source_app=entry.source_app,
        description=entry.description,
    )

    record = {
        "screenshot": path.name,
        "title": title,
        "collection": collection_id,
        "classification": classification.to_dict(),
        "vision": vision,
        "ocr": ocr.to_dict() if ocr else None,
        "text": ocr.text if ocr else "",
        "content_lines": list(entry.lines),
        "note_id": note_id,
        "week": week,
        "captured_at": captured_at,
        "processed_at": _now(),
    }
    await asyncio.to_thread(save_record, path.name, record)
    return record


async def process_screenshot(path: Path, *, enrich: bool | None = None) -> Job:
    """Run the pipeline over one screenshot. Never raises; the Job says what happened.

    A screenshot already in flight is not started twice: the upload route
    queues one and a /process call may find it pending a moment later.
    """
    existing = _jobs.get(path.name)
    if existing and existing.stage not in FINISHED:
        return existing

    job = Job(filename=path.name, started_at=_now(), updated_at=_now())
    _jobs[path.name] = job
    enrich = VLM_ENRICH if enrich is None else enrich
    captured_at = _now()

    try:
        collections = collections_store.list_collections()

        # 1. Text. The OCR engine when there is one; otherwise the VLM has
        #    to read it, which makes the caption pass come first.
        job.advance(Stage.READING)
        ocr = await ocr_service.recognize(path)
        vision: dict | None = None
        if ocr is None:
            if not await check_ollama_health():
                raise NoTextSource(
                    "No OCR engine is installed and Ollama is not running, so nothing "
                    "can read this screenshot yet. Install the ocr-fallback extra or start Ollama."
                )
            job.advance(Stage.CAPTIONING)
            async with _vlm_lock:
                vision = await analyze_screenshot(path, collections=collections)
            ocr = ocr_from_vision(vision)
        job.ocr_engine = ocr.engine if ocr else ""
        text = ocr.text if ocr else ""
        classifier_text = "\n".join(content_lines(ocr.line_texts)) if ocr else ""

        # 2. Classify, locally.
        job.advance(Stage.CLASSIFYING)
        embedder = _embedder_factory()
        classification = await asyncio.to_thread(
            classify, classifier_text, collections, embedder=embedder, vlm_choice=_vlm_vote(vision),
        )

        # 3. File it. From here on the screenshot is searchable.
        job.advance(Stage.INDEXING)
        title = screenshot_title(vision, ocr)
        await _file(path, title=title, vision=vision, ocr=ocr, classification=classification, captured_at=captured_at)
        job.title, job.collection = title, classification.collection_id
        job.confidence, job.method = classification.confidence, classification.method
        job.captioned = vision is not None

        # 4. Caption, if the VLM has not already been consulted and is available.
        if vision is None and enrich and await check_ollama_health():
            job.advance(Stage.CAPTIONING)
            try:
                async with _vlm_lock:
                    vision = await analyze_screenshot(path, ocr_text=text, collections=collections)
                refined = await asyncio.to_thread(
                    classify, classifier_text, collections, embedder=embedder, vlm_choice=_vlm_vote(vision),
                )
                title = screenshot_title(vision, ocr)
                await _file(
                    path, title=title, vision=vision, ocr=ocr, classification=refined,
                    captured_at=captured_at, previous_collection=classification.collection_id,
                )
                job.title, job.collection = title, refined.collection_id
                job.confidence, job.method = refined.confidence, refined.method
                job.captioned = True
            except Exception as exc:
                # The Item is already indexed and filed; the caption was a bonus.
                logger.warning("Caption pass failed for %s: %s", path.name, exc)

        job.advance(Stage.DONE)
    except Exception as exc:
        job.error = str(exc)
        job.advance(Stage.ERROR)
        logger.error("Failed to process %s: %s", path.name, exc)
    return job


def _entry_from_record(record: dict) -> Entry | None:
    if not record:
        return None
    vision = record.get("vision") or {}
    return Entry(
        screenshot=str(record.get("screenshot", "")),
        title=str(record.get("title", "")),
        captured_at=str(record.get("captured_at") or record.get("processed_at") or ""),
        source_app=as_text(vision.get("source_app")),
        description=as_text(vision.get("description")),
        lines=tuple(str(line) for line in record.get("content_lines", [])),
    )


async def recategorize(filename: str, collection_id: str) -> dict:
    """Move a screenshot to another collection, everywhere it is recorded.

    The store, the notes and the digest are updated together, and the
    record marks the choice as the user's so a re-run of the classifier
    never overrides it. Returns the updated record (possibly minimal, for a
    screenshot processed before records existed).
    """
    collection = collections_store.get_collection(collection_id)
    if collection is None:
        raise KeyError(collection_id)
    record = load_record(filename) or {"screenshot": filename}
    await asyncio.to_thread(set_collection, filename, collection.id)
    entry = _entry_from_record(record) if record.get("title") else None
    note_id = await asyncio.to_thread(move_entry, filename, collection.id, entry)
    moved = await asyncio.to_thread(digest.move_entry, record.get("week"), filename, collection.id)
    if not moved and record.get("title"):
        await asyncio.to_thread(
            digest.append_to_digest,
            screenshot_filename=filename, title=record["title"], collection_id=collection.id,
            source_app=(record.get("vision") or {}).get("source_app", ""),
            description=(record.get("vision") or {}).get("description", ""),
            week=record.get("week"),
        )
    record["collection"] = collection.id
    record["note_id"] = note_id
    record["classification"] = {**record.get("classification", {}), "collection": collection.id, "method": "manual", "confidence": 1.0}
    await asyncio.to_thread(save_record, filename, record)
    job = _jobs.get(filename)
    if job:
        job.collection, job.method, job.confidence = collection.id, "manual", 1.0
    return record


async def forget(filename: str) -> None:
    """Remove every trace of a screenshot outside the store: record, note entry, digest line."""
    holder = await asyncio.to_thread(find_entry_collection, filename)
    if holder:
        held_by = collections_store.get_collection(holder)
        if held_by and held_by.note_id:
            await asyncio.to_thread(remove_entry, held_by.note_id, filename)
    await asyncio.to_thread(digest.remove_entry, filename)
    await asyncio.to_thread(delete_record, filename)
    _jobs.pop(filename, None)
