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
    _PLACEHOLDER,
    _REGISTERED_TEMPLATES,
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


def _backend_sources() -> list[Path]:
    """Every backend module a scheduled job could plausibly be added to.

    Scoped to services/ and routes/ before, which missed main.py, where a
    task hung off the FastAPI lifespan hook would live, and the one place a
    scheduled job is most likely to go.
    """
    return [
        path for path in sorted(_BACKEND.rglob("*.py"))
        if ".venv" not in path.parts and "tests" not in path.parts
    ]


def test_the_allowlist_scan_covers_main_and_config():
    """The scan is only an allowlist if it looks where the caller would be."""
    scanned = {str(p.relative_to(_BACKEND)) for p in _backend_sources()}
    assert {"main.py", "config.py"} <= scanned
    assert "services/agent.py" in scanned


def test_interactive_constructor_allowlist():
    """Only the interactive turn entrypoint may mint a context-bearing permit.

    This is the test that fails when someone adds a scheduled job that
    wants conversation context. It is the structural answer to a comment
    asking nicely.
    """
    owners = set()
    for path in _backend_sources():
        if "Budget.interactive(" in path.read_text():
            owners.add(str(path.relative_to(_BACKEND)))
    assert owners == {"services/agent.py"}


def test_no_module_hand_builds_a_permit():
    """Budget.interactive/background are the only ways to obtain a permit.

    may_send_context is derived from origin, so the remaining way to claim
    it is to construct Budget directly with origin="interactive" and skip
    the classmethod the allowlist above pins.
    """
    owners = set()
    for path in _backend_sources():
        if path.name == "llm.py":
            continue
        if re.search(r"\bBudget\(", path.read_text()):
            owners.add(str(path.relative_to(_BACKEND)))
    assert owners == set()


def test_the_permit_cannot_grant_itself_context():
    """may_send_context is derived, not stored.

    As a field it was one assignment away from defeating the whole lever:
    Budget has to stay mutable for authorize and adopt_route, so
    `b.may_send_context = True` used to turn a background permit into an
    interactive one.
    """
    budget = Budget.background("nightly_digest", max_calls=1)
    assert budget.may_send_context is False
    with pytest.raises(AttributeError):
        budget.may_send_context = True
    assert budget.may_send_context is False


async def test_a_mutated_background_permit_still_refuses_session_state():
    budget = Budget.background("nightly_digest", max_calls=1)
    budget.origin = "nightly_digest (definitely interactive)"
    with pytest.raises(ContextBudgetError):
        await complete(Purpose.CLASSIFY, _render(Purpose.CLASSIFY), budget)
    assert budget.calls_made == 0


def test_background_may_not_claim_the_interactive_origin():
    with pytest.raises(ValueError, match="interactive origin"):
        Budget.background("interactive", max_calls=1)


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
    placeholder name that nobody classified. The pattern matches the one in
    services.llm, capitals included, so a {History} cannot be classified
    here and unrecognised there.
    """
    # LaTeX subscript in a math example inside final_response.py, not a
    # substitution key. Nothing renders it, and Prompt.render's own check
    # catches it if anyone ever tries.
    known_latex = {"hinge"}

    unclassified: dict[str, set[str]] = {}
    for path in sorted((_BACKEND / "prompts").glob("*.py")):
        found = set(_PLACEHOLDER.findall(path.read_text()))
        stray = found - CONTEXT_FIELDS - CONTEXT_FREE_FIELDS - known_latex
        if stray:
            unclassified[path.name] = stray
    assert unclassified == {}


async def test_render_rejects_an_unclassified_field():
    with pytest.raises(ValueError, match="CONTEXT_FIELDS"):
        Prompt.render("hello {mystery_field}", {"mystery_field": "x"})


async def test_render_rejects_a_capitalised_placeholder():
    """A lowercase-only pattern made capitalisation a way past the gate.

    {History} matched nothing, so `used` was empty, so nothing was
    unclassified and carries_session_state derived to False, and a
    background permit would send the conversation.
    """
    with pytest.raises(ValueError, match="CONTEXT_FIELDS"):
        Prompt.render("Summarize:\n{History}", {"History": "user: hi"})


async def test_render_rejects_a_template_built_at_runtime():
    """The derivation is meaningless if the caller can pre-interpolate.

    A prompt whose session state was pasted into the template itself has no
    placeholders to derive from, so it reported carries_session_state=False
    and a background job could send the whole conversation. Requiring the
    template to be a constant from prompts/ is what closes that, because a
    background job cannot smuggle context through a template it wrote.
    """
    history = "user: my private conversation\nassistant: secret notes"
    with pytest.raises(ValueError, match="prompts/"):
        Prompt.render(f"Summarize this conversation:\n{history}", {})


async def test_a_background_job_cannot_send_a_handwritten_prompt():
    """The end-to-end version of the above, at the chokepoint."""
    history = "user: my private conversation\nassistant: secret notes"
    budget = Budget.background("nightly_digest", max_calls=1)
    with pytest.raises(ValueError, match="prompts/"):
        prompt = Prompt.render(f"Summarize:\n{history}", {})
        await complete(Purpose.CLASSIFY, prompt, budget)
    assert budget.calls_made == 0


def test_every_real_prompt_is_registered():
    """The registry must admit exactly the prompts the backend actually uses."""
    for purpose in _REAL_PROMPTS:
        template, _, _ = _REAL_PROMPTS[purpose]
        assert template in _REGISTERED_TEMPLATES


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
