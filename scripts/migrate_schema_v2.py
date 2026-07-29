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

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from config import CHROMA_DIR
from services.migrate import run_migrations
from services.schema import SCHEMA_VERSION


def main() -> int:
    print(f"store: {CHROMA_DIR}")

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
