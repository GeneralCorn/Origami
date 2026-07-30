"""What the analyzer is actually shown for one retrieval hit.

ARCHITECTURE_V2 section 2: "Conflating the two is how a system confidently
cites something nobody wrote." The storage side records the distinction;
these tests pin the point where the agent reads it.
"""

from prompts import ANALYZE_PROMPT
from services.agent import _excerpt_block
from services.llm import Prompt

_CAPTION_HIT = {
    "text": "The user appears to be debugging a failing production database and looks frustrated.",
    "source": "shot.png",
    "source_type": "screenshot",
    "modality": "caption",
    "content_source": "generated",
    "prov_trust": "untrusted",
}

_OCR_HIT = {
    "text": "ERROR: connection refused at line 42",
    "source": "shot.png",
    "source_type": "screenshot",
    "modality": "ocr",
    "content_source": "extracted",
    "prov_trust": "untrusted",
}


def test_a_model_written_caption_is_labelled_as_one():
    block = _excerpt_block(1, _CAPTION_HIT)

    assert "WRITTEN BY A MODEL" in block
    assert "a description of an image" in block
    assert _CAPTION_HIT["text"] in block


def test_text_that_came_out_of_the_artifact_is_labelled_verbatim():
    block = _excerpt_block(2, _OCR_HIT)

    assert "WRITTEN BY A MODEL" not in block
    assert "verbatim from the source" in block
    assert "text read out of an image" in block


def test_the_two_are_distinguishable_in_the_assembled_prompt():
    """The failure this prevents: the VLM's guess about the user's mood and
    the terminal text that was really on screen arrive as two anonymous
    paragraphs under one "excerpts" heading, with an instruction to cite
    both."""
    chunks_text = "\n\n---\n\n".join(
        _excerpt_block(i + 1, hit) for i, hit in enumerate([_CAPTION_HIT, _OCR_HIT])
    )
    rendered = Prompt.render(ANALYZE_PROMPT, {
        "current_query": "what was on screen",
        "current_notes": "None yet.",
        "chunks_text": chunks_text,
        "active_notes": "No active notes.",
    }).text

    speculation = rendered.index(_CAPTION_HIT["text"])
    on_screen = rendered.index(_OCR_HIT["text"])
    assert rendered.count("WRITTEN BY A MODEL about the source") == 1
    assert rendered.rindex("WRITTEN BY A MODEL about the source", 0, speculation) > 0
    assert "verbatim from the source" in rendered[speculation:on_screen]


def test_provenance_trust_reaches_the_prompt():
    assert "trust: untrusted" in _excerpt_block(1, _CAPTION_HIT)
