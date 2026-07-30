"""The numbers the UI renders must describe the calls the ledger recorded.

Every test here pins an invariant between three places that used to disagree:
the per-turn meta attached to the text part, the append-only ledger, and the
month-to-date aggregate. A cost figure that is merely plausible is worse than
none, because it is the number the whole phase exists to produce.
"""

import json
import subprocess
from pathlib import Path

import pytest

from config import HAIKU_MODEL
from services import usage
from services.llm import Budget, ModelSpec, Prompt, Purpose, _to_result, complete

_REPO = Path(__file__).resolve().parents[2]


def _ledger_rows() -> list[dict]:
    path = usage.ledger_path()
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


async def _run_turn(monkeypatch, route: str) -> dict:
    """One interactive turn with fake retrieval and the route forced."""
    from prompts import CLASSIFY_PROMPT
    from services import agent

    async def fake_search(q, n_results=5, file_ids=None):
        return [
            {"text": f"chunk {i} about scaling", "source": "paper.pdf", "prov_trust": "trusted"}
            for i in range(5)
        ]

    async def fake_classify(q, history, note_preview, budget):
        result = await complete(Purpose.CLASSIFY, Prompt.render(CLASSIFY_PROMPT, {
            "history": history, "note_preview": note_preview[:500], "query": q,
        }), budget)
        return route, result

    monkeypatch.setattr(agent, "vector_search", fake_search)
    monkeypatch.setattr(agent, "classify_query", fake_classify)

    meta = {}
    async for event in agent.stream_research_agent(
        [{"role": "user", "content": "what does the paper say about scaling"}]
    ):
        if event["type"] == "text":
            meta = event["meta"]
    return meta


@pytest.mark.parametrize("route", ["fast_fact", "normal_rag", "deep_research"])
async def test_turn_totals_cover_every_call_the_turn_made(monkeypatch, route):
    """The classifier's tokens used to be dropped on the floor.

    classify_query wrote its ledger row but discarded the ModelResult, so
    state["total_cost_usd"] started at zero while total_calls came from
    budget.calls_made, which the classifier does increment. The footer
    rendered a call count and a dollar figure describing different sets of
    calls, understating every turn by one Haiku call on the modal route.
    """
    meta = await _run_turn(monkeypatch, route)
    rows = _ledger_rows()

    assert [r["purpose"] for r in rows][0] == "classify"
    assert meta["total_input_tokens"] == sum(r["input_tokens"] for r in rows)
    assert meta["total_output_tokens"] == sum(r["output_tokens"] for r in rows)
    assert meta["total_cost_usd"] == round(sum(r["cost_usd"] for r in rows), 6)


@pytest.mark.parametrize("route", ["fast_fact", "normal_rag", "deep_research"])
async def test_total_calls_equals_the_ledger_row_count(monkeypatch, route):
    """total_calls comes from the budget, the cost from the accumulator.

    They are only comparable if both count the same calls, so the row count
    is asserted against the number the user sees.
    """
    meta = await _run_turn(monkeypatch, route)
    assert meta["total_calls"] == len(_ledger_rows())


class _FakeProvider:
    """Stands in for ChatAnthropic so the priced branch runs with no key.

    Stub mode short-circuits pricing to zero, which would make any assertion
    about dollar parity vacuous. This drives the real _to_result path with a
    real model id and a real usage block instead.
    """

    def __init__(self, model, **_):
        self.model = model

    async def ainvoke(self, messages):
        from langchain_core.messages import AIMessage

        msg = AIMessage(
            content='{"action": "chat", "message": "Answer."}',
            response_metadata={"model_name": self.model},
        )
        msg.usage_metadata = {
            "input_tokens": 1000,
            "output_tokens": 100,
            "total_tokens": 1100,
            "input_token_details": {},
        }
        return msg


@pytest.mark.parametrize("route", ["fast_fact", "normal_rag", "deep_research"])
async def test_the_dollar_total_in_the_footer_is_the_turn_s_real_spend(monkeypatch, route):
    """The parity that matters, on priced rows rather than free stub rows.

    Every call costs the same nonzero amount here, so a missing call shows up
    as a proportional shortfall — which is exactly how the dropped classifier
    presented: 3 calls beside a cost covering 2.
    """
    from services import llm

    monkeypatch.setattr(llm, "MODEL_STUB", False)
    monkeypatch.setattr(llm, "ANTHROPIC_API_KEY", "test-key-not-used")
    monkeypatch.setattr(llm, "ChatAnthropic", _FakeProvider)

    meta = await _run_turn(monkeypatch, route)
    rows = _ledger_rows()

    assert all(r["priced"] for r in rows)
    assert all(r["cost_usd"] > 0 for r in rows)
    assert meta["total_cost_usd"] == round(sum(r["cost_usd"] for r in rows), 6)
    assert meta["total_calls"] == len(rows)
    # The classifier is one of the calls the money covers, not an extra tick
    # on the counter beside it.
    classify = next(r for r in rows if r["purpose"] == "classify")
    assert classify["cost_usd"] > 0
    assert meta["total_cost_usd"] >= classify["cost_usd"] * len(rows) - 1e-9


