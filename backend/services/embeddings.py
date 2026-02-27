"""
Embedding model registry for ablation / comparison.

To switch models, set EMBEDDING_MODEL in .env.local and re-ingest documents.
"""

from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from config import EMBEDDING_MODEL

EMBEDDING_MODELS = {
    "bge-small-en-v1.5": {
        "model_name": "BAAI/bge-small-en-v1.5",
        "dimensions": 384,
        "description": "BAAI BGE small — better retrieval benchmarks than MiniLM",
    },
    "all-MiniLM-L6-v2": {
        "model_name": "all-MiniLM-L6-v2",
        "dimensions": 384,
        "description": "ChromaDB default, fast, decent quality",
    },
}


def get_embedding_function(model_key: str | None = None) -> SentenceTransformerEmbeddingFunction:
    """Return a SentenceTransformerEmbeddingFunction for the given model key."""
    key = model_key or EMBEDDING_MODEL
    cfg = EMBEDDING_MODELS[key]
    return SentenceTransformerEmbeddingFunction(model_name=cfg["model_name"])
