"""Which collection a screenshot belongs to, decided locally and cheaply.

PRODUCT_DIRECTION.md rules out a model call per item at ingest, so the
default classifier spends none. It combines three signals that are all
already on the machine:

1. Keywords. Each collection carries lexical hints ("season", "episode",
   "imdb"); the OCR text is scored by how many distinct hints it contains.
   Cheap, precise when it fires, silent when it does not.
2. Embedding similarity. The OCR text and each collection's description
   go through the same bge-small model that embeds the corpus, and the
   cosine similarities are turned into a distribution with a sharp
   softmax. This catches the screenshot that says "Mark and Helly search
   the severed floor" without ever saying "episode".
3. The vision model's vote, when the caption pass has run. It saw the
   picture and the others did not, so it carries the most weight, but not
   enough to override lexical and semantic evidence that both point
   elsewhere.

A combined score below the configured floor, or two collections close to
a tie, files the screenshot in the inbox. Guessing wrong costs the user a
manual move; guessing "inbox" costs them a glance.
"""

import logging
import math
import re
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from config import CLASSIFY_MIN_CONFIDENCE
from services.collections import INBOX_ID, Collection

logger = logging.getLogger(__name__)

Embedder = Callable[[list[str]], Sequence[Sequence[float]]]

KEYWORD_WEIGHT = 0.55
EMBEDDING_WEIGHT = 0.45
VLM_VOTE = 0.5
# Distinct keyword hits at which the lexical score saturates at 1.0.
KEYWORD_SATURATION = 3
# bge-small cosine similarities between unrelated texts sit around 0.5 and
# related ones a few hundredths higher, so the softmax needs a low
# temperature to turn a 0.05 gap into a decision.
SOFTMAX_TEMPERATURE = 0.02
# How much of the runner-up's score is subtracted from the winner's, so
# two collections scoring alike read as uncertainty rather than confidence.
TIE_PENALTY = 0.5
MAX_TEXT_CHARS = 2000


@dataclass(frozen=True)
class Classification:
    collection_id: str
    confidence: float
    method: str
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def filed(self) -> bool:
        return self.collection_id != INBOX_ID

    def to_dict(self) -> dict:
        return {
            "collection": self.collection_id,
            "confidence": round(self.confidence, 4),
            "method": self.method,
            "scores": {k: round(v, 4) for k, v in self.scores.items()},
        }


def _keyword_matches(keyword: str, lowered: str) -> bool:
    keyword = keyword.lower().strip()
    if not keyword:
        return False
    # Symbols and phrases are matched as substrings; single words need a
    # boundary, or "api" fires inside "rapid" and "eth" inside "method".
    # The boundary allows a plural, because the hint says "season" and the
    # screen says "2 Seasons".
    if not re.fullmatch(r"[a-z0-9]+", keyword):
        return keyword in lowered
    return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?:e?s)?(?![a-z0-9])", lowered) is not None


def keyword_hits(text: str, keywords: Sequence[str]) -> int:
    lowered = text.lower()
    return sum(1 for keyword in dict.fromkeys(k.lower() for k in keywords) if _keyword_matches(keyword, lowered))


def keyword_scores(text: str, candidates: Sequence[Collection]) -> dict[str, float]:
    return {
        c.id: min(1.0, keyword_hits(text, c.keywords) / KEYWORD_SATURATION) if c.keywords else 0.0
        for c in candidates
    }


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _softmax(values: Sequence[float], temperature: float) -> list[float]:
    if not values:
        return []
    scaled = [v / temperature for v in values]
    peak = max(scaled)
    weights = [math.exp(v - peak) for v in scaled]
    total = sum(weights)
    return [w / total for w in weights]


_vector_cache: dict[tuple[int, str], Sequence[float]] = {}
_vector_lock = threading.Lock()


def _collection_vectors(candidates: Sequence[Collection], embedder: Embedder) -> list[Sequence[float]]:
    """Embed each collection's description once per embedder."""
    missing = [c for c in candidates if (id(embedder), c.embedding_text) not in _vector_cache]
    if missing:
        vectors = embedder([c.embedding_text for c in missing])
        with _vector_lock:
            for collection, vector in zip(missing, vectors):
                _vector_cache[(id(embedder), collection.embedding_text)] = vector
    return [_vector_cache[(id(embedder), c.embedding_text)] for c in candidates]


def embedding_scores(text: str, candidates: Sequence[Collection], embedder: Embedder) -> dict[str, float]:
    """A distribution over candidates from cosine similarity to their descriptions."""
    if not text.strip() or not candidates:
        return {c.id: 0.0 for c in candidates}
    query = embedder([text[:MAX_TEXT_CHARS]])[0]
    similarities = [_cosine(query, vector) for vector in _collection_vectors(candidates, embedder)]
    return dict(zip((c.id for c in candidates), _softmax(similarities, SOFTMAX_TEMPERATURE)))


def classify(
    text: str,
    collections: Sequence[Collection],
    *,
    embedder: Embedder | None = None,
    vlm_choice: str | None = None,
    min_confidence: float | None = None,
) -> Classification:
    """Pick a collection for the text, or the inbox when nothing is convincing.

    embedder=None runs keywords only, which is what the offline tests use
    and what a machine with no embedding model yet gets. vlm_choice is the
    collection id the vision model named, already validated by the caller.
    """
    floor = CLASSIFY_MIN_CONFIDENCE if min_confidence is None else min_confidence
    candidates = [c for c in collections if c.id != INBOX_ID]
    if not candidates:
        return Classification(INBOX_ID, 0.0, "no-collections")

    lexical = keyword_scores(text, candidates)
    semantic: dict[str, float] = {}
    if embedder is not None and text.strip():
        try:
            semantic = embedding_scores(text, candidates, embedder)
        except Exception as exc:
            logger.warning("Embedding classifier failed, continuing on keywords: %s", exc)

    combined: dict[str, float] = {}
    signals: set[str] = set()
    for collection in candidates:
        score = KEYWORD_WEIGHT * lexical.get(collection.id, 0.0)
        if lexical.get(collection.id, 0.0) > 0:
            signals.add("keywords")
        if semantic:
            score += EMBEDDING_WEIGHT * semantic.get(collection.id, 0.0)
        if vlm_choice and collection.id == vlm_choice:
            score += VLM_VOTE
            signals.add("vlm")
        combined[collection.id] = score
    if semantic and max(semantic.values(), default=0.0) > 1.5 / len(candidates):
        signals.add("embedding")

    ranked = sorted(combined.items(), key=lambda item: item[1], reverse=True)
    best_id, best = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    confidence = max(0.0, min(1.0, best - TIE_PENALTY * runner_up))
    method = "+".join(sorted(signals)) if signals else "fallback"

    if confidence < floor:
        return Classification(INBOX_ID, confidence, method, combined)
    return Classification(best_id, confidence, method, combined)


_default_embedder: Embedder | None = None
_default_lock = threading.Lock()


def default_embedder() -> Embedder:
    """The corpus embedding model, so the classifier and the index agree.

    fastembed loads the ONNX model on the first call and downloads it on a
    fresh machine, so this is resolved lazily and never at import.
    """
    global _default_embedder
    with _default_lock:
        if _default_embedder is None:
            from services.embeddings import get_embedding_function

            function = get_embedding_function()
            _default_embedder = lambda texts: function(list(texts))  # noqa: E731
        return _default_embedder
