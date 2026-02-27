"""Shared ChromaDB client + document-level helpers.

All document metadata (tags, content_hash) lives on the chunk metadata
in ChromaDB — there is no separate registry file.
"""

import hashlib
import json
from pathlib import Path

import chromadb

from config import CHROMA_DIR, CHROMA_COLLECTION
from services.embeddings import get_embedding_function

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_TAGS_FILE = _BACKEND_DIR / "saved_tags.json"

_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
_ef = get_embedding_function()


def get_collection() -> chromadb.Collection:
    """Get or create the ChromaDB collection with cosine similarity."""
    return _client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
        embedding_function=_ef,
    )


# -- Document-level helpers (query across chunks) --------------------------


def hash_bytes(data: bytes) -> str:
    """Return a SHA-256 hex digest for raw file bytes."""
    return hashlib.sha256(data).hexdigest()


def find_by_hash(content_hash: str) -> dict | None:
    """Return the first document matching the hash, or None.

    Returns {"file_id": str, "filename": str} or None.
    """
    col = get_collection()
    if col.count() == 0:
        return None
    results = col.get(where={"content_hash": content_hash}, include=["metadatas"], limit=1)
    if results["ids"]:
        meta = results["metadatas"][0]
        return {"file_id": meta["file_id"], "filename": meta["filename"]}
    return None


def _load_saved_tags() -> list[str]:
    """Load user-saved tags from disk."""
    if not _TAGS_FILE.exists():
        return []
    try:
        return json.loads(_TAGS_FILE.read_text())
    except Exception:
        return []


def save_tag(tag: str) -> None:
    """Persist a user-created tag so it appears in future uploads."""
    tags = set(_load_saved_tags())
    tags.add(tag)
    _TAGS_FILE.write_text(json.dumps(sorted(tags)))


def list_all_tags() -> list[str]:
    """Collect all unique tags across all chunks + saved tags, sorted."""
    col = get_collection()
    tags: set[str] = set(_load_saved_tags())
    if col.count() > 0:
        results = col.get(include=["metadatas"])
        for meta in results["metadatas"] or []:
            tags.update(meta.get("tags", []))
    return sorted(tags)


def get_document_meta(file_id: str) -> dict | None:
    """Look up metadata for a document by file_id (reads first chunk)."""
    col = get_collection()
    if col.count() == 0:
        return None
    results = col.get(where={"file_id": file_id}, include=["metadatas"], limit=1)
    if results["ids"]:
        return results["metadatas"][0]
    return None


def set_tags(file_id: str, tags: list[str]) -> bool:
    """Update tags on all chunks belonging to a document."""
    col = get_collection()
    results = col.get(where={"file_id": file_id}, include=["metadatas"])
    if not results["ids"]:
        return False
    updated_metadatas = []
    for meta in results["metadatas"]:
        meta["tags"] = tags
        updated_metadatas.append(meta)
    col.update(ids=results["ids"], metadatas=updated_metadatas)
    return True


def set_title(file_id: str, title: str) -> bool:
    """Update title on all chunks belonging to a document."""
    col = get_collection()
    results = col.get(where={"file_id": file_id}, include=["metadatas"])
    if not results["ids"]:
        return False
    for meta in results["metadatas"]:
        meta["title"] = title
    col.update(ids=results["ids"], metadatas=results["metadatas"])
    return True


def delete_chunks(file_id: str) -> int:
    """Delete all ChromaDB chunks for a file_id. Returns count deleted."""
    col = get_collection()
    results = col.get(where={"file_id": file_id}, include=[])
    chunk_ids = results["ids"]
    if chunk_ids:
        col.delete(ids=chunk_ids)
    return len(chunk_ids)


def resolve_tag(tag: str) -> list[str]:
    """Return all unique file_ids that have the given tag."""
    col = get_collection()
    if col.count() == 0:
        return []
    results = col.get(where={"tags": {"$contains": tag}}, include=["metadatas"])
    seen: set[str] = set()
    file_ids: list[str] = []
    for meta in results["metadatas"] or []:
        fid = meta.get("file_id", "")
        if fid and fid not in seen:
            seen.add(fid)
            file_ids.append(fid)
    return file_ids
