"""The local classifier: keywords, embedding softmax, the VLM vote, the inbox."""

import pytest

from services.classify_screenshot import (
    EMBEDDING_WEIGHT,
    KEYWORD_WEIGHT,
    VLM_VOTE,
    Classification,
    classify,
    keyword_hits,
    keyword_scores,
)
from services.collections import DEFAULT_COLLECTIONS, INBOX_ID, Collection

SHOWS = next(c for c in DEFAULT_COLLECTIONS if c.id == "shows-to-watch")
TECH = next(c for c in DEFAULT_COLLECTIONS if c.id == "tech-to-try")
MARKETS = next(c for c in DEFAULT_COLLECTIONS if c.id == "markets-to-watch")
PAPERS = next(c for c in DEFAULT_COLLECTIONS if c.id == "papers-to-read")
INBOX = next(c for c in DEFAULT_COLLECTIONS if c.id == INBOX_ID)
FOUR = [SHOWS, TECH, MARKETS, PAPERS, INBOX]

NETFLIX = "9:41\nNetflix\nSeverance\nSeason 2, Episode 3\nWho Is Alive?\nIMDb 8.7 2025 TV-MA\nPlay Download My List"
BROKERAGE = "NVDA $875.40 +3.2%\nNASDAQ\nMarket cap 2.1T\nEarnings Aug 28\nShares 24.6B"
ARXIV = "arxiv.org/abs/2401.12345\nAttention Is All You Need\nAbstract\nWe propose a new architecture"
PLAIN = "Mark and Helly search the severed floor."


def _one_hot_embedder(winner: int, total: int = 4, sharp: bool = True):
    """Collections map to unit axes; the text lands on axis `winner`."""
    def embed(texts):
        out = []
        for text in texts:
            if text.startswith(("Shows to watch.", "Tech to try.", "Markets to watch.", "Papers to read.")):
                axis = ["Shows", "Tech", "Markets", "Papers"].index(text.split()[0])
                out.append([1.0 if i == axis else 0.0 for i in range(total)])
            else:
                vec = [0.5] * total
                if sharp:
                    vec[winner] = 0.6
                out.append(vec)
        return out
    return embed


# ── Keywords ──────────────────────────────────────────────────────


def test_keyword_hits_count_distinct_hints_with_word_boundaries():
    assert keyword_hits("Season 2, Episode 3 on Netflix, season finale", ["season", "episode", "netflix"]) == 3
    # "api" must not fire inside "rapid", nor "eth" inside "method".
    assert keyword_hits("a rapid method", ["api", "eth"]) == 0
    assert keyword_hits("NVDA +3.2%", ["%"]) == 1
    assert keyword_hits("pip install fastembed", ["pip install"]) == 1
    # Hints are written in the singular; the screen says "2 Seasons".
    assert keyword_hits("2 Seasons, 28 Episodes, 4,120 citations", ["season", "episode", "citation"]) == 3
    assert keyword_hits("seasoning the pan", ["season"]) == 0


def test_keyword_scores_saturate_at_three_hits():
    scores = keyword_scores(NETFLIX, [SHOWS, TECH])
    assert scores["shows-to-watch"] == 1.0
    assert scores["tech-to-try"] == 0.0


# ── Classification ────────────────────────────────────────────────


def test_lexical_evidence_alone_files_a_clear_screenshot():
    result = classify(NETFLIX, FOUR)

    assert result.collection_id == "shows-to-watch"
    assert result.method == "keywords"
    assert result.confidence == pytest.approx(KEYWORD_WEIGHT)
    assert result.filed


def test_brokerage_and_arxiv_screens_land_where_they_should():
    assert classify(BROKERAGE, FOUR).collection_id == "markets-to-watch"
    assert classify(ARXIV, FOUR).collection_id == "papers-to-read"


def test_one_stray_keyword_is_not_enough():
    """A single hint scores 0.55/3, under the floor: the inbox, not a guess."""
    result = classify("we watched the model train", FOUR)

    assert result.collection_id == INBOX_ID
    assert not result.filed
    assert result.confidence < 0.35


def test_a_decisive_embedding_files_without_any_keyword():
    result = classify(PLAIN, FOUR, embedder=_one_hot_embedder(winner=0))

    assert result.collection_id == "shows-to-watch"
    assert "embedding" in result.method
    assert result.confidence == pytest.approx(EMBEDDING_WEIGHT, abs=0.02)


def test_an_indecisive_embedding_stays_in_the_inbox():
    result = classify(PLAIN, FOUR, embedder=_one_hot_embedder(winner=0, sharp=False))

    assert result.collection_id == INBOX_ID
    assert "embedding" not in result.method


def test_the_vlm_vote_files_on_its_own():
    result = classify("", FOUR, vlm_choice="papers-to-read")

    assert result.collection_id == "papers-to-read"
    assert result.method == "vlm"
    assert result.confidence == pytest.approx(VLM_VOTE)


def test_lexical_and_semantic_agreement_outranks_a_lone_vlm_vote():
    result = classify(NETFLIX, FOUR, embedder=_one_hot_embedder(winner=0), vlm_choice="tech-to-try")

    assert result.collection_id == "shows-to-watch"
    assert result.scores["shows-to-watch"] > result.scores["tech-to-try"]


def test_an_unknown_vlm_choice_is_ignored():
    result = classify("", FOUR, vlm_choice="cryptozoology")
    assert result.collection_id == INBOX_ID
    assert result.method == "fallback"


def test_two_collections_scoring_alike_read_as_uncertainty():
    both = Collection("a", "A", "a", keywords=("alpha", "beta", "gamma"))
    other = Collection("b", "B", "b", keywords=("alpha", "beta", "gamma"))

    result = classify("alpha beta gamma", [both, other, INBOX])

    assert result.collection_id == INBOX_ID
    assert result.confidence == pytest.approx(KEYWORD_WEIGHT * 0.5)


def test_no_collections_but_the_inbox_is_still_an_answer():
    result = classify(NETFLIX, [INBOX])
    assert result == Classification(INBOX_ID, 0.0, "no-collections")


def test_the_floor_is_adjustable_per_call():
    assert classify("we watched the model train", FOUR, min_confidence=0.1).filed


def test_an_embedder_that_raises_degrades_to_keywords():
    def broken(texts):
        raise RuntimeError("no model on this machine")

    result = classify(NETFLIX, FOUR, embedder=broken)

    assert result.collection_id == "shows-to-watch"
    assert result.method == "keywords"


def test_to_dict_rounds_and_names_the_collection():
    data = classify(NETFLIX, FOUR).to_dict()
    assert data["collection"] == "shows-to-watch"
    assert set(data) == {"collection", "confidence", "method", "scores"}
