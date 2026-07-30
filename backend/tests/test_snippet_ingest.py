"""Snippet capture, ARCHITECTURE_V2 section 7 step 5."""

import hashlib

from routes.snippets import derive_title, snippet_drafts, snippet_item
from services.indexing import index_item

_SHORT = "The reviewer asked for an ablation over chunk size, not over the embedding model."


def test_item_carries_source_identity():
    item = snippet_item("snip-1", _SHORT, "Reviewer request")

    assert item.source_type == "snippet"
    assert item.source_id == hashlib.sha256(_SHORT.encode("utf-8")).hexdigest()
    assert item.title == "Reviewer request"
    assert item.raw_ref == "snippets/snip-1.md"
    # The text came into existence elsewhere, at a time Origami cannot know.
    assert item.created_at == ""
    assert item.ingested_at


def test_a_pasted_snippet_is_untrusted():
    """The test that fails if someone later decides pasted text is trusted.

    Section 3's test is authorship, not delivery: the text inside a PDF
    someone emailed is untrusted even though the user handed it over.
    Pasting is not typing, and trust="trusted" must stay unreachable.
    """
    item = snippet_item("snip-1", _SHORT, "")

    assert item.provenance.trust == "untrusted"
    assert item.provenance.channel == "snippet"
    assert item.provenance.origin == "unknown"


def test_a_short_snippet_is_one_text_segment():
    drafts = snippet_drafts(_SHORT)

    assert len(drafts) == 1
    assert drafts[0].modality == "text"
    assert drafts[0].content_source == "extracted"
    assert drafts[0].content == _SHORT


async def test_a_short_snippet_costs_nothing_to_ingest(fake_collection):
    """Section 4 calls contextualisation "waste on ... a short snippet".
    This is that sentence made mechanical."""
    from services import usage

    item = snippet_item("snip-1", _SHORT, "Reviewer request")
    written = await index_item(item, snippet_drafts(_SHORT), whole_text=_SHORT)

    assert written == 1
    meta = fake_collection.records[0][2]
    assert meta["context_status"] == "skipped"
    assert meta["content_source"] == "extracted"
    assert meta["source_type"] == "snippet"
    assert meta["prov_trust"] == "untrusted"
    assert not usage.ledger_path().exists()


def test_derive_title_skips_blank_lines_and_hashes():
    assert derive_title("\n\n  # Reviewer request\nbody text") == "Reviewer request"


def test_derive_title_truncates():
    assert derive_title("w" * 200) == "w" * 80


def test_derive_title_falls_back():
    assert derive_title("   \n\n  ") == "Untitled Snippet"
