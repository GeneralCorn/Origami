"""Bring an existing Chroma store onto the Item/Segment schema (v2).

Two steps, both idempotent and both safe to re-run:

1. Repair the persisted embedding-function config. A store written before
   the fastembed swap declares a `known` sentence_transformer function and
   the current code cannot open it at all.
2. Backfill the schema v2 metadata onto every record that predates it.
   Metadata-only updates merge and recompute no vectors.

The store is copied aside before either step mutates anything.

Run from the repo root:

    cd backend && uv run python ../scripts/migrate_schema_v2.py
"""

import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND_DIR))

# Mirrors backend/main.py, and has to. config.py resolves CHROMA_DIR,
# CHROMA_COLLECTION and EMBEDDING_MODEL from the bare environment, so a
# script that skipped this migrated whichever store the defaults pointed
# at, created an empty `documents` collection beside the real one, and
# still exited 0 reporting success.
_DATA_DIR = Path(os.getenv("ORIGAMI_DATA_DIR", str(_BACKEND_DIR)))
load_dotenv(_DATA_DIR / ".env.local")
load_dotenv(_BACKEND_DIR / ".env.local")

from config import CHROMA_DIR, CHROMA_COLLECTION
from services.migrate import run_migrations
from services.schema import SCHEMA_VERSION


def collection_exists() -> bool:
    """Whether the configured collection is actually in this store.

    Read straight from sqlite rather than through a chromadb client:
    get_or_create_collection would conjure an empty collection, and the
    script would then report "0 records, 0 not at schema v2" and exit 0
    over a store it never touched.
    """
    database = CHROMA_DIR / "chroma.sqlite3"
    if not database.exists():
        return False
    connection = sqlite3.connect(database)
    try:
        names = [row[0] for row in connection.execute("SELECT name FROM collections")]
    finally:
        connection.close()
    return CHROMA_COLLECTION in names


def main() -> int:
    print(f"store:      {CHROMA_DIR.resolve()}")
    print(f"collection: {CHROMA_COLLECTION}")

    if not collection_exists():
        print(f"no collection named {CHROMA_COLLECTION!r} in this store; nothing was migrated")
        return 1

    # run_migrations before importing services.chroma: importing that module
    # creates the client, and chromadb caches the collection configuration
    # the repair step exists to rewrite.
    result = run_migrations()
    print(f"repaired embedding function: {result['repaired_embedding_function'] or 'nothing to repair'}")
    print(f"legacy embedding model:      {result['legacy_embedding_model'] or 'none recorded'}")
    print(f"records backfilled:          {result['backfilled']}")

    from services.chroma import get_collection

    collection = get_collection()
    stale = collection.get(where={"schema_version": {"$ne": SCHEMA_VERSION}}, include=[])["ids"]
    print(f"after: {collection.count()} records, {len(stale)} not at schema v{SCHEMA_VERSION}")
    return 0 if not stale else 1


if __name__ == "__main__":
    sys.exit(main())
