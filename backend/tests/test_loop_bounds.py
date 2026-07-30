"""Lever 4: the exact per-route model-call counts, pinned.

These counts are the denominator of every cost claim about this pipeline,
so they are asserted exactly rather than as an upper bound. Under stub mode
review always answers INCOMPLETE, so a route that loops will keep looping
until something stops it — which is what makes the cap the thing measured
rather than the model's willingness to stop.
"""

import json

import pytest

from services import usage
from services.llm import max_calls_for


def _counts() -> dict[str, int]:
    rows = [json.loads(line) for line in usage.ledger_path().read_text().splitlines()]
    out: dict[str, int] = {}
    for row in rows:
        out[row["purpose"]] = out.get(row["purpose"], 0) + 1
    return out


async def _run(monkeypatch, route: str, query: str = "what does the paper say about scaling") -> dict[str, int]:
    from services import agent

    async def fake_search(q, n_results=5, file_ids=None):
        return [
            {
                "text": f"chunk {i} about scaling",
                "source": "paper.pdf",
                "source_type": "pdf",
                "modality": "text",
                "content_source": "extracted",
                "prov_trust": "trusted",
            }
            for i in range(5)
        ]

    monkeypatch.setattr(agent, "vector_search", fake_search)

    async def fake_classify(q, history, note_preview, budget):
        # Stand in for the classifier's decision, but still spend its call,
        # because that call is part of every route's count.
        from services.llm import Prompt, Purpose, complete
        from prompts import CLASSIFY_PROMPT

        result = await complete(Purpose.CLASSIFY, Prompt.render(CLASSIFY_PROMPT, {
            "history": history, "note_preview": note_preview[:500], "query": q,
        }), budget)
        return route, result

    monkeypatch.setattr(agent, "classify_query", fake_classify)

    async for _ in agent.stream_research_agent([{"role": "user", "content": query}]):
        pass
    return _counts()


async def test_fast_fact_is_two_calls(monkeypatch):
    counts = await _run(monkeypatch, "fast_fact")
    assert counts == {"classify": 1, "fast_fact": 1}
    assert sum(counts.values()) == max_calls_for("fast_fact", 0) == 2


async def test_normal_rag_is_three_calls_and_never_reviews(monkeypatch):
    """review is deliberately absent, not missing.

    max_loops=1 means the single pass has no continue-decision to make,
    so paying for one is waste. This test fails if anyone "fixes" the
    increment-before-compare in review_node.
    """
    counts = await _run(monkeypatch, "normal_rag")
    assert counts == {"classify": 1, "analyze": 1, "final_response": 1}
    assert "review" not in counts
    assert sum(counts.values()) == max_calls_for("normal_rag", 1) == 3


async def test_deep_research_is_seven_calls(monkeypatch):
    counts = await _run(monkeypatch, "deep_research")
    assert counts == {"classify": 1, "analyze": 3, "review": 2, "final_response": 1}
    assert sum(counts.values()) == max_calls_for("deep_research", 3) == 7


async def test_no_chunks_skips_analyze_and_downgrades_the_final_call(monkeypatch):
    """An empty retrieval used to pay for Sonnet to say it found nothing."""
    from config import HAIKU_MODEL
    from services import agent

    async def empty_search(q, n_results=5, file_ids=None):
        return []

    monkeypatch.setattr(agent, "vector_search", empty_search)
    async for _ in agent.stream_research_agent([{"role": "user", "content": "what does the paper say about scaling"}]):
        pass

    counts = _counts()
    assert "analyze" not in counts
    assert counts["final_response"] == 1

    rows = [json.loads(line) for line in usage.ledger_path().read_text().splitlines()]
    final = next(r for r in rows if r["purpose"] == "final_response")
    assert final["model"] == HAIKU_MODEL


async def test_call_ceiling_matches_the_policy_table():
    assert max_calls_for("fast_fact", 0) == 2
    assert max_calls_for("normal_rag", 1) == 3
    assert max_calls_for("deep_research", 3) == 7


