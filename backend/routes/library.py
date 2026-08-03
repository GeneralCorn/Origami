"""The faceted library: every Item, grouped, counted, and filterable.

`/documents` answers "what PDFs do I have" and predates the schema. This
answers "what is in here, by where it came from", which is the question
PRODUCT_DIRECTION.md builds the interface around, so it reads the Phase 3
fields rather than the pre-schema subset.

Items and facets ship in one response on purpose. Both need the same full
scan of segment metadata, and serving them from two endpoints would pay for
that scan twice on every render.
"""

import logging
from collections import Counter

from fastapi import APIRouter

from services.chroma import get_collection
from services.schema import read_schema_fields

router = APIRouter()
logger = logging.getLogger(__name__)

# Facets the interface groups by, named as the item exposes them. Trust is
# included because "who wrote this" is the axis nothing else in this category
# offers, and it is the one the agent's egress rule keys on. Modality is
# counted per segment rather than per item, since one item holds several.
ITEM_FACETS = ("source_type", "trust", "origin")
EMPTY_FACETS = {name: {} for name in (*ITEM_FACETS, "modality")}


def _newest(a: str, b: str) -> str:
    """Later of two ISO strings, tolerating the empty string a v1 record has."""
    return a if a > b else b


@router.get("/library")
async def library():
    """Every Item with its facet counts.

    One pass over segment metadata builds both, because Chroma cannot project
    a subset of metadata keys: any read that needs one field pays for all of
    them. Measured at roughly 1.9KB of metadata per segment, so a corpus of
    ten thousand screenshots at three segments each moves about 57MB per
    call. That is tolerable at the sizes this has been run at and is the
    first thing to page when it is not; see PRODUCT_DIRECTION.md on scale.
    """
    collection = get_collection()
    if collection.count() == 0:
        return {"items": [], "facets": EMPTY_FACETS, "total": 0}

    result = collection.get(include=["metadatas"])

    items: dict[str, dict] = {}
    for meta in result["metadatas"] or []:
        file_id = meta.get("file_id", "")
        if not file_id:
            continue
        fields = read_schema_fields(meta)
        item = items.get(file_id)
        if item is None:
            item = {
                "file_id": file_id,
                "title": meta.get("title") or meta.get("filename") or "Untitled",
                "filename": meta.get("filename", ""),
                "source_type": fields["source_type"],
                "source_id": fields["source_id"],
                "raw_ref": fields["raw_ref"],
                "created_at": fields["created_at"],
                "ingested_at": fields["ingested_at"],
                "origin": fields["prov_origin"],
                "trust": fields["prov_trust"],
                "channel": fields["prov_channel"],
                "tags": meta.get("tags", []),
                "segments": 0,
                # What kinds of text this Item holds. A screenshot carrying
                # both reads differently from one carrying only a caption,
                # which is the difference between text somebody wrote and
                # text a model guessed.
                "modalities": Counter(),
            }
            items[file_id] = item
        item["segments"] += 1
        item["modalities"][fields["modality"]] += 1
        # An Item's timestamps are denormalised onto every segment, but a
        # partial migration can leave them uneven, so take the newest seen.
        item["created_at"] = _newest(item["created_at"], fields["created_at"])
        item["ingested_at"] = _newest(item["ingested_at"], fields["ingested_at"])
        # Trust is deliberately not averaged. One untrusted segment makes the
        # whole Item untrusted, because that is how the egress rule reads it.
        if fields["prov_trust"] == "untrusted":
            item["trust"] = "untrusted"

    rows = []
    for item in items.values():
        item["modalities"] = dict(item["modalities"])
        rows.append(item)

    # Newest first, falling back to ingest time for anything a source could
    # not date, then by title so the order is stable rather than arbitrary.
    rows.sort(key=lambda r: (r["created_at"] or r["ingested_at"], r["title"]), reverse=True)

    facets = {name: dict(Counter(row[name] for row in rows)) for name in ITEM_FACETS}
    # Summed rather than counted, so this is segments per modality across the
    # corpus and does not agree with the item totals above. That is the honest
    # number: one screenshot contributes one caption and several OCR segments.
    facets["modality"] = dict(sum((Counter(row["modalities"]) for row in rows), Counter()))

    return {"items": rows, "facets": facets, "total": len(rows)}
