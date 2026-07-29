"""Ollama VLM client for screenshot analysis."""

import base64
import json
import logging
import re

import httpx

from config import OLLAMA_URL, OLLAMA_VLM_MODEL, OLLAMA_TIMEOUT

logger = logging.getLogger(__name__)

_ANALYZE_PROMPT = """\
Analyze this screenshot and return a JSON object with these fields:
- "title": A short 5-8 word title summarizing the content.
- "description": A concise 1-2 sentence description of what this screenshot shows.
- "extracted_text": Any readable text visible in the screenshot. If no text, return empty string.
- "category": One of [news, social_media, code, documentation, conversation, meme, recipe, shopping, finance, other] or suggest a new one-word category if none fit.
- "source_app": The app or website shown (e.g. "instagram", "twitter", "safari", "chrome", "slack"). If unclear, return "unknown".
- "confidence": "high" if you are confident in the category, "low" if uncertain.

Return ONLY valid JSON, no markdown fences or extra text."""


async def check_ollama_health() -> bool:
    """Check if Ollama is running and the VLM model is available."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code != 200:
                return False
            models = [m["name"] for m in resp.json().get("models", [])]
            # Check if model is available (with or without :latest suffix)
            base = OLLAMA_VLM_MODEL.split(":")[0]
            return any(m.startswith(base) for m in models)
    except Exception:
        return False


def _parse_vlm_response(text: str) -> dict:
    """Parse VLM JSON response with fallback for malformed output."""
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown fences
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding first { ... } block
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # Last resort: return a low-confidence result with raw text as description
    logger.warning(f"Could not parse VLM response as JSON: {text[:200]}")
    return {
        "title": "Untitled Screenshot",
        "description": text[:200].strip(),
        "extracted_text": "",
        "category": "other",
        "source_app": "unknown",
        "confidence": "low",
    }


async def analyze_screenshot(image_path) -> dict:
    """Send an image to the Ollama VLM and get structured analysis."""
    image_bytes = image_path.read_bytes()
    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    payload = {
        "model": OLLAMA_VLM_MODEL,
        "messages": [
            {
                "role": "user",
                "content": _ANALYZE_PROMPT,
                "images": [image_b64],
            }
        ],
        "stream": False,
        "options": {"temperature": 0.1},
    }

    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        resp.raise_for_status()

    raw = resp.json()["message"]["content"]
    result = _parse_vlm_response(raw)

    # Ensure all expected fields exist
    defaults = {
        "title": "Untitled Screenshot",
        "description": "",
        "extracted_text": "",
        "category": "other",
        "source_app": "unknown",
        "confidence": "low",
    }
    for k, v in defaults.items():
        result.setdefault(k, v)

    return result
