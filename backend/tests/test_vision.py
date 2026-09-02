"""The VLM call after OCR took transcription away from it.

No Ollama here: the transport is mocked, and what is asserted is the shape
of the request and the safety of the response handling.
"""

import base64
import io
import json

import httpx
import pytest
from PIL import Image

from config import SCREENSHOTS_DIR
import services.vision as vision
from services.collections import DEFAULT_COLLECTIONS, INBOX_ID
from services.vision import (
    analyze_screenshot,
    build_prompt,
    check_ollama_health,
    coerce_result,
    response_schema,
)

CANDIDATES = [c for c in DEFAULT_COLLECTIONS if c.id in {"shows-to-watch", "papers-to-read", INBOX_ID}]


@pytest.fixture(autouse=True)
def _no_transport():
    vision._transport = None
    vision.reset_health_cache()
    yield
    vision._transport = None
    vision.reset_health_cache()


def _screenshot(width=1179, height=2556) -> "Path":
    from pathlib import Path

    path: Path = SCREENSHOTS_DIR / "vlm-input.png"
    Image.new("RGB", (width, height), "white").save(path)
    return path


# ── Prompt and schema ─────────────────────────────────────────────


def test_with_ocr_text_the_model_is_told_not_to_transcribe():
    prompt = build_prompt(CANDIDATES, "Severance\nSeason 2, Episode 3")

    assert "do not transcribe it again" in prompt
    assert "Severance\nSeason 2, Episode 3" in prompt
    assert '"extracted_text"' not in prompt
    assert "- shows-to-watch: Shows to watch." in prompt
    # The inbox is the fallback answer, not a destination to advertise.
    assert "- inbox:" not in prompt


def test_without_ocr_text_transcription_is_requested():
    prompt = build_prompt(CANDIDATES, None)

    assert '"extracted_text"' in prompt
    assert "do not transcribe" not in prompt


def test_long_ocr_text_is_truncated_in_the_prompt():
    prompt = build_prompt(CANDIDATES, "x" * 10_000)

    assert "[... truncated ...]" in prompt
    assert len(prompt) < 4_500


def test_schema_constrains_the_collection_to_ids_that_exist():
    schema = response_schema(CANDIDATES, include_text=False)

    assert schema["properties"]["collection"]["enum"] == ["inbox", "papers-to-read", "shows-to-watch"]
    assert schema["properties"]["confidence"]["enum"] == ["high", "low"]
    assert "extracted_text" not in schema["properties"]
    assert set(schema["required"]) == set(schema["properties"])
    assert "extracted_text" in response_schema(CANDIDATES, include_text=True)["properties"]


# ── Coercion ──────────────────────────────────────────────────────


def test_coerce_fills_defaults_and_validates_the_collection():
    result = coerce_result({"title": ["a", "list"], "collection": "Shows To Watch", "confidence": "HIGH"}, CANDIDATES)

    assert result["title"] == "Untitled Screenshot"
    assert result["collection"] == "shows-to-watch"
    assert result["confidence"] == "high"
    assert result["source_app"] == "unknown"
    assert result["description"] == ""


def test_coerce_sends_an_invented_collection_to_the_inbox():
    assert coerce_result({"collection": "cryptozoology"}, CANDIDATES)["collection"] == INBOX_ID
    assert coerce_result({"confidence": "maybe"}, CANDIDATES)["confidence"] == "low"


def test_coerce_keeps_line_shaped_extracted_text_for_the_adapter():
    assert coerce_result({"extracted_text": ["a", "b"]}, CANDIDATES)["extracted_text"] == ["a", "b"]
    assert coerce_result({"extracted_text": {"no": "dicts"}}, CANDIDATES)["extracted_text"] == ""


def test_parse_recovers_json_from_fences_and_prose():
    assert vision._parse_vlm_response('```json\n{"title": "t"}\n```')["title"] == "t"
    assert vision._parse_vlm_response('Sure! {"title": "t"} hope that helps')["title"] == "t"
    fallback = vision._parse_vlm_response("I cannot see the image")
    assert fallback["collection"] == INBOX_ID
    assert fallback["description"] == "I cannot see the image"


# ── The request ───────────────────────────────────────────────────


async def test_analyze_sends_a_downscaled_image_and_the_schema():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={
            "model": "qwen2.5-vl:7b",
            "message": {"role": "assistant", "content": json.dumps({
                "title": "Severance episode page",
                "description": "Netflix's page for an episode of Severance.",
                "collection": "shows-to-watch",
                "source_app": "Netflix",
                "confidence": "high",
            })},
            "prompt_eval_count": 900, "eval_count": 60, "total_duration": 4_000_000_000,
        })

    vision._transport = httpx.MockTransport(handler)

    result = await analyze_screenshot(_screenshot(), ocr_text="Severance\nSeason 2", collections=CANDIDATES)

    payload = seen["json"]
    assert payload["format"]["properties"]["collection"]["enum"] == ["inbox", "papers-to-read", "shows-to-watch"]
    assert "extracted_text" not in payload["format"]["properties"]
    assert payload["keep_alive"] == vision.OLLAMA_KEEP_ALIVE
    assert "do not transcribe" in payload["messages"][0]["content"]
    with Image.open(io.BytesIO(base64.b64decode(payload["messages"][0]["images"][0]))) as sent:
        assert sent.format == "JPEG"
        assert max(sent.size) == vision.VLM_MAX_SIDE
    assert result["collection"] == "shows-to-watch"
    assert result["source_app"] == "netflix"
    assert result["extracted_text"] == ""


async def test_analyze_without_ocr_asks_for_the_text():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": json.dumps({
            "title": "t", "description": "d", "collection": "papers-to-read",
            "source_app": "arxiv", "confidence": "low", "extracted_text": "line one\nline two",
        })}})

    vision._transport = httpx.MockTransport(handler)

    result = await analyze_screenshot(_screenshot(), collections=CANDIDATES)

    assert "extracted_text" in seen["json"]["format"]["properties"]
    assert result["extracted_text"] == "line one\nline two"


async def test_analyze_raises_on_an_ollama_error():
    vision._transport = httpx.MockTransport(lambda request: httpx.Response(500, text="boom"))

    with pytest.raises(httpx.HTTPStatusError):
        await analyze_screenshot(_screenshot(), ocr_text="x", collections=CANDIDATES)


async def test_health_is_cached_between_polls():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"models": [{"name": "qwen2.5-vl:7b"}]})

    vision._transport = httpx.MockTransport(handler)

    assert await check_ollama_health() is True
    assert await check_ollama_health() is True
    assert calls == 1
    assert await check_ollama_health(force=True) is True
    assert calls == 2


async def test_health_is_false_when_ollama_is_down_or_the_model_is_missing():
    vision._transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"models": [{"name": "deepseek-r1:8b"}]}))
    assert await check_ollama_health(force=True) is False

    def down(request):
        raise httpx.ConnectError("refused")

    vision._transport = httpx.MockTransport(down)
    assert await check_ollama_health(force=True) is False
