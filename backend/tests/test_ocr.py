"""The OCR layer: results, engine selection, the record, and one real engine.

Everything but the last test runs with no engine installed. The RapidOCR
test skips when the ocr-fallback extra is absent, and is the only place a
real recogniser is exercised, which is what makes the adapter trustworthy
rather than merely typed.
"""

import asyncio
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from config import OCR_DIR, SCREENSHOTS_DIR
import services.ocr as ocr
from services.ocr import (
    AppleVisionEngine,
    OcrLine,
    OcrResult,
    RapidOcrEngine,
    delete_record,
    load_record,
    reading_order,
    recognize,
    record_path,
    resolve_engine,
    save_record,
)


@pytest.fixture(autouse=True)
def _fresh_engine():
    ocr.override_engine(None, resolved=False)
    yield
    ocr.override_engine(None, resolved=False)


class _FakeEngine:
    name = "fake"

    def __init__(self, result: OcrResult | None = None):
        self.calls: list[Path] = []
        self.result = result or OcrResult(
            engine="fake", lines=(OcrLine("hello", 0.9), OcrLine("world", 0.7)), width=10, height=20, elapsed_s=0.01,
        )

    def recognize(self, path: Path) -> OcrResult:
        self.calls.append(path)
        return self.result


# ── Results ───────────────────────────────────────────────────────


def test_text_joins_non_empty_lines_and_confidence_averages_them():
    result = OcrResult(
        engine="x", lines=(OcrLine("a", 1.0), OcrLine("  ", 0.0), OcrLine("b", 0.5)), width=1, height=1, elapsed_s=0,
    )

    assert result.text == "a\nb"
    assert result.line_texts == ["a", "b"]
    assert result.mean_confidence == 0.75


def test_result_round_trips_through_its_dict():
    original = OcrResult(
        engine="rapidocr",
        lines=(OcrLine("NVDA $875.40", 0.97, (0.1, 0.2, 0.5, 0.25)),),
        width=1179, height=2556, elapsed_s=2.02,
    )

    restored = OcrResult.from_dict(original.to_dict())

    assert restored == original
    assert original.to_dict()["mean_confidence"] == 0.97


def test_from_text_marks_a_vlm_transcription_honestly():
    result = OcrResult.from_text("line one\n\nline two\n", engine="vlm")

    assert result.engine == "vlm"
    assert result.line_texts == ["line one", "line two"]
    assert result.mean_confidence == 0.0


def test_reading_order_is_rows_then_columns():
    right_top = OcrLine("B", 1.0, (0.6, 0.10, 0.9, 0.14))
    left_top = OcrLine("A", 1.0, (0.1, 0.11, 0.4, 0.15))
    below = OcrLine("C", 1.0, (0.1, 0.30, 0.4, 0.34))

    assert [l.text for l in reading_order([below, right_top, left_top])] == ["A", "B", "C"]


# ── Engine selection ──────────────────────────────────────────────


def test_off_means_the_vlm_does_the_reading():
    assert resolve_engine("off") is None
    assert resolve_engine("vlm") is None


def test_auto_prefers_vision_when_it_is_available(monkeypatch):
    monkeypatch.setattr(AppleVisionEngine, "available", staticmethod(lambda: True))
    monkeypatch.setattr(RapidOcrEngine, "available", staticmethod(lambda: True))

    assert resolve_engine("auto").name == "apple_vision"


def test_auto_falls_back_to_rapidocr(monkeypatch):
    monkeypatch.setattr(AppleVisionEngine, "available", staticmethod(lambda: False))
    monkeypatch.setattr(RapidOcrEngine, "available", staticmethod(lambda: True))

    assert resolve_engine("auto").name == "rapidocr"


def test_auto_with_nothing_installed_is_none(monkeypatch):
    monkeypatch.setattr(AppleVisionEngine, "available", staticmethod(lambda: False))
    monkeypatch.setattr(RapidOcrEngine, "available", staticmethod(lambda: False))

    assert resolve_engine("auto") is None


