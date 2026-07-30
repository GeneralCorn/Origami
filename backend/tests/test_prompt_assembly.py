"""Prompt assembly, provable with no key.

The ingest cache block and the conditional action protocol are both
structural claims about what gets sent, so both are asserted against the
request that would have been made.
"""

import json

from prompts import CONTEXTUALIZER_PROMPT
from services.llm import Prompt


def test_cache_prefix_plus_text_is_the_whole_prompt():
    """Splitting the template must not change a single byte."""
    fields = {"whole_document": "DOC BODY", "chunk_content": "CHUNK BODY"}
    split = Prompt.render(CONTEXTUALIZER_PROMPT, fields, cache_after="whole_document")
    whole = Prompt.render(CONTEXTUALIZER_PROMPT, fields)

    assert split.cache_prefix is not None
    assert split.cache_prefix + split.text == whole.text
    assert whole.cache_prefix is None


def test_the_cached_block_is_the_document_and_carries_the_breakpoint():
    prompt = Prompt.render(
        CONTEXTUALIZER_PROMPT,
        {"whole_document": "DOC BODY", "chunk_content": "CHUNK BODY"},
        cache_after="whole_document",
    )
    blocks = prompt.to_messages()[0].content

    assert len(blocks) == 2
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert "DOC BODY" in blocks[0]["text"]
    assert "CHUNK BODY" not in blocks[0]["text"]
    # The breakpoint must be on the first block. The cache_control invoke
    # kwarg attaches to the last eligible block, which would cache nothing
    # reusable here.
    assert "cache_control" not in blocks[1]
    assert "CHUNK BODY" in blocks[1]["text"]


def test_the_cached_prefix_is_identical_across_chunks():
    """This is the whole basis of the saving."""
    prefixes = {
        Prompt.render(
            CONTEXTUALIZER_PROMPT,
            {"whole_document": "DOC BODY", "chunk_content": f"chunk {i}"},
            cache_after="whole_document",
        ).cache_prefix
        for i in range(5)
    }
    assert len(prefixes) == 1


def test_document_prefix_clears_the_minimum_cacheable_length():
    """Anthropic's floor for Haiku 4.5 is 4,096 tokens.

    Below it the cache silently never engages and no error is returned, so
    the prefix budget is a correctness condition for the saving, not a
    tuning preference. ~4 chars/token is the standard estimate.
    """
    from config import CONTEXT_DOC_CHARS

    assert CONTEXT_DOC_CHARS // 4 > 4096


async def test_stub_mode_dumps_the_request_with_its_cache_block():
    """Proves the wire shape with no key, by reading what would be sent."""
    from services import usage
    from services.ingest import contextualize_chunk
    from services.llm import Budget

    budget = Budget.background("ingest", max_calls=1)
    await contextualize_chunk("DOC BODY " * 100, "CHUNK BODY", budget)

    dumps = sorted(usage.REQUESTS_DIR.glob("*-contextualize.json"))
    assert len(dumps) == 1
    payload = json.loads(dumps[0].read_text())

    assert payload["purpose"] == "contextualize"
    assert payload["max_tokens"] == 100
    content = payload["messages"][0]["content"]
    assert content[0]["cache_control"] == {"type": "ephemeral"}
    assert "DOC BODY" in content[0]["text"]
    assert "CHUNK BODY" in content[1]["text"]


def _final_prompt(allow_edits: bool) -> str:
    from prompts import (
        CHAT_ONLY_INSTRUCTION,
        CHAT_ONLY_PROTOCOL,
        EDIT_ALLOWED_INSTRUCTION,
        EDIT_PROTOCOL,
        FINAL_RESPONSE_WITH_ACTIONS_PROMPT,
    )

    return Prompt.render(
        FINAL_RESPONSE_WITH_ACTIONS_PROMPT,
        {
            "history": "user: hi",
            "notes_text": "- a finding",
            "active_notes": "notes",
            "active_note_title": "Paper",
            "mode_instruction": (
                EDIT_ALLOWED_INSTRUCTION.format(active_note_title="Paper")
                if allow_edits else CHAT_ONLY_INSTRUCTION
            ),
            "action_protocol": EDIT_PROTOCOL if allow_edits else CHAT_ONLY_PROTOCOL,
        },
        mode="replace",
    ).text


def test_chat_only_mode_does_not_ship_the_edit_protocol():
    """CHAT_ONLY_INSTRUCTION already forbids edit and create.

    Sending their schemas and the filename rule anyway is instructions the
    mode instruction has ruled out.
    """
    prompt = _final_prompt(allow_edits=False)
    assert '"action": "create"' not in prompt
    assert '"action": "edit"' not in prompt
    assert "filename" not in prompt
    assert '"action": "chat"' in prompt


def test_edit_mode_still_ships_the_full_protocol():
    prompt = _final_prompt(allow_edits=True)
    assert '"action": "create"' in prompt
    assert '"action": "edit"' in prompt
    assert "filename" in prompt


def test_math_rules_survive_in_both_modes():
    """Not gated on route or content: a bare-LaTeX answer is a wrong answer."""
    for allow_edits in (True, False):
        prompt = _final_prompt(allow_edits)
        assert "NEVER write bare LaTeX" in prompt
        assert "$$" in prompt


def test_no_placeholders_survive_substitution():
    for allow_edits in (True, False):
        prompt = _final_prompt(allow_edits)
        for field in ("{history}", "{notes_text}", "{active_notes}",
                      "{mode_instruction}", "{action_protocol}", "{active_note_title}"):
            assert field not in prompt


def test_chat_only_protocol_is_materially_smaller():
    saved = len(_final_prompt(allow_edits=True)) - len(_final_prompt(allow_edits=False))
    assert saved > 300
