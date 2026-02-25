"""API routes for managing local markdown notes."""

import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
NOTES_DIR = _BACKEND_DIR / "notes"
NOTES_DIR.mkdir(exist_ok=True)


class CreateNoteRequest(BaseModel):
    title: str = "Untitled"


class UpdateNoteRequest(BaseModel):
    content: str


def _extract_title(content: str, filename: str = "") -> str:
    """Extract the first # heading as the title, fall back to filename stem."""
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    # Use filename (without .md) if no heading found
    if filename:
        stem = filename.rsplit(".", 1)[0] if "." in filename else filename
        if stem:
            return stem
    return "Untitled"


def _note_path(note_id: str) -> Path:
    path = (NOTES_DIR / f"{note_id}.md").resolve()
    if not path.parent == NOTES_DIR.resolve():
        raise HTTPException(status_code=400, detail="Invalid note id")
    return path


# -- Importable write helpers (used by agent.py) ----------------------------


def create_note_file(title: str) -> dict:
    """Create a new note file on disk. Returns {id, title, updated_at}."""
    note_id = str(uuid.uuid4())
    path = NOTES_DIR / f"{note_id}.md"
    content = f"# {title}\n\n"
    path.write_text(content, encoding="utf-8")
    updated_at = datetime.now(timezone.utc).isoformat()
    logger.info("Created note %s: %s", note_id, title)
    return {"id": note_id, "title": title, "updated_at": updated_at}


def append_to_note(note_id: str, markdown: str) -> dict:
    """Append markdown to an existing note. Returns {id, title, content, updated_at}."""
    path = NOTES_DIR / f"{note_id}.md"
    if not path.exists():
        raise FileNotFoundError(f"Note {note_id} not found")
    existing = path.read_text(encoding="utf-8")
    updated = existing.rstrip() + "\n\n" + markdown
    path.write_text(updated, encoding="utf-8")
    title = _extract_title(updated, path.name)
    updated_at = datetime.now(timezone.utc).isoformat()
    logger.info("Appended to note %s (%d chars)", note_id, len(markdown))
    return {"id": note_id, "title": title, "content": updated, "updated_at": updated_at}


@router.get("/notes")
async def list_notes():
    """List all saved notes with id, title, and updated_at."""
    notes = []
    for path in NOTES_DIR.glob("*.md"):
        note_id = path.stem
        content = path.read_text(encoding="utf-8")
        title = _extract_title(content, path.name)
        stat = path.stat()
        notes.append({
            "id": note_id,
            "title": title,
            "updated_at": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
        })
    # Most recently updated first
    notes.sort(key=lambda n: n["updated_at"], reverse=True)
    return notes


@router.get("/notes/{note_id}")
async def get_note(note_id: str):
    """Read the full content of a note."""
    path = _note_path(note_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Note not found")
    return {"id": note_id, "content": path.read_text(encoding="utf-8")}


@router.post("/notes")
async def create_note(req: CreateNoteRequest):
    """Create a new note with a title."""
    result = create_note_file(req.title)
    return {"id": result["id"], "title": result["title"]}


@router.put("/notes/{note_id}")
async def update_note(note_id: str, req: UpdateNoteRequest):
    """Overwrite a note's content."""
    path = _note_path(note_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Note not found")
    path.write_text(req.content, encoding="utf-8")
    title = _extract_title(req.content, path.name)
    return {"id": note_id, "title": title}


@router.delete("/notes/{note_id}")
async def delete_note(note_id: str):
    """Delete a note."""
    path = _note_path(note_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Note not found")
    path.unlink()
    logger.info(f"Deleted note {note_id}")
    return {"deleted": True}