def test_an_explicit_engine_that_is_missing_yields_none_not_another_engine(monkeypatch):
    """Asking for Vision on Linux must not silently run RapidOCR: the name
    is recorded on every segment, and a wrong name is a wrong record."""
    monkeypatch.setattr(AppleVisionEngine, "available", staticmethod(lambda: False))
    monkeypatch.setattr(RapidOcrEngine, "available", staticmethod(lambda: True))

    assert resolve_engine("apple_vision") is None


def test_an_unknown_engine_name_is_none():
    assert resolve_engine("tesseract") is None


def test_the_process_engine_is_resolved_once(monkeypatch):
    calls = []
    monkeypatch.setattr(ocr, "resolve_engine", lambda preference=None: calls.append(1) or _FakeEngine())

    ocr.current_engine()
    ocr.current_engine()

    assert len(calls) == 1


# ── The async entry point ─────────────────────────────────────────


async def test_recognize_returns_none_when_no_engine_is_configured():
    ocr.override_engine(None)

    assert await recognize(SCREENSHOTS_DIR / "anything.png") is None


async def test_recognize_runs_the_engine_off_the_loop():
    engine = _FakeEngine()
    ocr.override_engine(engine)
    path = SCREENSHOTS_DIR / "shot.png"

    result = await recognize(path)

    assert engine.calls == [path]
    assert result.text == "hello\nworld"


async def test_recognize_bounds_concurrency():
    """A batch drop of twenty screenshots must not spawn twenty OCR threads."""
    running = 0
    peak = 0

    class Slow:
        name = "slow"

        def recognize(self, path):
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            import time
            time.sleep(0.02)
            running -= 1
            return OcrResult(engine="slow", lines=(), width=0, height=0, elapsed_s=0)

    ocr.override_engine(Slow())
    await asyncio.gather(*[recognize(SCREENSHOTS_DIR / f"{i}.png") for i in range(8)])

    assert peak <= 2


# ── The record ────────────────────────────────────────────────────


def test_record_round_trips_and_lives_under_ocr_dir():
    path = save_record("abc.png", {"screenshot": "abc.png", "ocr": {"engine": "fake"}})

    assert path.parent == OCR_DIR.resolve()
    assert load_record("abc.png") == {"screenshot": "abc.png", "ocr": {"engine": "fake"}}
    assert delete_record("abc.png") is True
    assert load_record("abc.png") is None
    assert delete_record("abc.png") is False


def test_record_path_refuses_traversal():
    with pytest.raises(ValueError):
        record_path("../notes/escape.md")


# ── One real engine ───────────────────────────────────────────────


def _render_iphone_screenshot(lines: list[str]) -> Path:
    path = SCREENSHOTS_DIR / "rendered-iphone.png"
    image = Image.new("RGB", (1179, 2556), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=44)
    for candidate in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        try:
            font = ImageFont.truetype(candidate, 44)
            break
        except OSError:
            continue
    y = 120
    for line in lines:
        draw.text((80, y), line, fill="black", font=font)
        y += 150
    image.save(path)
    return path


def _assert_reads_in_order(result, engine_name: str) -> None:
    assert result.engine == engine_name
    assert result.width == 1179 and result.height == 2556
    texts = result.line_texts
    assert texts.index("Severance") < texts.index("Season 2, Episode 3")
    assert any("NVDA" in t for t in texts)
    assert result.mean_confidence > 0.8
    assert all(0.0 <= v <= 1.0 for line in result.lines for v in line.box)
    # Boxes are normalised with the origin at the top left: the clock is
    # the first thing on the screen.
    assert result.lines[0].box[1] < result.lines[-1].box[1]


def test_rapidocr_reads_a_rendered_screenshot_in_order():
    pytest.importorskip("rapidocr")
    path = _render_iphone_screenshot(["9:41", "Severance", "Season 2, Episode 3", "NVDA $875.40 +3.2%"])

    _assert_reads_in_order(RapidOcrEngine().recognize(path), "rapidocr")


def test_apple_vision_reads_a_rendered_screenshot_in_order():
    """Vision reports boxes with a bottom-left origin; the adapter flips them."""
    if not AppleVisionEngine.available():
        pytest.skip("the Vision framework binding is macOS only")
    path = _render_iphone_screenshot(["9:41", "Severance", "Season 2, Episode 3", "NVDA $875.40 +3.2%"])

    _assert_reads_in_order(AppleVisionEngine().recognize(path), "apple_vision")
