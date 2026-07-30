"""The shared write path, ARCHITECTURE_V2 section 4.

Every test here runs against the fake_collection recorder, so nothing
embeds and no model is downloaded. The contextualisation branch is
exercised through ORIGAMI_MODEL_STUB, at zero cost.
"""

import json
from datetime import datetime, timezone

from services import usage
from services.embeddings import current_embedding_model_id
from services.indexing import SegmentDraft, index_item
from services.schema import (
    Item,
    provenance_for_screenshot,
    read_schema_fields,
    segment_id,
)

_STUB_BLURB = "Stubbed context blurb situating this chunk."


def _item() -> Item:
    return Item(
        id="item-abc",
        source_type="screenshot",
        source_id="deadbeef",
        title="A screenshot",
        created_at="",
        ingested_at=datetime.now(timezone.utc).isoformat(),
        provenance=provenance_for_screenshot(),
        raw_ref="screenshots/item-abc.png",
    )


def _draft(ordinal: int, modality: str, chars: int) -> SegmentDraft:
    return SegmentDraft(
        ordinal=ordinal,
        modality=modality,
        content="x" * chars,
        content_source="extracted",
    )


def _ledger_rows() -> list[dict]:
    path = usage.ledger_path()
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


async def test_ids_and_documents_follow_the_segment_contract(fake_collection):
    item = _item()
    drafts = [
        SegmentDraft(ordinal=0, modality="ocr", content="ocr text", content_source="extracted"),
        SegmentDraft(ordinal=1, modality="caption", content="a caption", content_source="generated"),
    ]

    written = await index_item(item, drafts)

    assert written == 2
    by_id = {rec[0]: rec for rec in fake_collection.records}
    assert set(by_id) == {segment_id(item.id, 0), segment_id(item.id, 1)}
    assert by_id[segment_id(item.id, 0)][1] == "ocr text"
    assert by_id[segment_id(item.id, 1)][1] == "a caption"


async def test_every_schema_field_is_written_not_defaulted(fake_collection):
    """The test that fails if a record bypasses segment_metadata and starts
    impersonating a PDF through read_schema_fields' legacy defaults."""
    item = _item()

    await index_item(item, [
        SegmentDraft(ordinal=0, modality="ocr", content="ocr text", content_source="extracted"),
    ])

    meta = fake_collection.records[0][2]
    fields = read_schema_fields(meta)

    assert fields["source_type"] == "screenshot"
    assert fields["source_id"] == "deadbeef"
    assert fields["created_at"] == ""
    assert fields["ingested_at"] == item.ingested_at
    assert fields["raw_ref"] == "screenshots/item-abc.png"
    assert fields["modality"] == "ocr"
    assert fields["content_source"] == "extracted"
    assert fields["embedding_model"] == current_embedding_model_id()
    assert fields["prov_origin"] == "unknown"
    assert fields["prov_trust"] == "untrusted"
    assert fields["prov_channel"] == "screenshot"
    assert fields["prov_author"] == ""
    assert fields["context_status"] == "skipped"
    assert meta["schema_version"] == 3
    assert meta["file_id"] == item.id
    assert meta["title"] == item.title
    assert meta["chunk_index"] == 0


async def test_the_denormalised_reader_keys_are_present(fake_collection):
    """filename is subscripted by chroma.find_by_hash and
    documents.delete_document; original_chunk is what rag.vector_search
    returns as the citable text."""
    await index_item(_item(), [
        SegmentDraft(ordinal=0, modality="ocr", content="ocr text", content_source="extracted"),
    ])

    meta = fake_collection.records[0][2]

    assert meta["filename"] == "item-abc.png"
    assert meta["original_chunk"] == "ocr text"
    assert meta["content_hash"] == "deadbeef"


