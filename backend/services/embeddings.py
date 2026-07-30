"""
Embedding model registry for ablation / comparison.

Backed by fastembed (quantized ONNX, no Torch dependency). To switch
models, set EMBEDDING_MODEL in .env.local and re-ingest documents.
"""

from chromadb import Documents, EmbeddingFunction, Embeddings

from config import EMBEDDING_MODEL, MODELS_DIR

EMBEDDING_BACKEND = "fastembed"

EMBEDDING_MODELS = {
    "bge-small-en-v1.5": {
        "model_name": "BAAI/bge-small-en-v1.5",
        "dimensions": 384,
        "description": "BAAI BGE small — better retrieval benchmarks than MiniLM",
    },
    "all-MiniLM-L6-v2": {
        "model_name": "sentence-transformers/all-MiniLM-L6-v2",
        "dimensions": 384,
        "description": "Fast baseline, decent quality",
    },
}


class FastembedEmbeddingFunction(EmbeddingFunction[Documents]):
    """Chroma embedding function backed by fastembed.

    The ONNX model is loaded lazily on first use so importing the backend
    stays cheap and no model download happens at process startup.
    """

    def __init__(self, model_name: str):
        self._model_name = model_name
        self._model = None

    def __call__(self, input: Documents) -> Embeddings:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(
                model_name=self._model_name,
                cache_dir=str(MODELS_DIR),
            )
        return [vector.tolist() for vector in self._model.embed(list(input))]


def get_embedding_function(model_key: str | None = None) -> FastembedEmbeddingFunction:
    """Return a fastembed-backed embedding function for the given model key."""
    key = model_key or EMBEDDING_MODEL
    cfg = EMBEDDING_MODELS[key]
    return FastembedEmbeddingFunction(model_name=cfg["model_name"])


def current_embedding_model_id(model_key: str | None = None) -> str:
    """Identifier recorded on every segment this process embeds.

    The backend prefix is load-bearing: fastembed ships quantized ONNX, so
    its vectors are not interchangeable with the sentence-transformers
    build of the same checkpoint (ARCHITECTURE_V2 section 5).
    """
    key = model_key or EMBEDDING_MODEL
    return f"{EMBEDDING_BACKEND}:{EMBEDDING_MODELS[key]['model_name']}"
