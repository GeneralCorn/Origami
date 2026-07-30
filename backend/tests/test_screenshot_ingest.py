"""The screenshot adapter, ARCHITECTURE_V2 section 7 step 4.

Pure functions on purpose: no Chroma, no Ollama, no key, no network.
"""

import hashlib

from config import SCREENSHOTS_DIR
from services.screenshot_ingest import (
    CAPTION_ORDINAL,
    DEFAULT_TITLE,
    OCR_ORDINAL,
    screenshot_drafts,
    screenshot_item,
)

_IMAGE_BYTES = b"\x89PNG\r\n\x1a\n fake pixels"

_FULL_RESULT = {
    "title": "Postgres connection error in terminal",
    "description": "A terminal window showing a failed database connection.",
    "extracted_text": "ERROR: connection refused at line 42",
    "category": "code",
    "source_app": "iterm",
    "confidence": "high",
}


def _screenshot_on_disk(name: str = "11111111-2222-3333-4444-555555555555.png"):
    path = SCREENSHOTS_DIR / name
    path.write_bytes(_IMAGE_BYTES)
    return path


def test_item_carries_source_identity():
    path = _screenshot_on_disk()
    item = screenshot_item(path, _FULL_RESULT)

    assert item.source_type == "screenshot"
    assert item.id == path.stem
    assert item.source_id == hashlib.sha256(_IMAGE_BYTES).hexdigest()
    assert item.title == _FULL_RESULT["title"]
    assert item.raw_ref == f"screenshots/{path.name}"
    # The capture time is not recoverable, and an empty string is honest
    # where a plausible wrong value is not.
    assert item.created_at == ""
    assert item.ingested_at


def test_screenshot_provenance_is_untrusted():
    """Section 3 names this case verbatim: the OCR of a screenshot."""
    item = screenshot_item(_screenshot_on_disk(), _FULL_RESULT)

    assert item.provenance.trust == "untrusted"
    assert item.provenance.channel == "screenshot"
    # Not "self": the only signal about the content is the VLM's own guess.
    assert item.provenance.origin == "unknown"


def test_ocr_and_caption_are_separate_segments():
    drafts = screenshot_drafts(_FULL_RESULT)

    assert [d.ordinal for d in drafts] == [OCR_ORDINAL, CAPTION_ORDINAL]
    assert [d.modality for d in drafts] == ["ocr", "caption"]
    assert [d.content_source for d in drafts] == ["extracted", "generated"]


def test_extracted_text_survives_as_its_own_segment():
    """The defect step 4 fixes: extracted_text had zero readers."""
    drafts = screenshot_drafts(_FULL_RESULT)
    ocr = next(d for d in drafts if d.modality == "ocr")

    assert ocr.content == "ERROR: connection refused at line 42"


def test_missing_text_leaves_the_caption_at_its_own_ordinal():
    """Absence must not renumber, or a re-run moves the caption's id."""
    drafts = screenshot_drafts({**_FULL_RESULT, "extracted_text": ""})

    assert len(drafts) == 1
    assert drafts[0].ordinal == CAPTION_ORDINAL
    assert drafts[0].modality == "caption"


def test_whitespace_only_text_produces_no_ocr_segment():
    drafts = screenshot_drafts({**_FULL_RESULT, "extracted_text": "   \n  "})

    assert [d.modality for d in drafts] == ["caption"]


def test_caption_falls_back_to_the_title():
    drafts = screenshot_drafts({**_FULL_RESULT, "description": ""})
    caption = next(d for d in drafts if d.modality == "caption")

    assert caption.content == _FULL_RESULT["title"]


def test_an_empty_result_still_yields_one_indexable_segment():
    """An Item with no segments would never reach Chroma, so it would stay
    pending forever and be re-analysed on every run."""
    drafts = screenshot_drafts({"title": "", "description": "", "extracted_text": ""})

    assert len(drafts) == 1
    assert drafts[0].content == DEFAULT_TITLE


def test_non_string_vlm_output_does_not_raise():
    """VLM output is untyped JSON; a list where a string was asked for must
    not reach an f-string."""
    drafts = screenshot_drafts({
        "title": ["a", "list"],
        "description": None,
        "extracted_text": ["line one", "line two"],
    })

    assert [d.modality for d in drafts] == ["caption"]
    assert drafts[0].content == DEFAULT_TITLE
