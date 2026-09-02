"""Collections: the store, and the note entries behind each one."""

import json

import pytest

from config import COLLECTIONS_FILE, NOTES_DIR
import services.collections as collections
from services.collections import (
    DEFAULT_COLLECTIONS,
    ENTRY_CLOSE,
    ENTRY_OPEN,
    INBOX_ID,
    Entry,
    create_collection,
    delete_collection,
    ensure_note,
    find_entry_collection,
    get_collection,
    list_collections,
    move_entry,
    normalize_collection_id,
    remove_entry,
    render_entry,
    update_collection,
    upsert_entry,
)


@pytest.fixture(autouse=True)
def _fresh_store():
    if COLLECTIONS_FILE.exists():
        COLLECTIONS_FILE.unlink()
    for path in NOTES_DIR.glob("*.md"):
        path.unlink()
    yield


def _note_text(note_id: str) -> str:
    return (NOTES_DIR / f"{note_id}.md").read_text(encoding="utf-8")


# ── The store ─────────────────────────────────────────────────────


def test_first_read_seeds_the_defaults_to_disk():
    listed = list_collections()

    assert [c.id for c in listed] == [c.id for c in DEFAULT_COLLECTIONS]
    assert COLLECTIONS_FILE.exists()
    assert json.loads(COLLECTIONS_FILE.read_text())["collections"][0]["id"] == "shows-to-watch"


def test_the_inbox_is_always_present_and_builtin():
    inbox = get_collection(INBOX_ID)
    assert inbox is not None and inbox.builtin

    # A hand-edited file that dropped it gets it back.
    data = json.loads(COLLECTIONS_FILE.read_text())
    data["collections"] = [c for c in data["collections"] if c["id"] != INBOX_ID]
    COLLECTIONS_FILE.write_text(json.dumps(data))

    assert get_collection(INBOX_ID) is not None


def test_create_slugs_the_name_and_persists():
    created = create_collection("Books to read", "Novels and non-fiction.", ["goodreads", "isbn"])

    assert created.id == "books-to-read"
    assert created.keywords == ("goodreads", "isbn")
    assert get_collection("books-to-read") == created


def test_create_rejects_a_duplicate_name_and_disambiguates_a_clashing_slug():
    create_collection("Shows to watch!")  # slugs to shows-to-watch, which exists
    assert get_collection("shows-to-watch-2") is not None
    with pytest.raises(ValueError):
        create_collection("shows to watch")
    with pytest.raises(ValueError):
        create_collection("   ")


def test_update_changes_only_what_was_given():
    updated = update_collection("tech-to-try", description="New description")

    assert updated.description == "New description"
    assert updated.name == "Tech to try"
    assert updated.keywords == get_collection("tech-to-try").keywords
    with pytest.raises(KeyError):
        update_collection("nope", name="x")


def test_delete_removes_everything_but_the_inbox():
    assert delete_collection("recipes-to-cook") is True
    assert get_collection("recipes-to-cook") is None
    assert delete_collection("recipes-to-cook") is False
    with pytest.raises(ValueError):
        delete_collection(INBOX_ID)


@pytest.mark.parametrize("raw,expected", [
    ("shows-to-watch", "shows-to-watch"),
    ("Shows to watch", "shows-to-watch"),
    ("shows_to_watch", "shows-to-watch"),
    ("cryptozoology", INBOX_ID),
    ("inbox\n\n## Injected", INBOX_ID),
    (None, INBOX_ID),
    (["shows-to-watch"], INBOX_ID),
])
def test_model_output_resolves_to_an_existing_collection_or_the_inbox(raw, expected):
    assert normalize_collection_id(raw) == expected


def test_embedding_text_names_the_collection_and_its_hints():
    text = get_collection("papers-to-read").embedding_text
    assert text.startswith("Papers to read.")
    assert "arxiv" in text


# ── Notes ─────────────────────────────────────────────────────────


def test_ensure_note_creates_once_and_records_the_id():
    collection = get_collection("shows-to-watch")
    note_id = ensure_note(collection)

    assert _note_text(note_id).startswith("# Shows to watch\n")
    assert get_collection("shows-to-watch").note_id == note_id
    assert ensure_note(get_collection("shows-to-watch")) == note_id
    assert len(list(NOTES_DIR.glob("*.md"))) == 1


