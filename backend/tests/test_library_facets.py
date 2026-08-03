"""The faceted library groups segments into Items and counts them honestly."""

from routes import library


class _FakeCollection:
    def __init__(self, metadatas: list[dict]):
        self._metadatas = metadatas

    def count(self) -> int:
        return len(self._metadatas)

    def get(self, include=None):
        return {"metadatas": self._metadatas}


def _seg(file_id: str, **over) -> dict:
    base = {
        "file_id": file_id,
        "title": f"Item {file_id}",
        "filename": f"{file_id}.pdf",
        "source_type": "pdf",
        "source_id": f"hash-{file_id}",
        "raw_ref": f"pdfs/{file_id}.pdf",
        "created_at": "2026-01-01T00:00:00Z",
        "ingested_at": "2026-01-02T00:00:00Z",
        "modality": "text",
        "prov_origin": "self",
        "prov_trust": "trusted",
        "prov_channel": "upload",
        "schema_version": 3,
    }
    base.update(over)
    return base


async def _library(monkeypatch, metadatas: list[dict]) -> dict:
    monkeypatch.setattr(library, "get_collection", lambda: _FakeCollection(metadatas))
    return await library.library()


async def test_empty_store_still_names_every_facet(monkeypatch):
    """The empty response must have the same shape as a populated one.

    An interface that reads facets.modality on a fresh install should get an
    empty mapping rather than a KeyError, so the two branches cannot drift.
    """
    result = await _library(monkeypatch, [])
    assert result == {"items": [], "facets": library.EMPTY_FACETS, "total": 0}
    assert set(result["facets"]) == {"source_type", "trust", "origin", "modality"}


async def test_segments_collapse_into_items(monkeypatch):
    result = await _library(monkeypatch, [_seg("a"), _seg("a"), _seg("b")])
    assert result["total"] == 2
    assert {row["file_id"]: row["segments"] for row in result["items"]} == {"a": 2, "b": 1}
    assert result["facets"]["source_type"] == {"pdf": 2}


async def test_one_untrusted_segment_makes_the_item_untrusted(monkeypatch):
    """Trust is pessimistic, because that is how the egress rule reads it.

    Averaging or majority-voting would let an item with one attacker-authored
    segment present as trusted, which is the whole failure the rule prevents.
    """
    result = await _library(
        monkeypatch,
        [_seg("a", prov_trust="trusted"), _seg("a", prov_trust="untrusted")],
    )
    assert result["items"][0]["trust"] == "untrusted"
    assert result["facets"]["trust"] == {"untrusted": 1}


async def test_modality_counts_segments_while_the_rest_count_items(monkeypatch):
    """A screenshot is one item holding a caption and several OCR segments.

    Reporting modality per item would hide that, so it is summed per segment
    and deliberately does not agree with the item total.
    """
    result = await _library(
        monkeypatch,
        [
            _seg("shot", source_type="screenshot", modality="caption"),
            _seg("shot", source_type="screenshot", modality="ocr"),
            _seg("shot", source_type="screenshot", modality="ocr"),
        ],
    )
    assert result["total"] == 1
    assert result["items"][0]["modalities"] == {"caption": 1, "ocr": 2}
    assert result["facets"]["modality"] == {"caption": 1, "ocr": 2}
    assert result["facets"]["source_type"] == {"screenshot": 1}


async def test_v1_records_fall_back_rather_than_vanishing(monkeypatch):
    """A record written before Phase 3 has none of the schema keys.

    It must still appear in the library, defaulted, rather than being dropped
    or crashing the scan.
    """
    result = await _library(monkeypatch, [{"file_id": "old", "filename": "old.pdf"}])
    row = result["items"][0]
    assert row["source_type"] == "pdf"
    assert row["trust"] == "untrusted"
    assert row["title"] == "old.pdf"


async def test_newest_timestamp_wins_across_uneven_segments(monkeypatch):
    """A partial migration can leave an Item's segments disagreeing on dates."""
    result = await _library(
        monkeypatch,
        [_seg("a", created_at=""), _seg("a", created_at="2026-05-05T00:00:00Z")],
    )
    assert result["items"][0]["created_at"] == "2026-05-05T00:00:00Z"
