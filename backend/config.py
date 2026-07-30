"""Centralized configuration loaded from environment variables.

All tunables live here. Copy .env.example → .env.local and adjust.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent

# ── Data root ────────────────────────────────────────────────────
# Every directory the backend writes lives under DATA_DIR. Unset,
# it is the backend folder itself (the historical dev layout). A
# packaged desktop app sets ORIGAMI_DATA_DIR to a user-writable
# location because it cannot write next to its own binary.
DATA_DIR: Path = Path(os.getenv("ORIGAMI_DATA_DIR", str(_BACKEND_DIR)))

SCREENSHOTS_DIR: Path = DATA_DIR / "screenshots"
DIGESTS_DIR: Path = DATA_DIR / "digests"
UPLOADS_DIR: Path = DATA_DIR / "uploads"
PDFS_DIR: Path = DATA_DIR / "pdfs"
CHATS_DIR: Path = DATA_DIR / "chats"
NOTES_DIR: Path = DATA_DIR / "notes"
SNIPPETS_DIR: Path = DATA_DIR / "snippets"
CHROMA_DIR: Path = Path(os.getenv("CHROMA_DIR", str(DATA_DIR / "chroma_data")))
MODELS_DIR: Path = DATA_DIR / "models"
USAGE_DIR: Path = DATA_DIR / "usage"
SAVED_TAGS_FILE: Path = DATA_DIR / "saved_tags.json"

for _dir in (
    SCREENSHOTS_DIR, DIGESTS_DIR, UPLOADS_DIR, PDFS_DIR,
    CHATS_DIR, NOTES_DIR, SNIPPETS_DIR, CHROMA_DIR, MODELS_DIR, USAGE_DIR,
):
    _dir.mkdir(parents=True, exist_ok=True)

# ── Server ───────────────────────────────────────────────────────
HOST: str = os.getenv("ORIGAMI_HOST", "127.0.0.1")
PORT: int = int(os.getenv("ORIGAMI_PORT", "8000"))

# Optional shared secret. When set, every request must carry it as a
# Bearer token (or ?token= for resources loaded via src attributes).
# Unset, no auth is enforced and the plain dev workflow is unchanged.
AUTH_TOKEN: str = os.getenv("ORIGAMI_AUTH_TOKEN", "")

# ── Anthropic ────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
HAIKU_MODEL: str = os.getenv("HAIKU_MODEL", "claude-haiku-4-5-20251001")
SONNET_MODEL: str = os.getenv("SONNET_MODEL", "claude-sonnet-4-6")

# ── Ollama (for VLMs) ───────────────────────────────────────────
OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")
OLLAMA_VLM_MODEL: str = os.getenv("OLLAMA_VLM_MODEL", "qwen2.5-vl:7b")
OLLAMA_TIMEOUT: float = float(os.getenv("OLLAMA_TIMEOUT", "120"))

# ── Embeddings ───────────────────────────────────────────────────
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "bge-small-en-v1.5")

# ── ChromaDB ─────────────────────────────────────────────────────
CHROMA_COLLECTION: str = os.getenv("CHROMA_COLLECTION", "documents")

# ── Frontend / CORS ──────────────────────────────────────────────
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
EXTRA_ALLOWED_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.getenv("ORIGAMI_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

# ── Ingestion ────────────────────────────────────────────────────
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "300"))

# ARCHITECTURE_V2 section 4 gates contextualisation on segment length. A
# segment shorter than half a chunk is either a document's tail or a short
# standalone capture; in both cases a full Haiku call buys a blurb the
# reader did not need.
CONTEXTUALIZE_MIN_CHARS: int = int(os.getenv("ORIGAMI_CONTEXTUALIZE_MIN_CHARS", "600"))

# How much of the source document is prepended to every contextualization
# request. That prefix is byte-identical across a document's chunks, so it
# is sent as a cacheable block; Anthropic's minimum cacheable prefix for
# Haiku 4.5 is 4,096 tokens, and at the ~4 chars/token of English prose a
# 12,000-char prefix lands near 3,000 tokens — below the floor, where the
# cache silently never engages and no error is returned. 24,000 chars is
# ~6,000 tokens, which clears the floor even on dense notation that
# tokenizes closer to 3 chars/token.
CONTEXT_DOC_CHARS: int = int(os.getenv("CONTEXT_DOC_CHARS", "24000"))

# ── Cost controls ────────────────────────────────────────────────
MAX_LOOPS_CLAMP: int = 5

_DEFAULT_LOOPS_BY_ROUTE: dict[str, int] = {
    "fast_fact": 0,
    "normal_rag": 1,
    "deep_research": 3,
}

# Per-route lower bound. fast_fact bypasses the graph entirely, so its loop
# count is never read and 0 is the honest value. Every other route runs
# retrieve -> analyze -> save_notes -> review before max_loops is consulted
# at all, so 0 there is not a cheaper policy but a broken one: it sets the
# call ceiling below the calls the pipeline has already made and drops the
# graph's recursion_limit below one pass, and the turn dies with
# CallBudgetExceeded or GraphRecursionError on every query, forever.
_MIN_LOOPS_BY_ROUTE: dict[str, int] = {
    "fast_fact": 0,
    "normal_rag": 1,
    "deep_research": 1,
}


def _parse_loops(raw: str) -> dict[str, int]:
    """Parse "fast_fact=0,normal_rag=1,deep_research=3" over the defaults.

    Every value is clamped to _MIN_LOOPS_BY_ROUTE..MAX_LOOPS_CLAMP because
    this is the only knob that multiplies the per-turn call count: an
    unclamped typo would bill an unbounded number of retrieval passes, and
    a value below the floor would break the route outright. Unparseable
    entries and unknown route names are dropped rather than raising, so a
    bad override degrades to the default policy instead of failing startup.
    The clamp is logged, so an override that did not take effect is
    diagnosable rather than silent.
    """
    loops = dict(_DEFAULT_LOOPS_BY_ROUTE)
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        name, _, value = entry.partition("=")
        name = name.strip()
        if name not in loops:
            continue
        try:
            requested = int(value.strip())
        except ValueError:
            continue
        clamped = max(_MIN_LOOPS_BY_ROUTE[name], min(MAX_LOOPS_CLAMP, requested))
        if clamped != requested:
            logger.warning(
                "ORIGAMI_LOOPS_BY_ROUTE: %s=%d is outside %d..%d, using %d",
                name, requested, _MIN_LOOPS_BY_ROUTE[name], MAX_LOOPS_CLAMP, clamped,
            )
        loops[name] = clamped
    return loops


LOOPS_BY_ROUTE: dict[str, int] = _parse_loops(os.getenv("ORIGAMI_LOOPS_BY_ROUTE", ""))

# Route the normal_rag final synthesis to Haiku instead of Sonnet. Off by
# default: the node must emit a single valid JSON object containing LaTeX,
# and there is no way to A/B the resulting answer quality without a key.
CHEAP_FINAL: bool = os.getenv("ORIGAMI_CHEAP_FINAL", "") not in ("", "0", "false", "False")

# Answer every model call from a local stub and dump the would-be request
# to disk instead of calling the API. Lets the whole pipeline, prompt
# assembly, and cache-block structure be exercised with no API key.
MODEL_STUB: bool = os.getenv("ORIGAMI_MODEL_STUB", "") not in ("", "0", "false", "False")
