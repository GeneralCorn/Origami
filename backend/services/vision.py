"""Ollama VLM client for screenshots: the caption, and the collection vote.

Before on-device OCR existed this call did everything, transcription
included, and a 7B model transcribing a dense screen is the slow part of
the whole pipeline. Now the OCR text is handed to the model in the prompt
and it is asked only for what needs eyes: a title, a description, which
collection the screenshot belongs to, and the app it shows. The
transcription field survives for the machine with no OCR engine at all.

Two other changes bring the latency down. The image is downscaled before
it is encoded, because the caption does not need retina pixels, and the
response is constrained by a JSON schema through Ollama's `format` field,
so the model cannot wander into prose the parser then has to rescue.
"""

import base64
import json
import logging
import re
import time
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import httpx

from config import OLLAMA_KEEP_ALIVE, OLLAMA_TIMEOUT, OLLAMA_URL, OLLAMA_VLM_MODEL, VLM_MAX_SIDE
from services import usage
from services.collections import INBOX_ID, Collection
from services.images import downscaled_jpeg
from services.text_utils import as_text

logger = logging.getLogger(__name__)

MAX_OCR_CHARS_IN_PROMPT = 3000
HEALTH_CACHE_SECONDS = 30.0

DEFAULT_RESULT = {
    "title": "Untitled Screenshot",
    "description": "",
    "extracted_text": "",
    "collection": INBOX_ID,
    "source_app": "unknown",
    "confidence": "low",
}

_FIELDS_CAPTION = """\
- "title": 5 to 8 words naming the specific thing on screen (the show, the library, the ticker, the paper, the place), not the app.
- "description": one or two sentences on what the screenshot shows and why someone might have saved it.
- "collection": exactly one id from the list below, or "inbox" if none fits.
- "source_app": the app or site shown, lowercase, such as "netflix", "safari", "x", "robinhood", "arxiv"; "unknown" if unclear.
- "confidence": "high" if the collection is clear, "low" if you are guessing."""

_FIELDS_TEXT = """\
- "extracted_text": every line of readable text in the screenshot, in reading order, one line per line. Empty string if there is none."""


def build_prompt(collections: Sequence[Collection], ocr_text: str | None) -> str:
    """The instruction the VLM sees, with the user's collections spelled out."""
    listed = "\n".join(
        f"- {c.id}: {c.name}. {c.description}" for c in collections if c.id != INBOX_ID
    ) or "- (no collections defined)"
    if ocr_text is not None and ocr_text.strip():
        quoted = ocr_text.strip()
        if len(quoted) > MAX_OCR_CHARS_IN_PROMPT:
            quoted = quoted[:MAX_OCR_CHARS_IN_PROMPT].rstrip() + "\n[... truncated ...]"
        return (
            "You are filing a phone screenshot into a personal knowledge base. The text on it "
            "has already been read by OCR and is quoted below, so do not transcribe it again; "
            "describe what the screenshot shows and decide where it belongs.\n\n"
            "Return a JSON object with exactly these fields:\n"
            f"{_FIELDS_CAPTION}\n\n"
            f"Collections:\n{listed}\n\n"
            f"Text read from the screenshot:\n\"\"\"\n{quoted}\n\"\"\""
        )
    return (
        "You are filing a phone screenshot into a personal knowledge base. Read it and "
        "return a JSON object with exactly these fields:\n"
        f"{_FIELDS_CAPTION}\n{_FIELDS_TEXT}\n\n"
        f"Collections:\n{listed}"
    )


def response_schema(collections: Sequence[Collection], *, include_text: bool) -> dict:
    """The JSON schema Ollama constrains generation to.

    The collection enum is the important part: the model can only answer
    with an id that exists, so normalisation downstream is a safety net
    rather than the mechanism.
    """
    ids = sorted({c.id for c in collections} | {INBOX_ID})
    properties: dict = {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "collection": {"type": "string", "enum": ids},
        "source_app": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "low"]},
    }
    if include_text:
        properties["extracted_text"] = {"type": "string"}
    return {"type": "object", "properties": properties, "required": list(properties)}


# Tests swap this for an httpx.MockTransport; production leaves it None.
_transport: httpx.AsyncBaseTransport | None = None


def _client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, transport=_transport)


_health_cache: tuple[float, bool] | None = None


def reset_health_cache() -> None:
    global _health_cache
    _health_cache = None


