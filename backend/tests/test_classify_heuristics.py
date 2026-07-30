"""The free routing heuristics, and the regression that made them lie.

Route mix is the denominator of every saving claim, so which queries skip
retrieval is a correctness question with a cost flavour.
"""

import pytest

from services.agent import classify_query
from services.llm import Budget

# Cases the free heuristic must catch without spending a call.
_FREE_FAST_FACT = ["hi", "Hello", "  thanks  ", "ok", "thank you", "Thanks!", "yes.", "cool"]

# Cases the free heuristic must catch as deep research.
_FREE_DEEP = [
    "compare these two papers",
    "synthesize what I have read",
    "give me a comprehensive summary",
    "what do all papers say",
]

# Short but substantive questions. These used to be routed to fast_fact by a
# "len(q) < 12" disjunct, which answered them without ever reading the
# user's documents.
_MUST_NOT_SHORTCUT = ["why NaN?", "fix eq 3?", "what is ELBO", "define GAN", "page 4?"]


@pytest.mark.parametrize("query", _FREE_FAST_FACT)
async def test_greetings_route_free(query):
    budget = Budget.interactive()
    route, result = await classify_query(query, "", "", budget)
    assert route == "fast_fact"
    assert budget.calls_made == 0
    # No call, so nothing for the caller to account for.
    assert result is None


@pytest.mark.parametrize("query", _FREE_DEEP)
async def test_deep_keywords_route_free(query):
    budget = Budget.interactive()
    route, result = await classify_query(query, "", "", budget)
    assert route == "deep_research"
    assert budget.calls_made == 0
    assert result is None


@pytest.mark.parametrize("query", _MUST_NOT_SHORTCUT)
async def test_short_substantive_questions_reach_the_classifier(query):
    """They must cost one Haiku call rather than skipping the documents."""
    budget = Budget.interactive()
    route, result = await classify_query(query, "", "", budget)
    assert budget.calls_made == 1
    # The stub classifier answers NORMAL_RAG, so retrieval happens.
    assert route == "normal_rag"
    # Returned rather than dropped, so the caller can bill the turn for it.
    assert result is not None
    assert result.input_tokens > 0


async def test_a_greeting_is_matched_on_the_whole_token_not_a_prefix():
    budget = Budget.interactive()
    route, _ = await classify_query("no clue what this notation means", "", "", budget)
    assert route == "normal_rag"