async def test_contextualization_is_skipped_on_modality(fake_collection):
    """A long caption alongside a second draft is still not contextualised:
    the gate rejects it before length is consulted."""
    await index_item(
        _item(),
        [_draft(0, "caption", 10_000), _draft(1, "caption", 10_000)],
        whole_text="x" * 10_000,
    )

    statuses = {rec[2]["context_status"] for rec in fake_collection.records}
    assert statuses == {"skipped"}
    assert _ledger_rows() == []


async def test_contextualization_is_skipped_on_a_single_segment(fake_collection):
    """One segment is the whole, so the call would situate a text inside
    itself. This is section 4's "waste on a short snippet"."""
    await index_item(_item(), [_draft(0, "text", 10_000)], whole_text="x" * 10_000)

    assert fake_collection.records[0][2]["context_status"] == "skipped"
    assert _ledger_rows() == []


async def test_contextualization_is_skipped_on_length(fake_collection):
    await index_item(
        _item(),
        [_draft(0, "text", 100), _draft(1, "text", 100)],
        whole_text="x" * 200,
    )

    statuses = {rec[2]["context_status"] for rec in fake_collection.records}
    assert statuses == {"skipped"}
    assert _ledger_rows() == []


async def test_contextualization_fires_for_long_text_segments(fake_collection):
    whole = "x" * 20_000
    await index_item(
        _item(),
        [_draft(0, "text", 10_000), _draft(1, "text", 10_000)],
        whole_text=whole,
    )

    assert len(fake_collection.records) == 2
    for _id, document, meta in fake_collection.records:
        assert meta["context_status"] == "ok"
        # The blurb is prepended to the embedded string only. The citable
        # text is still the chunk verbatim, so content_source does not move.
        assert meta["content_source"] == "extracted"
        assert document.startswith(_STUB_BLURB)
        # The verbatim text is what gets cited, so it must survive intact.
        assert meta["original_chunk"] == "x" * 10_000
        assert document == f"{_STUB_BLURB}\n\n{'x' * 10_000}"


async def test_the_contextualization_calls_are_billed_to_a_background_permit(fake_collection):
    await index_item(
        _item(),
        [_draft(0, "text", 10_000), _draft(1, "text", 10_000)],
        whole_text="x" * 20_000,
    )

    rows = _ledger_rows()
    assert len(rows) == 2
    assert {row["origin"] for row in rows} == {"index"}
    assert {row["purpose"] for row in rows} == {"contextualize"}
    # The stub measured nothing, so it must claim nothing.
    assert all(row["cost_usd"] == 0.0 and row["priced"] is False for row in rows)


async def test_no_drafts_writes_nothing(fake_collection):
    assert await index_item(_item(), []) == 0
    assert fake_collection.records == []


async def test_a_reindex_replaces_rather_than_silently_dropping(fake_collection):
    """chromadb's add on an existing id writes nothing and raises nothing,
    so a corrected VLM result could never replace a bad first one while
    index_item still reported it as written."""
    item = _item()
    await index_item(item, [
        SegmentDraft(ordinal=0, modality="ocr", content="first ocr", content_source="extracted"),
    ])

    written = await index_item(item, [
        SegmentDraft(ordinal=0, modality="ocr", content="corrected ocr", content_source="extracted"),
    ])

    assert written == 1
    assert len(fake_collection.records) == 1
    assert fake_collection.records[0][1] == "corrected ocr"


async def test_a_shorter_reindex_drops_the_segments_it_no_longer_covers(fake_collection):
    item = _item()
    await index_item(item, [_draft(0, "ocr", 20), _draft(1, "ocr", 20), _draft(2, "ocr", 20)])

    await index_item(item, [_draft(0, "ocr", 20)])

    assert [rec[0] for rec in fake_collection.records] == [segment_id(item.id, 0)]


async def test_every_record_carries_the_expected_segment_count(fake_collection):
    """Writes are not transactional, so a truncated Item is only
    detectable if the records say how many there should have been."""
    await index_item(_item(), [_draft(0, "ocr", 20), _draft(1, "ocr", 20)])

    assert {rec[2]["segment_total"] for rec in fake_collection.records} == {2}
