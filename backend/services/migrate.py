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
    """Copy the whole store aside before anything mutates it.

    copytree rather than a sqlite copy: the vectors live in the HNSW
    segment directory, not in chroma.sqlite3.

    One backup per schema version rather than one per process. The copy
    worth keeping is the first, taken before any record was rewritten; a
    later one captures a half-migrated store. Timestamped names meant a
    crash-restart loop wrote a fresh full-size copy on every launch, so a
    2 GB store filled the disk over a handful of failed starts.

    The copy lands on a `.partial` path and is renamed into place only
    once copytree returns. An interrupted copy is therefore never
    mistaken for a usable backup, and never accumulates: the next attempt
    discards it rather than adding to it.
    """
    global _backed_up
    if _backed_up or not CHROMA_DIR.exists():
        return None

    destination = CHROMA_DIR.parent / f"{CHROMA_DIR.name}.bak-v{SCHEMA_VERSION}"
    if destination.exists():
        _backed_up = True
        logger.info(f"Reusing the pre-v{SCHEMA_VERSION} backup at {destination}")
        return destination

    staging = destination.with_name(f"{destination.name}.partial")
    shutil.rmtree(staging, ignore_errors=True)
    try:
        shutil.copytree(CHROMA_DIR, staging)
    except BaseException:
        # BaseException on purpose: a KeyboardInterrupt part-way through
        # must not leave a full-size partial copy behind either.
        shutil.rmtree(staging, ignore_errors=True)
        raise
    staging.replace(destination)

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
    """The v2 fields for one record that is behind the current version.

    Built from read_schema_fields so the migration writes exactly what the
    legacy read path would otherwise infer, and the two can never disagree.

    A derived value only fills a field that is absent or empty. A v1 record
    carries none of them, so the v1->v2 hop is unchanged. The guard matters
    at the next SCHEMA_VERSION bump, which re-selects records that already
    hold correct values: overwriting those would stamp the legacy model id
    onto a segment embedded by the current one, hiding it from the
    incremental re-embed job that embedding_model exists to drive.

    ingested_at is deliberately left empty. copy2 preserves the *source*
    mtime, so a PDF's mtime is the author's timestamp rather than the time
    Origami saw it. An empty string is honest; a plausible wrong value is not.
    """
    record = read_schema_fields(meta)
    filename = meta.get("filename", "")
    derived = {
        "source_id": meta.get("content_hash", ""),
        "created_at": meta.get("publish_date", ""),
        "raw_ref": f"pdfs/{filename}" if filename else "",
        "embedding_model": model_id,
    }
    for key, value in derived.items():
        if not record[key]:
            record[key] = value
    record["schema_version"] = SCHEMA_VERSION
    return record


def backfill_schema_v2() -> int:
    """Step B: write the v2 metadata onto every record that predates it.

    Metadata-only updates merge and touch no vector, so this recomputes no
    embeddings. Returns the number of records updated.

    Read and write are both paged. Fetching every stale record's metadata
    in one call binds a SQL variable per matched row and raises "too many
    SQL variables" above 32,766 of them, which silently aborted the entire
    migration on any library past roughly 650 PDFs. It also held every
    matched original_chunk resident at once: 30k records cost 647 MB.
    """
    from services.chroma import get_collection, max_batch_size

    collection = get_collection()
    if collection.count() == 0:
        return 0

    # include=[] binds no per-row variable, so the id list is safe to take
    # in one call at any corpus size. Only the metadata fetch needs paging.
    ids = collection.get(where={"schema_version": {"$ne": SCHEMA_VERSION}}, include=[])["ids"]
    if not ids:
        return 0

    # A store whose persisted config was never `known` was written by the
    # current stack, so its vectors are the current model's. Stamping the
    # current model onto legacy vectors instead would hide them from the
    # incremental re-embed job forever, and a wrong label is
    # indistinguishable from a right one at query time.
    model_id = legacy_embedding_model_id() or current_embedding_model_id()

    _backup_once()

    batch = max_batch_size()
    done = 0
    for start in range(0, len(ids), batch):
        # get(ids=...) makes no promise about ordering, so the update is
        # keyed on the ids the page actually came back with.
        page = collection.get(ids=ids[start:start + batch], include=["metadatas"])
        updates = [_backfill_record(meta, model_id) for meta in page["metadatas"]]
        collection.update(ids=page["ids"], metadatas=updates)
        done += len(page["ids"])

    logger.info(f"Backfilled schema v{SCHEMA_VERSION} onto {done} records (embedding_model={model_id})")
    return done


def run_migrations() -> dict:
    """Both steps in order. Safe to call on an empty or already-migrated store."""
    repaired = repair_embedding_function()
    return {
        "repaired_embedding_function": repaired,
        "legacy_embedding_model": legacy_embedding_model_id(),
        "backfilled": backfill_schema_v2(),
    }
