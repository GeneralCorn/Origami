"""API routes for managing chat instances."""

import json
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

router = APIRouter()
logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
CHATS_DIR = _BACKEND_DIR / "chats"
CHATS_DIR.mkdir(exist_ok=True)


class MessagePart(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str
    text: str = ""


class MessageData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    role: str
    parts: list[MessagePart] = []


class SaveChatRequest(BaseModel):
    messages: list[MessageData]
    title: str | None = None


class CreateChatRequest(BaseModel):
    title: str = "New Chat"


def _chat_path(chat_id: str) -> Path:
    path = (CHATS_DIR / f"{chat_id}.json").resolve()
    if not path.parent == CHATS_DIR.resolve():
        raise HTTPException(status_code=400, detail="Invalid chat id")
    return path


def _read_chat(chat_id: str) -> dict:
    path = _chat_path(chat_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Chat not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_chat(chat_id: str, data: dict) -> None:
    path = _chat_path(chat_id)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _extract_title(messages: list[dict]) -> str:
    """Extract title from first user message."""
    for msg in messages:
        if msg.get("role") == "user":
            for part in msg.get("parts", []):
                if part.get("type") == "text" and part.get("text"):
                    text = part["text"].strip()
                    return text[:50] + ("..." if len(text) > 50 else "")
    return "New Chat"


@router.get("/chats")
async def list_chats():
    """List all chat instances."""
    chats = []
    for path in CHATS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            chats.append({
                "id": data["id"],
                "title": data.get("title", "New Chat"),
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
                "message_count": len(data.get("messages", [])),
            })
        except (json.JSONDecodeError, KeyError):
            continue
    chats.sort(key=lambda c: c["updated_at"], reverse=True)
    return chats


@router.post("/chats")
async def create_chat(req: CreateChatRequest):
    """Create a new chat instance."""
    chat_id = uuid.uuid4().hex[:10]
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "id": chat_id,
        "title": req.title,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    _write_chat(chat_id, data)
    logger.info(f"Created chat {chat_id}: {req.title}")
    return {"id": chat_id, "title": req.title}


@router.get("/chats/{chat_id}")
async def get_chat(chat_id: str):
    """Get a chat instance with all messages."""
    return _read_chat(chat_id)


@router.put("/chats/{chat_id}")
async def update_chat(chat_id: str, req: SaveChatRequest):
    """Save messages to a chat instance."""
    data = _read_chat(chat_id)
    now = datetime.now(timezone.utc).isoformat()

    # Filter to only text/reasoning parts
    filtered_messages = []
    for msg in req.messages:
        filtered_parts = [
            p.model_dump() for p in msg.parts
            if p.type in ("text", "reasoning")
        ]
        if filtered_parts or msg.role == "user":
            filtered_messages.append({
                "id": msg.id,
                "role": msg.role,
                "parts": filtered_parts,
            })

    data["messages"] = filtered_messages
    data["updated_at"] = now

    if req.title:
        data["title"] = req.title
    elif not data.get("title") or data["title"] == "New Chat":
        data["title"] = _extract_title(filtered_messages)

    _write_chat(chat_id, data)
    return {"id": chat_id, "title": data["title"], "updated_at": now}


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str):
    """Delete a chat instance."""
    path = _chat_path(chat_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Chat not found")
    path.unlink()
    logger.info(f"Deleted chat {chat_id}")
    return {"deleted": True}
