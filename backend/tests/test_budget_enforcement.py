"""Lever 2: non-interactive work may not send the session's state.

These tests are the enforcement. The gate is only real if adding a
scheduled job that wants conversation context fails here.
"""

import re
from pathlib import Path

import pytest

from prompts import (
    ANALYZE_PROMPT,
    CLASSIFY_PROMPT,
    CONTEXTUALIZER_PROMPT,
    FAST_FACT_PROMPT,
    FINAL_RESPONSE_WITH_ACTIONS_PROMPT,
    REVIEW_PROMPT,
)
from services.llm import (
    CONTEXT_FIELDS,
    CONTEXT_FREE_FIELDS,
    Budget,
    CallBudgetExceeded,
    ContextBudgetError,
    Prompt,
    Purpose,
    complete,
)

_BACKEND = Path(__file__).resolve().parent.parent

# The six real prompts with the field sets their call sites actually pass.
_REAL_PROMPTS: dict[Purpose, tuple[str, dict[str, str], str]] = {
    Purpose.CLASSIFY: (
        CLASSIFY_PROMPT,
        {"history": "user: hi", "note_preview": "notes", "query": "what is X"},
        "format",
    ),
    Purpose.FAST_FACT: (
        FAST_FACT_PROMPT,
        {"history": "user: hi", "note_section": "note", "query": "what is X"},
        "format",
    ),
    Purpose.ANALYZE: (
        ANALYZE_PROMPT,
        {"current_query": "q", "current_notes": "n", "chunks_text": "c", "active_notes": "a"},
        "format",
    ),
    Purpose.REVIEW: (
        REVIEW_PROMPT,
        {"original_question": "q", "notes_text": "n"},
        "format",
    ),
    Purpose.FINAL_RESPONSE: (
        FINAL_RESPONSE_WITH_ACTIONS_PROMPT,
        {
            "history": "user: hi",
            "notes_text": "n",
            "active_notes": "a",
            "active_note_title": "t",
            "mode_instruction": "m",
        },
        "replace",
    ),
    Purpose.CONTEXTUALIZE: (
        CONTEXTUALIZER_PROMPT,
        {"whole_document": "doc", "chunk_content": "chunk"},
        "format",
    ),
}


def _render(purpose: Purpose) -> Prompt:
    template, fields, mode = _REAL_PROMPTS[purpose]
    return Prompt.render(template, fields, mode=mode)


@pytest.mark.parametrize("purpose", [
    Purpose.CLASSIFY, Purpose.FAST_FACT, Purpose.ANALYZE,
    Purpose.REVIEW, Purpose.FINAL_RESPONSE,
])
async def test_background_budget_refuses_session_state(purpose):
    budget = Budget.background("digest", max_calls=10)
    with pytest.raises(ContextBudgetError):
        await complete(purpose, _render(purpose), budget)
    assert budget.calls_made == 0


async def test_background_budget_allows_the_ingest_payload():
    """Ingest is background work that legitimately runs.

    Its prompt carries the document it was handed, not a live session's
    state, so it must pass the same gate the others fail.
    """
    budget = Budget.background("ingest", max_calls=1)
    result = await complete(Purpose.CONTEXTUALIZE, _render(Purpose.CONTEXTUALIZE), budget)
    assert result.text
    assert budget.calls_made == 1


async def test_interactive_budget_may_send_session_state():
    budget = Budget.interactive("normal_rag", 1)
    result = await complete(Purpose.ANALYZE, _render(Purpose.ANALYZE), budget)
    assert result.text


def test_carries_session_state_is_derived_not_declared():
    """A caller cannot promise a context-bearing prompt is background-safe."""
    assert _render(Purpose.ANALYZE).carries_session_state is True
    assert _render(Purpose.CONTEXTUALIZE).carries_session_state is False


def test_interactive_constructor_allowlist():
    """Only the interactive turn entrypoint may mint a context-bearing permit.

    This is the test that fails when someone adds a scheduled job that
    wants conversation context. It is the structural answer to a comment
    asking nicely.
    """
    owners = set()
    for path in sorted((_BACKEND / "services").rglob("*.py")) + sorted((_BACKEND / "routes").rglob("*.py")):
        if "Budget.interactive(" in path.read_text():
            owners.add(str(path.relative_to(_BACKEND)))
    assert owners == {"services/agent.py"}


def test_single_client_construction_site():
    """The chokepoint cannot be bypassed by a new inline construction."""
    owners = set()
    for path in sorted(_BACKEND.rglob("*.py")):
        if ".venv" in path.parts or "tests" in path.parts:
            continue
        if "ChatAnthropic(" in path.read_text():
            owners.add(str(path.relative_to(_BACKEND)))
    assert owners == {"services/llm.py"}


def test_prompt_placeholders_are_classified():
    """Every placeholder in every template is on one side of the gate.

    Stops the derivation in Prompt.render being dodged by inventing a new
    placeholder name that nobody classified.
    """
    # LaTeX subscript in a math example inside final_response.py, not a
    # substitution key. Nothing renders it, and Prompt.render's own check
    # catches it if anyone ever tries.
    known_latex = {"hinge"}

    unclassified: dict[str, set[str]] = {}
    for path in sorted((_BACKEND / "prompts").glob("*.py")):
        found = set(re.findall(r"\{([a-z][a-z0-9_]*)\}", path.read_text()))
        stray = found - CONTEXT_FIELDS - CONTEXT_FREE_FIELDS - known_latex
        if stray:
            unclassified[path.name] = stray
    assert unclassified == {}


async def test_render_rejects_an_unclassified_field():
    with pytest.raises(ValueError, match="CONTEXT_FIELDS"):
        Prompt.render("hello {mystery_field}", {"mystery_field": "x"})


async def test_call_ceiling_is_structural_not_advisory():
    """The ceiling is what makes a runaway loop impossible rather than unlikely."""
    budget = Budget.background("ingest", max_calls=2)
    prompt = _render(Purpose.CONTEXTUALIZE)

    await complete(Purpose.CONTEXTUALIZE, prompt, budget)
    await complete(Purpose.CONTEXTUALIZE, prompt, budget)
    with pytest.raises(CallBudgetExceeded):
        await complete(Purpose.CONTEXTUALIZE, prompt, budget)


async def test_budget_is_required():
    with pytest.raises(TypeError):
        await complete(Purpose.CONTEXTUALIZE, _render(Purpose.CONTEXTUALIZE))
