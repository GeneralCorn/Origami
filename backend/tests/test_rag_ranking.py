"""The ranking layer over cosine similarity: chrome demotion, length, exact tokens, filters.

Chroma is faked with a collection that answers query() and get() from
lists, so what is exercised is the merge and the reordering, not the
vector store.
"""

from collections import Counter

import pytest

import services.rag as rag
from services.rag import (
    chrome_fraction,
    compose_where,
    exact_tokens,
    rerank,
    vector_search,
)


class _FakeChroma:
    """Enough of Collection for vector_search: ranked query hits and exact gets."""

    def __init__(self, ranked, records=None):
        self.ranked = ranked            # list of (id, doc, meta, distance)
        self.records = records or []    # list of (id, doc, meta), for get()
        self.queries = []
        self.gets = []

    def count(self):
        return max(len(self.ranked), len(self.records), 1)

    def query(self, query_texts, n_results, where=None):
        self.queries.append({"n_results": n_results, "where": where})
        top = self.ranked[:n_results]
        return {
            "ids": [[r[0] for r in top]],
            "documents": [[r[1] for r in top]],
            "metadatas": [[r[2] for r in top]],
            "distances": [[r[3] for r in top]],
        }

    def get(self, where=None, where_document=None, include=None, limit=None):
        self.gets.append({"where": where, "where_document": where_document})
        token = (where_document or {}).get("$contains")
        if include == ["metadatas"] and (where or {}).get("modality") == "ocr":
            matched = [r for r in self.records if r[2].get("modality") == "ocr"]
        else:
            matched = [r for r in self.records if token is None or token in r[1]]
        matched = matched[: limit or None]
        return {"ids": [r[0] for r in matched], "documents": [r[1] for r in matched], "metadatas": [r[2] for r in matched]}


def _meta(file_id, text, modality="ocr", **over):
    base = {
        "file_id": file_id, "filename": file_id, "original_chunk": text, "modality": modality,
        "source_type": "screenshot", "content_source": "extracted", "prov_trust": "untrusted",
        "title": f"Title of {file_id}", "collection": "shows-to-watch", "ocr_engine": "rapidocr",
    }
    base.update(over)
    return base


@pytest.fixture(autouse=True)
def _fresh_cache():
    rag.invalidate_line_frequency()
    yield
    rag.invalidate_line_frequency()


# ── Pieces ────────────────────────────────────────────────────────


def test_exact_tokens_pick_identifiers_not_words():
    assert exact_tokens("what did I save about NVDA and qwen2.5-vl?") == ["NVDA", "qwen2.5-vl"]
    assert exact_tokens("the paper 2401.12345 on arxiv") == ["2401.12345"]
    assert exact_tokens("$AAPL earnings") == ["$AAPL"]
    assert exact_tokens("What is the ELBO in a VAE") == ["ELBO", "VAE"]
    assert exact_tokens("show me my recipes") == []
    assert exact_tokens("OK so US news") == []  # two-letter caps are words, not tickers


def test_exact_tokens_are_deduplicated_and_capped():
    assert exact_tokens("NVDA NVDA AMD TSLA MSFT GOOG AMZN") == ["NVDA", "AMD", "TSLA", "MSFT", "GOOG"]


def test_compose_where_is_none_one_clause_or_an_and():
    assert compose_where() is None
    assert compose_where(file_ids=["a"]) == {"file_id": {"$in": ["a"]}}
    assert compose_where(source_types=["screenshot"], modalities=["ocr"]) == {
        "$and": [{"source_type": {"$in": ["screenshot"]}}, {"modality": {"$in": ["ocr"]}}]
    }


def test_chrome_fraction_counts_lines_shared_across_screenshots():
    counts = Counter({"for you": 40, "following": 40, "severance season 2": 1})
    assert chrome_fraction("For You\nFollowing\nSeverance Season 2", counts, 100) == pytest.approx(2 / 3)
    assert chrome_fraction("Severance Season 2", counts, 100) == 0.0
    assert chrome_fraction("", counts, 100) == 0.0
    # Below the item floor nothing is chrome yet: two screenshots agreeing is coincidence.
    assert chrome_fraction("For You", Counter({"for you": 2}), 10) == 0.0


