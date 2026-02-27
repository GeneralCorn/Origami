"""
Vector search over contextualized chunks stored in ChromaDB.

Embedding model is configured in services/embeddings.py (currently BAAI/bge-small-en-v1.5).
"""

from ipaddress import collapse_addresses
from typing import Any

from services.chroma import get_collection


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

    Returns a list of dicts with:
        {"text": str, "source": str, "score": float, "chunk_index": int}
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
                "text": doc,
                "source": metadata.get("filename", "unknown"),
                "score": 1 - distance,  # Convert cosine distance to similarity
                "chunk_index": metadata.get("chunk_index", i),
                "file_id": metadata.get("file_id", ""),
            })

    return chunks
