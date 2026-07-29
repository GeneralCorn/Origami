"""
Vector search over contextualized chunks stored in ChromaDB.

Embedding model is configured in services/embeddings.py (currently BAAI/bge-small-en-v1.5).
"""

from typing import Any

from services.chroma import get_collection
from services.schema import read_schema_fields


async def vector_search(
    query: str,
    n_results: int = 5,
    file_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Search ChromaDB for the most relevant contextualized chunks.

    Args:
        query: The search query text.
        n_results: Maximum number of results to return.
        file_ids: Optional list of file_ids to restrict the search to.

    Returns a list of dicts carrying the retrieval hit plus every schema
    field from services.schema, so provenance reaches the agent's context
    (ARCHITECTURE_V2 section 6) and the section 3 taint rule has something
    to read.

    `text` is the citable content: the chunk verbatim as it appears in the
    source. What was embedded is the chunk with a Haiku-written context
    blurb prepended, kept separately as `embedded_text`. Handing the
    contextualized string to the agent as if it were source text is how a
    system ends up citing a sentence nobody wrote.
    """
    collection = get_collection()
    if collection.count() == 0:
        return []

    where = {"file_id": {"$in": file_ids}} if file_ids else None

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, collection.count()),
        where=where,
    )

    chunks = []
    if results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else 0.0

            chunks.append({
                "text": metadata.get("original_chunk") or doc,
                "embedded_text": doc,
                "source": metadata.get("filename", "unknown"),
                "score": 1 - distance,  # Convert cosine distance to similarity
                "chunk_index": metadata.get("chunk_index", i),
                "file_id": metadata.get("file_id", ""),
                **read_schema_fields(metadata),
            })

    return chunks