def test_rerank_demotes_chrome_and_short_segments_but_not_captions():
    counts = Counter({"for you": 10, "following": 10})
    hits = [
        {"text": "For You\nFollowing\nHome", "modality": "ocr", "score": 0.80},
        {"text": "Severance returns for a second season on Netflix this January", "modality": "ocr", "score": 0.78},
        {"text": "For You", "modality": "caption", "score": 0.79},
    ]

    ranked = rerank(hits, counts, 50)

    assert [h["text"][:9] for h in ranked] == ["Severance", "For You", "For You\nF"]
    chrome = ranked[-1]
    assert chrome["chrome_fraction"] == pytest.approx(0.667)
    assert chrome["score"] == pytest.approx(0.80 * (1 - 0.5 * 2 / 3) * 0.85)
    # The caption is short, so it pays the length penalty, but never the chrome one.
    assert ranked[1]["score"] == pytest.approx(0.79 * 0.85)
    assert "chrome_fraction" not in ranked[1]


# ── Search ────────────────────────────────────────────────────────


async def test_search_overfetches_reranks_and_cuts(monkeypatch):
    chrome = "For You\nFollowing\nHome\nSearch"
    content = "Severance returns for a second season on Netflix this January"
    ranked = [
        ("shot1-1", chrome, _meta("shot1", chrome), 0.20),
        ("shot2-1", content, _meta("shot2", content), 0.22),
        ("shot3-1", "x", _meta("shot3", "x"), 0.60),
    ]
    records = [(f"s{i}-1", chrome, _meta(f"s{i}", chrome)) for i in range(6)] + [("shot2-1", content, _meta("shot2", content))]
    fake = _FakeChroma(ranked, records)
    monkeypatch.setattr(rag, "get_collection", lambda: fake)

    hits = await vector_search("severance second season", n_results=2)

    assert fake.queries[0]["n_results"] == 6
    assert [h["file_id"] for h in hits] == ["shot2", "shot1"]
    assert hits[0]["title"] == "Title of shot2"
    assert hits[0]["collection"] == "shows-to-watch"
    assert hits[0]["ocr_engine"] == "rapidocr"
    assert hits[0]["raw_ref"] == ""  # v1-shaped metadata falls back to the schema default
    assert hits[1]["chrome_fraction"] == 1.0


async def test_exact_tokens_join_the_candidates_with_a_floor(monkeypatch):
    ranked = [("shot1-1", "Nvidia earnings preview", _meta("shot1", "Nvidia earnings preview"), 0.30)]
    records = [
        ("shot1-1", "Nvidia earnings preview", _meta("shot1", "Nvidia earnings preview")),
        ("shot9-1", "NVDA $875.40 +3.2% NASDAQ market cap 2.1T after hours", _meta("shot9", "NVDA $875.40 +3.2% NASDAQ market cap 2.1T after hours")),
    ]
    fake = _FakeChroma(ranked, records)
    monkeypatch.setattr(rag, "get_collection", lambda: fake)

    hits = await vector_search("what did NVDA do", n_results=5, source_types=["screenshot"])

    exact = next(h for h in hits if h["file_id"] == "shot9")
    assert exact["matched_token"] == "NVDA"
    assert exact["score"] == pytest.approx(rag.EXACT_MATCH_FLOOR)
    assert hits[0]["file_id"] == "shot9"
    assert fake.gets[0]["where"] == {"source_type": {"$in": ["screenshot"]}}
    assert fake.gets[0]["where_document"] == {"$contains": "NVDA"}


async def test_an_empty_store_returns_nothing(monkeypatch):
    class Empty:
        def count(self):
            return 0

    monkeypatch.setattr(rag, "get_collection", lambda: Empty())
    assert await vector_search("anything") == []


async def test_filters_reach_chroma(monkeypatch):
    fake = _FakeChroma([("a-0", "t", _meta("a", "t"), 0.1)])
    monkeypatch.setattr(rag, "get_collection", lambda: fake)

    await vector_search("q", file_ids=["a"], modalities=["ocr", "caption"])

    assert fake.queries[0]["where"] == {"$and": [{"file_id": {"$in": ["a"]}}, {"modality": {"$in": ["ocr", "caption"]}}]}


def test_line_frequency_is_cached_until_invalidated(monkeypatch):
    fake = _FakeChroma([], [("s1-1", "For You", _meta("s1", "For You")), ("s2-1", "For You", _meta("s2", "For You"))])

    counts, items = rag.line_frequency(fake)
    rag.line_frequency(fake)

    assert counts == Counter({"for you": 2})
    assert items == 2
    assert len(fake.gets) == 1
    rag.invalidate_line_frequency()
    rag.line_frequency(fake)
    assert len(fake.gets) == 2
