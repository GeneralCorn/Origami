"""Shared ChromaDB client + document-level helpers.

All document metadata (tags, content_hash) lives on the chunk metadata
in ChromaDB — there is no separate registry file.
"""

import hashlib
import json
import logging
import threading

import chromadb

from config import CHROMA_DIR, CHROMA_COLLECTION, SAVED_TAGS_FILE
from services.embeddings import get_embedding_function
from services.migrate import repair_embedding_function

logger = logging.getLogger(__name__)

_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
_ef = get_embedding_function()

_repair_lock = threading.Lock()
_repaired = False


def _repair_once() -> None:
    """Run the embedding-function repair before the first collection handle.

    Deliberately here rather than at module import. chromadb reads the
    collection's persisted embedding-function config once and caches it on
    the handle, so a store written before the fastembed swap has to be
    repaired before any handle exists. But the repair copies the whole
    store aside and rewrites sqlite, and at import time an OSError from
    that copy (a read-only volume, a full disk, a packaged read-only
    Resources dir) propagated out of `import services.chroma` and aborted
    `import main`, so the app never launched at all. Swallowing it here
    leaves a backend that binds its port and serves; only the
    pre-fastembed store stays unreadable, which it already was.
    """
    global _repaired
    with _repair_lock:
        if _repaired:
            return
        _repaired = True
        try:
            repair_embedding_function()
        except Exception as exc:
            logger.error(f"Embedding-function repair failed: {exc}", exc_info=True)


def get_collection() -> chromadb.Collection:
    """Get or create the ChromaDB collection with cosine similarity."""
    _repair_once()
    return _client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
        embedding_function=_ef,
    )


def max_batch_size() -> int:
    """Largest number of records Chroma accepts in one add or update call."""
    return _client.get_max_batch_size()


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
    if not SAVED_TAGS_FILE.exists():
        return []
    try:
        return json.loads(SAVED_TAGS_FILE.read_text())
    except Exception:
        return []


def save_tag(tag: str) -> None:
    """Persist a user-created tag so it appears in future uploads."""
    tags = set(_load_saved_tags())
    tags.add(tag)
    SAVED_TAGS_FILE.write_text(json.dumps(sorted(tags)))


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
    """Update tags on all chunks belonging to a document.

    Chroma rejects an empty list, so clearing the last tag writes None,
    which removes the key. That is the same on-disk shape an untagged
    upload produces, and every reader already defaults it to [].
    """
    col = get_collection()
    chunk_ids = col.get(where={"file_id": file_id}, include=[])["ids"]
    if not chunk_ids:
        return False
    col.update(ids=chunk_ids, metadatas=[{"tags": tags or None} for _ in chunk_ids])
    return True


def set_title(file_id: str, title: str) -> bool:
    """Update title on all chunks belonging to a document."""
    col = get_collection()
    chunk_ids = col.get(where={"file_id": file_id}, include=[])["ids"]
    if not chunk_ids:
        return False
    col.update(ids=chunk_ids, metadatas=[{"title": title} for _ in chunk_ids])
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
