"""The screenshot adapter, ARCHITECTURE_V2 section 7 step 4, after OCR split from the VLM.

Pure functions on purpose: no Chroma, no Ollama, no key, no network.
"""

import hashlib

from config import CHUNK_SIZE, SCREENSHOTS_DIR
from services.ocr import OcrLine, OcrResult
from services.screenshot_ingest import (
    CAPTION_ORDINAL,
    DEFAULT_TITLE,
    FIRST_OCR_ORDINAL,
    extracted_text,
    ocr_from_vision,
    screenshot_drafts,
    screenshot_item,
    screenshot_title,
)

_IMAGE_BYTES = b"\x89PNG\r\n\x1a\n fake pixels"

_VISION = {
    "title": "Postgres connection error in terminal",
    "description": "A terminal window showing a failed database connection.",
    "extracted_text": "",
    "collection": "tech-to-try",
    "source_app": "iterm",
    "confidence": "high",
}


def _ocr(*texts: str, engine: str = "rapidocr", confidence: float = 0.95) -> OcrResult:
    return OcrResult(
        engine=engine,
        lines=tuple(OcrLine(t, confidence) for t in texts),
        width=1179, height=2556, elapsed_s=1.0,
    )


def _screenshot_on_disk(name: str = "11111111-2222-3333-4444-555555555555.png"):
    path = SCREENSHOTS_DIR / name
    path.write_bytes(_IMAGE_BYTES)
    return path


# ── Item ──────────────────────────────────────────────────────────


def test_item_carries_source_identity():
    path = _screenshot_on_disk()
    item = screenshot_item(path, "Postgres connection error in terminal")

    assert item.source_type == "screenshot"
    assert item.id == path.name
    assert item.source_id == hashlib.sha256(_IMAGE_BYTES).hexdigest()
    assert item.title == "Postgres connection error in terminal"
    assert item.raw_ref == f"screenshots/{path.name}"
    assert item.created_at == ""
    assert item.ingested_at


def test_screenshot_provenance_is_untrusted():
    item = screenshot_item(_screenshot_on_disk(), "t")

    assert item.provenance.trust == "untrusted"
    assert item.provenance.channel == "screenshot"
    assert item.provenance.origin == "unknown"


# ── Title ─────────────────────────────────────────────────────────


def test_title_prefers_the_vlm_then_the_ocr_then_the_default():
    ocr = _ocr("9:41", "Back", "Severance", "Season 2")

    assert screenshot_title(_VISION, ocr) == _VISION["title"]
    assert screenshot_title(None, ocr) == "Severance"
    assert screenshot_title({"title": DEFAULT_TITLE}, ocr) == "Severance"
    assert screenshot_title(None, None) == DEFAULT_TITLE
    assert screenshot_title({"title": ["a", "list"]}, _ocr("9:41")) == DEFAULT_TITLE


# ── Segments ──────────────────────────────────────────────────────


def test_ocr_and_caption_are_separate_segments():
    drafts = screenshot_drafts(_VISION, _ocr("ERROR: connection refused at line 42"))

    assert [d.ordinal for d in drafts] == [CAPTION_ORDINAL, FIRST_OCR_ORDINAL]
    assert [d.modality for d in drafts] == ["caption", "ocr"]
    assert [d.content_source for d in drafts] == ["generated", "extracted"]


def test_segments_record_who_produced_them():
    caption, ocr = screenshot_drafts(_VISION, _ocr("ERROR: connection refused", engine="apple_vision", confidence=0.91))

    assert caption.span["generated_by"]
    assert ocr.span == {"ocr_engine": "apple_vision", "ocr_confidence": 0.91}


def test_ocr_alone_indexes_before_any_caption_exists():
    """The fast path: text lands in the store seconds before the VLM runs."""
    drafts = screenshot_drafts(None, _ocr("Severance", "Season 2, Episode 3"))

    assert [d.modality for d in drafts] == ["ocr"]
    assert drafts[0].ordinal == FIRST_OCR_ORDINAL
    assert drafts[0].content == "Severance\nSeason 2, Episode 3"


def test_chrome_is_dropped_from_the_embedded_text():
    drafts = screenshot_drafts(None, _ocr("9:41", "5G 100%", "Back", "NVDA $875.40 +3.2%", "Play"))

    assert [d.content for d in drafts] == ["NVDA $875.40 +3.2%"]


def test_missing_text_leaves_the_caption_at_its_own_ordinal():
    drafts = screenshot_drafts(_VISION, None)

    assert len(drafts) == 1
    assert drafts[0].ordinal == CAPTION_ORDINAL
    assert drafts[0].modality == "caption"


def test_all_chrome_produces_no_ocr_segment():
    drafts = screenshot_drafts(_VISION, _ocr("9:41", "100%"))

    assert [d.modality for d in drafts] == ["caption"]


def test_an_empty_result_still_yields_one_indexable_segment():
    """An Item with no segments would never reach Chroma, so it would stay
    pending forever and be re-analysed on every run."""
    drafts = screenshot_drafts(None, None, title="From the filename")

    assert len(drafts) == 1
    assert drafts[0].modality == "caption"
    assert drafts[0].content == "From the filename"
    assert screenshot_drafts({"description": ""}, None)[0].content == DEFAULT_TITLE


def test_non_string_vlm_output_does_not_raise():
    drafts = screenshot_drafts({"title": ["a", "list"], "description": None}, None)

    assert [d.modality for d in drafts] == ["caption"]
    assert drafts[0].content == DEFAULT_TITLE


def test_long_text_is_split_for_the_embedder():
    """The embedder's window is 512 tokens, so an unsplit page of
    screenshotted text embedded only its opening and the rest was stored
    but unreachable by search."""
    page = ["The board reviewed the quarterly numbers in detail."] * 150
    drafts = screenshot_drafts(_VISION, _ocr(*page))
    ocr = [d for d in drafts if d.modality == "ocr"]

    # Consecutive duplicate lines collapse to one, so widen the input.
    assert len(ocr) >= 1
    page = [f"Paragraph {i}: the board reviewed the quarterly numbers in detail." for i in range(150)]
    ocr = [d for d in screenshot_drafts(_VISION, _ocr(*page)) if d.modality == "ocr"]
    assert len(ocr) > 1
    assert all(len(d.content) <= CHUNK_SIZE for d in ocr)
    assert [d.ordinal for d in ocr] == list(range(FIRST_OCR_ORDINAL, FIRST_OCR_ORDINAL + len(ocr)))
    assert "Paragraph 149" in ocr[-1].content


# ── The VLM transcription fallback ────────────────────────────────


def test_line_shaped_extracted_text_is_kept_not_dropped():
    assert extracted_text({"extracted_text": ["line one", "line two"]}) == "line one\nline two"
    assert extracted_text({"extracted_text": {"unusable": "shape"}}) == ""
    assert extracted_text({"extracted_text": "  plain  "}) == "plain"


def test_a_vlm_transcription_becomes_an_ocr_result_that_says_so():
    result = ocr_from_vision({"extracted_text": "ERROR: connection refused\nat line 42"})

    assert result.engine == "vlm"
    assert result.line_texts == ["ERROR: connection refused", "at line 42"]
    assert result.mean_confidence == 0.0
    assert ocr_from_vision({"extracted_text": ""}) is None