async def test_the_classifier_is_billed_to_the_turn_it_classified(monkeypatch):
    """One turn_id, so the append-only ledger and the footer agree per turn."""
    await _run_turn(monkeypatch, "normal_rag")
    rows = _ledger_rows()
    assert len({r["turn_id"] for r in rows}) == 1
    assert {r["purpose"] for r in rows} == {"classify", "analyze", "final_response"}


async def test_stub_calls_are_free_and_flagged_not_priced_as_real_spend():
    """The stub estimates tokens from char_count; pricing them invents money.

    _to_result deliberately substituted the routed model id for the stub's
    own "stub", which resolved a real Anthropic rate and returned
    priced=True. A keyless development run wrote fabricated dollars into the
    same monthly file a real key writes to.
    """
    from prompts import CONTEXTUALIZER_PROMPT

    budget = Budget.background("ingest", max_calls=2)
    prompt = Prompt.render(
        CONTEXTUALIZER_PROMPT,
        {"whole_document": "d" * 8000, "chunk_content": "c" * 400},
    )
    result = await complete(Purpose.CONTEXTUALIZE, prompt, budget)

    assert result.cost_usd == 0.0
    assert result.priced is False
    # The routed model id is still recorded: which model a route picks is a
    # claim the stub exists to verify. Only the money is withheld.
    assert result.model == HAIKU_MODEL

    mtd = usage.month_to_date()
    assert mtd["total"]["cost_usd"] == 0.0
    assert mtd["stub_calls"] == 1
    assert mtd["stub"]["input_tokens"] == mtd["total"]["input_tokens"]


def test_a_response_without_usage_metadata_is_unpriced_not_free():
    """Zeroed counts against a known model used to report a priced $0.00 call.

    Any systematic loss of usage metadata would then render the pipeline as
    free and read as an enormous saving, and unpriced_calls could not catch
    it because the model is in the price table.
    """
    class NoUsage:
        content = "hello"
        response_metadata = {"model_name": HAIKU_MODEL}

    result = _to_result(NoUsage(), ModelSpec(HAIKU_MODEL, 100, 0.0), 0.1, False)

    assert result.input_tokens == 0
    assert result.cost_usd == 0.0
    assert result.priced is False


async def test_a_failed_call_still_lands_in_the_ledger(monkeypatch):
    """authorize() spends the slot before the invoke, so a raise cannot be silent.

    Without a row, a turn's total_calls exceeded its ledger rows and
    ingest's [COST] line understated a document by exactly the chunks whose
    own comment calls them billed.
    """
    from prompts import CONTEXTUALIZER_PROMPT
    from services import llm

    def boom(purpose, prompt):
        raise RuntimeError("overloaded_error")

    monkeypatch.setattr(llm, "_stub_response", boom)

    budget = Budget.background("ingest", max_calls=1)
    prompt = Prompt.render(CONTEXTUALIZER_PROMPT, {"whole_document": "d", "chunk_content": "c"})
    with pytest.raises(RuntimeError, match="overloaded_error"):
        await complete(Purpose.CONTEXTUALIZE, prompt, budget)

    rows = _ledger_rows()
    assert len(rows) == budget.calls_made == 1
    assert rows[0]["failed"] is True
    assert rows[0]["priced"] is False
    assert rows[0]["input_tokens"] == 0
    assert usage.month_to_date()["failed_calls"] == 1


def test_the_usage_dir_is_not_committable():
    """The stub request dumps hold verbatim document and conversation text.

    USAGE_DIR defaults to backend/usage in the dev layout, so an unignored
    path here means `git add -A` commits the user's documents. The ledger
    itself records no content, which is exactly why the dumps beside it are
    easy to forget.
    """
    for candidate in ("backend/usage/usage-2026-07.jsonl", "backend/usage/requests/turn-0-classify.json"):
        proc = subprocess.run(
            ["git", "check-ignore", "-q", candidate],
            cwd=_REPO, capture_output=True,
        )
        assert proc.returncode == 0, f"{candidate} is not gitignored"
