"""Vector search over the store, with the ranking fixes screenshots need.

Embedding model is configured in services/embeddings.py (currently
BAAI/bge-small-en-v1.5). Three things are layered over the raw cosine
ranking, all of them from PRODUCT_DIRECTION.md's "keep the bytes, fix the
ranking", and none of them a model call:

1. Chrome demotion. A line that recurs across many screenshots is
   interface furniture ("For You", "Following", a tab bar), whatever
   application it belongs to. Document frequency finds it with no rules,
   and it tunes itself to whichever applications the user actually runs.
   An OCR hit is demoted in proportion to how much of it is such lines.
2. A length penalty. A segment that is a few words long matches almost
   anything nearly as well as anything else, so it yields a little to
   segments with enough text to have meant something.
3. Exact-token recall. Tickers, version strings, package names and paper
   ids ("NVDA", "qwen2.5-vl", "2401.12345") embed badly and match exactly,
   so a query carrying one also runs a substring lookup and the hits join
   the candidate set with a floor score.

Metadata filters compose, so the agent (or a library view) can scope a
search to screenshots, to OCR text, or to a set of items.
"""

import logging
import math
import re
import threading
import time
from collections import Counter, defaultdict
from typing import Any

from services.chroma import get_collection
from services.schema import read_schema_fields

logger = logging.getLogger(__name__)

# Candidates fetched per result returned, so demotion has something to
# demote below the cut rather than only reordering the top five.
OVERFETCH = 3
# A line is chrome when it appears in at least this many screenshots, or
# this fraction of them, whichever is larger.
CHROME_MIN_ITEMS = 3
CHROME_MIN_FRACTION = 0.05
# An OCR hit that is entirely chrome keeps half its score, never zero:
# the query might genuinely be about the interface.
CHROME_MAX_DEMOTION = 0.5
SHORT_SEGMENT_CHARS = 40
SHORT_SEGMENT_PENALTY = 0.85
# What an exact-token hit scores when the vector search did not rank it.
EXACT_MATCH_FLOOR = 0.8
EXACT_MATCH_LIMIT = 20
MAX_EXACT_TOKENS = 5
LINE_FREQUENCY_TTL_S = 120.0

# Tickers ($NVDA, AAPL), versioned names (qwen2.5-vl, gpt-4o), dotted or
# slashed identifiers (fastembed/qdrant, 2401.12345), package-like names.
_IDENTIFIER_RE = re.compile(
    r"^\$?(?:"
    r"[A-Z][A-Z0-9]{2,5}"                   # NVDA, S&P is not matched; AAPL is
    r"|[A-Za-z]*\d[A-Za-z0-9._/-]*"          # 2401.12345, gpt-4o, h100
    r"|[A-Za-z0-9]+[._/-][A-Za-z0-9._/-]+"   # qwen2.5-vl, fastembed/qdrant, torch.compile
    r")$"
)
_TOKEN_STRIP = ".,;:!?()[]{}\"'`<>"


def exact_tokens(query: str) -> list[str]:
    """Tokens in the query that look like identifiers and deserve an exact lookup."""
    found: list[str] = []
    for raw in query.split():
        token = raw.strip(_TOKEN_STRIP)
        if len(token) < 3 or token in found:
            continue
        if _IDENTIFIER_RE.match(token):
            found.append(token)
        if len(found) >= MAX_EXACT_TOKENS:
            break
    return found


