"""One-time repairs that bring an existing Chroma store onto schema v2.

Two ordered steps, both idempotent. Step A repairs the embedding-function
conflict that otherwise stops the current code opening a pre-fastembed
store at all. Step B backfills the schema v2 metadata onto the records
that predate it, without recomputing a single vector.

Nothing here imports services.chroma at module level: step A rewrites the
collection configuration in sqlite, and chromadb caches that configuration
the first time a collection handle is created.
"""

import json
import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import CHROMA_DIR
from services.embeddings import current_embedding_model_id
from services.schema import SCHEMA_VERSION, read_schema_fields

logger = logging.getLogger(__name__)

SQLITE_PATH = CHROMA_DIR / "chroma.sqlite3"

# Records which embedding function produced the vectors already in the
# store, read off the collection's own persisted configuration before that
# configuration is rewritten. Durable on purpose: if the backfill is
# interrupted, a later run can no longer recover this from the store.
STATE_PATH = CHROMA_DIR / "origami_migration.json"

_backed_up = False


def _legacyise(node) -> list[dict]:
    """Rewrite every "known" embedding_function config to the legacy marker.

    Returns the configs that were replaced, so the caller can record which
    model actually produced the vectors already in the store.
    """
    replaced: list[dict] = []
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if key == "embedding_function" and isinstance(value, dict) and value.get("type") == "known":
                replaced.append(value)
                node[key] = {"type": "legacy"}
            else:
                replaced.extend(_legacyise(value))
    elif isinstance(node, list):
        for value in node:
            replaced.extend(_legacyise(value))
    return replaced


def _backup_once() -> Path | None:
    """Copy the whole store aside, at most once per process.

    copytree rather than a sqlite copy: the vectors live in the HNSW
    segment directory, not in chroma.sqlite3.
    """
    global _backed_up
    if _backed_up or not CHROMA_DIR.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = CHROMA_DIR.parent / f"{CHROMA_DIR.name}.bak-{stamp}"
    shutil.copytree(CHROMA_DIR, destination)
    _backed_up = True
    logger.info(f"Backed up Chroma store to {destination}")
    return destination


def _model_id_from_config(config: dict) -> str:
    """Build an embedding_model identifier from a persisted Chroma EF config."""
    name = config.get("name", "unknown")
    model_name = (config.get("config") or {}).get("model_name", "")
    return f"{name}:{model_name}" if model_name else name


def legacy_embedding_model_id() -> str | None:
    """The model that produced the store's pre-existing vectors, if recorded."""
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text()).get("legacy_embedding_model")
    except (OSError, ValueError) as exc:
        logger.error(f"Could not read {STATE_PATH}: {exc}")
        return None


def repair_embedding_function() -> str | None:
    """Step A: converge the persisted embedding-function config on "legacy".

    A store written before the fastembed swap declares a `known`
    sentence_transformer function. Opening it with the current code raises
    an embedding-function conflict, so no later step can run. A store
    written by the current code persists `{"type": "legacy"}` already, and
    this rewrite converges the old one onto that shape.

    Returns the model identifier it found, or None if nothing needed
    repairing.
    """
    if not SQLITE_PATH.exists():
        return None

    connection = sqlite3.connect(SQLITE_PATH)
    try:
        rows = connection.execute("SELECT id, schema_str FROM collections").fetchall()
        pending: list[tuple[str, str]] = []
        found: str | None = None
        for collection_id, raw in rows:
            if not raw:
                continue
            schema = json.loads(raw)
            replaced = _legacyise(schema)
            if not replaced:
                continue
            found = _model_id_from_config(replaced[0])
            pending.append((json.dumps(schema), collection_id))

        if not pending:
            return None

        _backup_once()
        STATE_PATH.write_text(json.dumps({
            "legacy_embedding_model": found,
            "repaired_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2))

        connection.executemany(
            "UPDATE collections SET schema_str = ? WHERE id = ?", pending
        )
        connection.commit()
    finally:
        connection.close()

    logger.info(f"Repaired embedding-function config for {len(pending)} collection(s); vectors are {found}")
    return found


def _backfill_record(meta: dict, model_id: str) -> dict:
    """The v2 fields for one v1 record.

    Built from read_schema_fields so the migration writes exactly what the
    legacy read path would otherwise infer, and the two can never disagree.
    Only the fields derivable from the record itself are overridden.

    ingested_at is deliberately left empty. copy2 preserves the *source*
    mtime, so a PDF's mtime is the author's timestamp rather than the time
    Origami saw it. An empty string is honest; a plausible wrong value is not.
    """
    record = read_schema_fields(meta)
    filename = meta.get("filename", "")
    record["schema_version"] = SCHEMA_VERSION
    record["source_id"] = meta.get("content_hash", "")
    record["created_at"] = meta.get("publish_date", "")
    record["raw_ref"] = f"pdfs/{filename}" if filename else ""
    record["embedding_model"] = model_id
    return record


def backfill_schema_v2() -> int:
    """Step B: write the v2 metadata onto every record that predates it.

    Metadata-only updates merge and touch no vector, so this recomputes no
    embeddings. Returns the number of records updated.
    """
    from services.chroma import get_collection, max_batch_size

    collection = get_collection()
    if collection.count() == 0:
        return 0

    stale = collection.get(where={"schema_version": {"$ne": SCHEMA_VERSION}}, include=["metadatas"])
    ids = stale["ids"]
    if not ids:
        return 0

    # A store whose persisted config was never `known` was written by the
    # current stack, so its vectors are the current model's. Stamping the
    # current model onto legacy vectors instead would hide them from the
    # incremental re-embed job forever, and a wrong label is
    # indistinguishable from a right one at query time.
    model_id = legacy_embedding_model_id() or current_embedding_model_id()

    _backup_once()

    updates = [_backfill_record(meta, model_id) for meta in stale["metadatas"]]
    batch = max_batch_size()
    for start in range(0, len(ids), batch):
        collection.update(ids=ids[start:start + batch], metadatas=updates[start:start + batch])

    logger.info(f"Backfilled schema v{SCHEMA_VERSION} onto {len(ids)} records (embedding_model={model_id})")
    return len(ids)


def run_migrations() -> dict:
    """Both steps in order. Safe to call on an empty or already-migrated store."""
    repaired = repair_embedding_function()
    return {
        "repaired_embedding_function": repaired,
        "legacy_embedding_model": legacy_embedding_model_id(),
        "backfilled": backfill_schema_v2(),
    }
