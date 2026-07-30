"""The v2 to v3 hop: content_source stops describing the embedded string.

_backfill_record is a pure function over one record's metadata, so this
needs no store.
"""

from services.migrate import _backfill_record
from services.schema import SCHEMA_VERSION

_MODEL_ID = "fastembed:BAAI/bge-small-en-v1.5"


def _v2(**overrides) -> dict:
    record = {
        "schema_version": 2,
        "source_type": "pdf",
        "source_id": "abc123",
        "created_at": "2026-01-01",
        "ingested_at": "2026-01-02T00:00:00+00:00",
        "raw_ref": "pdfs/paper.pdf",
        "modality": "text",
        "content_source": "generated",
        "embedding_model": _MODEL_ID,
        "prov_origin": "self",
        "prov_trust": "untrusted",
        "prov_channel": "upload",
        "prov_author": "",
        "context_status": "ok",
        "filename": "paper.pdf",
    }
    record.update(overrides)
    return record


def test_a_contextualised_chunk_of_human_prose_stops_claiming_to_be_generated():
    """v2 wrote content_source against the embedded string, so a chunk of
    a paper whose blurb succeeded was stored as "generated". A consumer
    filtering for model-written text kept human paragraphs."""
    record = _backfill_record(_v2(), _MODEL_ID)

    assert record["content_source"] == "extracted"
    assert record["context_status"] == "ok"
    assert record["schema_version"] == SCHEMA_VERSION


def test_a_generated_caption_keeps_its_label():
    record = _backfill_record(
        _v2(source_type="screenshot", modality="caption", context_status="skipped"),
        _MODEL_ID,
    )

    assert record["content_source"] == "generated"


def test_ocr_is_untouched():
    record = _backfill_record(
        _v2(source_type="screenshot", modality="ocr", content_source="extracted"),
        _MODEL_ID,
    )

    assert record["content_source"] == "extracted"


def test_a_v1_record_still_gets_its_derived_fields():
    """The v1 to v2 hop must not regress: those records carry none of the
    schema fields and the legacy defaults are facts about that pipeline."""
    record = _backfill_record(
        {"filename": "old.pdf", "content_hash": "hash1", "publish_date": "2025-05-05"},
        _MODEL_ID,
    )

    assert record["source_id"] == "hash1"
    assert record["created_at"] == "2025-05-05"
    assert record["raw_ref"] == "pdfs/old.pdf"
    assert record["embedding_model"] == _MODEL_ID
    assert record["content_source"] == "extracted"
    assert record["prov_trust"] == "untrusted"