def compose_where(
    file_ids: list[str] | None = None,
    source_types: list[str] | None = None,
    modalities: list[str] | None = None,
) -> dict | None:
    """Chroma's where clause for the given scopes, or None for no filter."""
    clauses: list[dict] = []
    if file_ids:
        clauses.append({"file_id": {"$in": list(file_ids)}})
    if source_types:
        clauses.append({"source_type": {"$in": list(source_types)}})
    if modalities:
        clauses.append({"modality": {"$in": list(modalities)}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


# ── Line frequency across screenshots ─────────────────────────────

_frequency_lock = threading.Lock()
_frequency_cache: tuple[float, Counter, int] | None = None


def _normalise_line(line: str) -> str:
    return " ".join(line.split()).casefold()


def _build_line_frequency(collection) -> tuple[Counter, int]:
    """How many distinct screenshots each OCR line appears in.

    A full scan of OCR segments, the same shape as the library's, cached
    because it changes only when a screenshot is indexed.
    """
    holders: dict[str, set[str]] = defaultdict(set)
    items: set[str] = set()
    try:
        result = collection.get(where={"modality": "ocr"}, include=["metadatas"])
    except Exception as exc:
        logger.warning("Line frequency scan failed: %s", exc)
        return Counter(), 0
    for meta in result.get("metadatas") or []:
        file_id = meta.get("file_id", "")
        if not file_id:
            continue
        items.add(file_id)
        for line in (meta.get("original_chunk") or "").splitlines():
            key = _normalise_line(line)
            if key:
                holders[key].add(file_id)
    return Counter({line: len(ids) for line, ids in holders.items()}), len(items)


def line_frequency(collection) -> tuple[Counter, int]:
    global _frequency_cache
    with _frequency_lock:
        now = time.monotonic()
        if _frequency_cache and now - _frequency_cache[0] < LINE_FREQUENCY_TTL_S:
            return _frequency_cache[1], _frequency_cache[2]
        counts, items = _build_line_frequency(collection)
        _frequency_cache = (now, counts, items)
        return counts, items


def invalidate_line_frequency() -> None:
    global _frequency_cache
    with _frequency_lock:
        _frequency_cache = None


def chrome_threshold(item_count: int) -> int:
    return max(CHROME_MIN_ITEMS, math.ceil(CHROME_MIN_FRACTION * item_count))


def chrome_fraction(text: str, counts: Counter, item_count: int) -> float:
    """The share of a segment's lines that recur across the screenshot corpus."""
    lines = [_normalise_line(line) for line in text.splitlines() if line.strip()]
    if not lines or not counts:
        return 0.0
    threshold = chrome_threshold(item_count)
    return sum(1 for line in lines if counts.get(line, 0) >= threshold) / len(lines)


def rerank(hits: list[dict], counts: Counter, item_count: int) -> list[dict]:
    """Apply the chrome and length adjustments, highest adjusted score first."""
    for hit in hits:
        score = hit["score"]
        if hit.get("modality") == "ocr":
            fraction = chrome_fraction(hit["text"], counts, item_count)
            if fraction:
                score *= 1.0 - CHROME_MAX_DEMOTION * fraction
                hit["chrome_fraction"] = round(fraction, 3)
        if len(hit["text"]) < SHORT_SEGMENT_CHARS:
            score *= SHORT_SEGMENT_PENALTY
        hit["score"] = score
    return sorted(hits, key=lambda h: h["score"], reverse=True)


# ── Search ────────────────────────────────────────────────────────


def _hit(record_id: str, doc: str, metadata: dict, score: float, position: int) -> dict[str, Any]:
    """One retrieval hit plus every schema field, so provenance reaches the agent.

    `text` is the citable content: the chunk verbatim as it appears in the
    source. What was embedded is kept separately as `embedded_text`;
    handing the contextualized string to the agent as if it were source
    text is how a system ends up citing a sentence nobody wrote.
    """
    return {
        "id": record_id,
        "text": metadata.get("original_chunk") or doc,
        "embedded_text": doc,
        "source": metadata.get("filename", "unknown"),
        "score": score,
        "chunk_index": metadata.get("chunk_index", position),
        "file_id": metadata.get("file_id", ""),
        "title": metadata.get("title", ""),
        "collection": metadata.get("collection", ""),
        "source_app": metadata.get("source_app", ""),
        "ocr_engine": metadata.get("ocr_engine", ""),
        **read_schema_fields(metadata),
    }


async def vector_search(
    query: str,
    n_results: int = 5,
    file_ids: list[str] | None = None,
    *,
    source_types: list[str] | None = None,
    modalities: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search the store for the most relevant segments.

    Args:
        query: The search query text.
        n_results: Maximum number of results to return.
        file_ids: Restrict to these Items.
        source_types: Restrict to these source types ("screenshot", "pdf", ...).
        modalities: Restrict to these segment modalities ("ocr", "caption", ...).
    """
    collection = get_collection()
    total = collection.count()
    if total == 0:
        return []

    where = compose_where(file_ids, source_types, modalities)
    fetch = min(max(n_results, 1) * OVERFETCH, total)
    results = collection.query(query_texts=[query], n_results=fetch, where=where)

    hits: dict[str, dict] = {}
    ids = results.get("ids") or [[]]
    documents = results.get("documents") or [[]]
    metadatas = results.get("metadatas") or [[]]
    distances = results.get("distances") or [[]]
    for position, doc in enumerate(documents[0] if documents else []):
        metadata = metadatas[0][position] if metadatas and metadatas[0] else {}
        distance = distances[0][position] if distances and distances[0] else 0.0
        record_id = ids[0][position] if ids and ids[0] else f"{metadata.get('file_id', '')}-{position}"
        hits[record_id] = _hit(record_id, doc, metadata, 1 - distance, position)

    for token in exact_tokens(query):
        try:
            exact = collection.get(
                where=where,
                where_document={"$contains": token},
                include=["metadatas", "documents"],
                limit=EXACT_MATCH_LIMIT,
            )
        except Exception as exc:
            logger.debug("Exact lookup for %r failed: %s", token, exc)
            continue
        for position, record_id in enumerate(exact.get("ids") or []):
            metadata = (exact.get("metadatas") or [{}])[position] or {}
            doc = (exact.get("documents") or [""])[position] or ""
            if record_id in hits:
                hits[record_id]["score"] = max(hits[record_id]["score"], EXACT_MATCH_FLOOR)
            else:
                hits[record_id] = _hit(record_id, doc, metadata, EXACT_MATCH_FLOOR, position)
            hits[record_id]["matched_token"] = token

    counts, item_count = line_frequency(collection)
    return rerank(list(hits.values()), counts, item_count)[:n_results]