async def check_ollama_health(*, force: bool = False) -> bool:
    """Whether Ollama is up and has the VLM pulled. Cached briefly.

    The status endpoint the renderer polls asks this every couple of
    seconds while a batch processes; hitting Ollama that often is noise.
    """
    global _health_cache
    now = time.monotonic()
    if not force and _health_cache and now - _health_cache[0] < HEALTH_CACHE_SECONDS:
        return _health_cache[1]
    healthy = False
    try:
        async with _client(5) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code == 200:
                models = [m.get("name", "") for m in resp.json().get("models", [])]
                base = OLLAMA_VLM_MODEL.split(":")[0]
                healthy = any(m.startswith(base) for m in models)
    except Exception:
        healthy = False
    _health_cache = (now, healthy)
    return healthy


def _parse_vlm_response(text: str) -> dict:
    """Parse VLM JSON with fallbacks for output that ignored the schema."""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    for pattern in (r"```(?:json)?\s*(\{.*?\})\s*```", r"\{.*\}"):
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1) if match.lastindex else match.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

    logger.warning("Could not parse VLM response as JSON: %s", text[:200])
    return {**DEFAULT_RESULT, "description": text[:200].strip()}


def coerce_result(raw: dict, collections: Sequence[Collection]) -> dict:
    """Model output made safe to read: strings where strings were asked for,
    a collection that exists, a confidence from the closed set.

    extracted_text is left as the model shaped it, because
    screenshot_ingest.extracted_text knows how to read a list of lines.
    """
    known = {c.id for c in collections} | {INBOX_ID}
    result = dict(DEFAULT_RESULT)
    result["title"] = as_text(raw.get("title")) or DEFAULT_RESULT["title"]
    result["description"] = as_text(raw.get("description"))
    result["source_app"] = (as_text(raw.get("source_app")) or "unknown").lower()
    result["confidence"] = "high" if as_text(raw.get("confidence")).lower() == "high" else "low"
    chosen = as_text(raw.get("collection")).lower().replace("_", "-").replace(" ", "-")
    result["collection"] = chosen if chosen in known else INBOX_ID
    text = raw.get("extracted_text")
    result["extracted_text"] = text if isinstance(text, (str, list, tuple)) else ""
    return result


async def _record_vlm_usage(body: dict, prompt_chars: int) -> None:
    """Record the local VLM's token counts at zero dollars.

    They cost nothing, and they are the only numbers that could ever
    substantiate a claim that routing work to a local model is cheaper.
    """
    await usage.record(usage.CallRecord(
        ts=datetime.now(timezone.utc).isoformat(),
        purpose="vision",
        route="",
        origin="background",
        model=body.get("model", OLLAMA_VLM_MODEL),
        input_tokens=int(body.get("prompt_eval_count", 0) or 0),
        output_tokens=int(body.get("eval_count", 0) or 0),
        cache_read_tokens=0,
        cache_creation_tokens=0,
        billable_input_tokens=int(body.get("prompt_eval_count", 0) or 0),
        elapsed_s=round(int(body.get("total_duration", 0) or 0) / 1e9, 4),
        prompt_chars=prompt_chars,
        cost_usd=0.0,
        priced=False,
        turn_id=str(uuid.uuid4()),
        loop=0,
        stub=False,
        failed=False,
    ))


async def analyze_screenshot(
    image_path: Path,
    *,
    ocr_text: str | None = None,
    collections: Sequence[Collection] = (),
) -> dict:
    """Ask the VLM what a screenshot shows and where it belongs.

    With ocr_text the model captions and classifies only. Without it the
    model also transcribes, which is the pre-OCR behaviour and the path a
    machine with no OCR engine still takes.
    """
    include_text = not (ocr_text and ocr_text.strip())
    try:
        image_bytes = downscaled_jpeg(image_path, VLM_MAX_SIDE)
    except Exception as exc:
        # Pillow could not decode it; let the VLM try the original bytes.
        logger.debug("Sending %s to the VLM undownscaled: %s", image_path.name, exc)
        image_bytes = image_path.read_bytes()
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    prompt = build_prompt(collections, ocr_text)

    payload = {
        "model": OLLAMA_VLM_MODEL,
        "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
        "stream": False,
        "format": response_schema(collections, include_text=include_text),
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"temperature": 0.1},
    }

    started = time.perf_counter()
    async with _client(OLLAMA_TIMEOUT) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        resp.raise_for_status()

    body = resp.json()
    await _record_vlm_usage(body, len(prompt) + len(image_b64))
    result = coerce_result(_parse_vlm_response(body.get("message", {}).get("content", "")), collections)
    logger.info(
        "VLM %s: %s -> %s (%s) in %.1fs",
        image_path.name, result["title"], result["collection"], result["confidence"],
        time.perf_counter() - started,
    )
    return result
