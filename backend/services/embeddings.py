"""
Embedding model registry for ablation / comparison.

To switch models, change ACTIVE_MODEL and re-ingest documents.
To add a new model, add an entry to EMBEDDING_MODELS.
"""

from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

# ── Available models ─────────────────────────────────────────────
EMBEDDING_MODELS = {
    # "all-MiniLM-L6-v2": {
    #     "model_name": "all-MiniLM-L6-v2",
    #     "dimensions": 384,
    #     "description": "ChromaDB default, fast, decent quality",
    # },
    "bge-small-en-v1.5": {
        "model_name": "BAAI/bge-small-en-v1.5",
        "dimensions": 384,
        "description": "BAAI BGE small — better retrieval benchmarks than MiniLM",
    },
}

# ── Active model ─────────────────────────────────────────────────
ACTIVE_MODEL = "bge-small-en-v1.5"


def get_embedding_function(model_key: str | None = None) -> SentenceTransformerEmbeddingFunction:
    """Return a SentenceTransformerEmbeddingFunction for the given model key."""
    key = model_key or ACTIVE_MODEL
    cfg = EMBEDDING_MODELS[key]
    return SentenceTransformerEmbeddingFunction(model_name=cfg["model_name"])