def test_a_deleted_note_is_recreated_rather_than_resurrected():
    note_id = ensure_note(get_collection("shows-to-watch"))
    (NOTES_DIR / f"{note_id}.md").unlink()

    fresh = ensure_note(get_collection("shows-to-watch"))

    assert fresh != note_id
    assert (NOTES_DIR / f"{fresh}.md").exists()


_ENTRY = Entry(
    screenshot="abc123.png",
    title="Severance — Season 2, Episode 3",
    captured_at="2026-09-02T10:00:00+00:00",
    source_app="netflix",
    description="The Netflix episode page for Severance.",
    lines=("Season 2, Episode 3", "Who Is Alive?", "IMDb 8.7 2025 TV-MA"),
)


def test_render_entry_is_a_marked_block_with_image_and_quoted_lines():
    block = render_entry(_ENTRY)

    assert block.startswith(ENTRY_OPEN.format(name="abc123.png"))
    assert block.endswith(ENTRY_CLOSE.format(name="abc123.png"))
    assert "### Severance — Season 2, Episode 3" in block
    assert "*netflix · 2026-09-02 · [screenshot](../screenshots/abc123.png)*" in block
    assert "![Severance — Season 2, Episode 3](../screenshots/abc123.png)" in block
    assert "The Netflix episode page for Severance." in block
    assert "> Who Is Alive?" in block


def test_render_entry_caps_the_quote_and_flattens_hostile_titles():
    entry = Entry(
        screenshot="x.png", title="# Heading\n\ninjected", captured_at="2026-01-01",
        lines=tuple(f"line {i}" for i in range(40)),
    )
    block = render_entry(entry)

    assert "### Heading injected" in block
    assert block.count("\n> ") == 13  # 12 lines plus the ellipsis
    assert "> …" in block
    assert "unknown" not in render_entry(Entry("x.png", "t", "2026-01-01", source_app="unknown"))


def test_upsert_appends_once_and_replaces_in_place():
    note_id = upsert_entry("shows-to-watch", _ENTRY)
    first = _note_text(note_id)
    assert first.count(ENTRY_OPEN.format(name="abc123.png")) == 1

    richer = Entry(**{**_ENTRY.__dict__, "description": "A better caption arrived."})
    upsert_entry("shows-to-watch", richer)
    second = _note_text(note_id)

    assert second.count(ENTRY_OPEN.format(name="abc123.png")) == 1
    assert "A better caption arrived." in second
    assert "The Netflix episode page" not in second


def test_upsert_into_an_unknown_collection_lands_in_the_inbox():
    note_id = upsert_entry("does-not-exist", _ENTRY)
    assert note_id == get_collection(INBOX_ID).note_id


def test_remove_cuts_only_the_block_and_leaves_user_text():
    note_id = upsert_entry("shows-to-watch", _ENTRY)
    path = NOTES_DIR / f"{note_id}.md"
    path.write_text(path.read_text() + "\nMy own thoughts about the finale.\n")

    removed = remove_entry(note_id, "abc123.png")

    assert removed and removed.startswith(ENTRY_OPEN.format(name="abc123.png"))
    remaining = _note_text(note_id)
    assert "My own thoughts about the finale." in remaining
    assert "abc123.png" not in remaining
    assert remove_entry(note_id, "abc123.png") is None
    assert remove_entry("", "abc123.png") is None


def test_move_relocates_the_block_verbatim_when_no_entry_is_given():
    upsert_entry(INBOX_ID, _ENTRY)
    inbox_note = get_collection(INBOX_ID).note_id
    path = NOTES_DIR / f"{inbox_note}.md"
    path.write_text(path.read_text().replace("> Who Is Alive?", "> Who Is Alive? (my edit)"))

    destination = move_entry("abc123.png", "shows-to-watch")

    assert "abc123.png" not in _note_text(inbox_note)
    assert "> Who Is Alive? (my edit)" in _note_text(destination)
    assert find_entry_collection("abc123.png") == "shows-to-watch"


def test_move_with_an_entry_re_renders_and_is_idempotent():
    upsert_entry(INBOX_ID, _ENTRY)
    move_entry("abc123.png", "shows-to-watch", _ENTRY)
    move_entry("abc123.png", "shows-to-watch", _ENTRY)

    assert _note_text(get_collection("shows-to-watch").note_id).count("abc123.png") == render_entry(_ENTRY).count("abc123.png")
    assert find_entry_collection("abc123.png") == "shows-to-watch"
    assert find_entry_collection("never-filed.png") is None