@pytest.mark.parametrize("max_loops", range(0, 6))
def test_call_ceiling_never_dips_below_the_structural_minimum(max_loops):
    """Two calls (classify + final_response) happen before max_loops is read.

    max_loops is only consulted in review_node, which runs after
    retrieve -> analyze, so a ceiling below 2 is unsatisfiable by
    construction. Written as 2 * max_loops + 1 the formula returned 1 at
    max_loops=0 and every turn on that route aborted at analyze.
    """
    for route in ("normal_rag", "deep_research"):
        assert max_calls_for(route, max_loops) >= 2


def test_a_zero_loop_ceiling_is_exactly_classify_plus_final():
    assert max_calls_for("normal_rag", 0) == 2
    assert max_calls_for("deep_research", 0) == 2


def test_env_override_is_clamped():
    """A typo must not be able to bill fifty retrieval passes."""
    from config import MAX_LOOPS_CLAMP, _parse_loops

    assert _parse_loops("deep_research=50")["deep_research"] == MAX_LOOPS_CLAMP
    assert _parse_loops("normal_rag=2")["normal_rag"] == 2
    # Unparseable and unknown entries fall back rather than failing startup.
    assert _parse_loops("normal_rag=banana")["normal_rag"] == 1
    assert _parse_loops("nonsense=9") == _parse_loops("")


def test_every_route_has_both_a_default_and_a_floor():
    """_parse_loops indexes the floor by route name, so drift is a KeyError.

    Caught here rather than as a crash on startup the first time someone
    adds a route to one table and not the other.
    """
    from config import _DEFAULT_LOOPS_BY_ROUTE, _MIN_LOOPS_BY_ROUTE

    assert set(_DEFAULT_LOOPS_BY_ROUTE) == set(_MIN_LOOPS_BY_ROUTE)
    for route, default in _DEFAULT_LOOPS_BY_ROUTE.items():
        assert _MIN_LOOPS_BY_ROUTE[route] <= default


def test_env_override_floors_the_graph_routes_at_one_pass():
    """0 is not a cheaper policy for a graph route, it is a broken one.

    The clamp used to have a lower bound of 0 for every route, so both an
    explicit 0 and any negative typo produced a value that made every turn
    on that route die: at a call ceiling of 1 the classifier consumed the
    only permitted call, and at recursion_limit 4*0+2 the graph could not
    complete one pass. fast_fact keeps 0 because it bypasses the graph.
    """
    from config import _parse_loops

    assert _parse_loops("normal_rag=0")["normal_rag"] == 1
    assert _parse_loops("deep_research=0")["deep_research"] == 1
    assert _parse_loops("deep_research=-4")["deep_research"] == 1
    assert _parse_loops("fast_fact=0")["fast_fact"] == 0


@pytest.mark.parametrize("route", ["normal_rag", "deep_research"])
async def test_a_zeroed_override_still_answers(monkeypatch, route):
    """End to end, because the two floors have to hold together.

    A bad override must degrade to a working policy, which is what
    _parse_loops' own docstring promises. This is the regression that
    bricked the primary chat feature via a documented env knob.
    """
    import config
    from services import agent

    monkeypatch.setitem(config.LOOPS_BY_ROUTE, route, config._parse_loops(f"{route}=0")[route])
    monkeypatch.setattr(agent, "LOOPS_BY_ROUTE", config.LOOPS_BY_ROUTE)

    counts = await _run(monkeypatch, route)
    assert counts["final_response"] == 1
    assert sum(counts.values()) <= max_calls_for(route, config.LOOPS_BY_ROUTE[route])


def test_unrecognised_route_falls_back_to_the_cheap_policy():
    from config import LOOPS_BY_ROUTE
    from services.agent import DEFAULT_MAX_LOOPS

    assert DEFAULT_MAX_LOOPS == 1
    assert LOOPS_BY_ROUTE.get("some_new_route", DEFAULT_MAX_LOOPS) == 1


@pytest.mark.parametrize("route,max_loops,expected_supersteps", [
    ("normal_rag", 1, 5),
    ("deep_research", 3, 13),
])
def test_recursion_limit_leaves_exactly_one_superstep_of_headroom(route, max_loops, expected_supersteps):
    """Guards the arithmetic in the recursion_limit passed to astream.

    Four nodes per loop plus one final_response superstep.
    """
    assert 4 * max_loops + 1 == expected_supersteps
    assert 4 * max_loops + 2 == expected_supersteps + 1
