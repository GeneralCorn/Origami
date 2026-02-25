import json
import logging
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from services.agent import stream_research_agent
from services.chroma import resolve_tag

router = APIRouter()
logger = logging.getLogger(__name__)


# -- Request models (AI SDK v6 UIMessage format) ----------------------------


class ChatMessagePart(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str
    text: str = ""


class ChatMessage(BaseModel):
    """Accept both AI SDK v6 UIMessage (parts) and plain {role, content}."""

    model_config = ConfigDict(extra="ignore")
    role: str
    parts: list[ChatMessagePart] = []
    content: str | None = None

    def get_text(self) -> str:
        if self.parts:
            return " ".join(
                p.text for p in self.parts if p.type == "text" and p.text
            )
        return self.content or ""


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    messages: list[ChatMessage]
    current_note: str = ""
    allow_edits: bool = False
    active_note_title: str = ""
    active_note_id: str | None = None
    scope: list[str] = []


# -- SSE helpers (AI SDK v6 JSON event stream) ------------------------------


def _sse(data: dict) -> str:
    """Format a single Server-Sent Event."""
    return f"data: {json.dumps(data)}\n\n"


def _reasoning_block(content: str, block_id: str) -> str:
    """Emit a complete reasoning part (start + delta + end)."""
    return (
        _sse({"type": "reasoning-start", "id": block_id})
        + _sse({"type": "reasoning-delta", "id": block_id, "delta": content})
        + _sse({"type": "reasoning-end", "id": block_id})
    )


# -- Endpoint ---------------------------------------------------------------


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    Streaming chat endpoint compatible with the AI SDK v6 JSON event stream.

    Invokes the LangGraph research agent and streams execution steps
    (searching, reasoning, note-taking) as reasoning parts, then the final
    response as a text part.
    """
    messages = [
        {"role": m.role, "content": m.get_text()}
        for m in request.messages
    ]

    # Resolve scope: tags (prefixed with #) become file_ids, UUIDs pass through
    file_ids: list[str] = []
    for entry in request.scope:
        if entry.startswith("#"):
            file_ids.extend(resolve_tag(entry[1:]))
        else:
            file_ids.append(entry)
    resolved_scope = file_ids if file_ids else None

    async def generate():
        yield _sse({"type": "start"})

        reasoning_counter = 0

        async for event in stream_research_agent(
            messages,
            request.current_note,
            allow_edits=request.allow_edits,
            active_note_title=request.active_note_title,
            active_note_id=request.active_note_id,
            scope=resolved_scope,
        ):
            event_type = event["type"]
            content = event["content"]

            if event_type == "text":
                # Final answer → text part
                text_id = str(uuid.uuid4())
                yield _sse({"type": "text-start", "id": text_id})
                yield _sse({"type": "text-delta", "id": text_id, "delta": content})
                yield _sse({"type": "text-end", "id": text_id})
            elif event_type == "action":
                # File action proposal → data part SSE
                logger.info("[SSE] Emitting data-action: %s file=%s markdown_len=%d",
                            content.get("action"), content.get("filename"), len(content.get("markdown", "")))
                yield _sse({
                    "type": "data-action",
                    "id": str(uuid.uuid4()),
                    "data": content,
                })
            elif event_type in ("reasoning", "searching", "note_taking"):
                block_id = f"r-{reasoning_counter}"
                reasoning_counter += 1
                yield _reasoning_block(content, block_id)

        yield _sse({"type": "finish", "finishReason": "stop"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
