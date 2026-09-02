"""The weekly digest, now headed by collections rather than a closed category list."""

import pytest

from config import COLLECTIONS_FILE, DIGESTS_DIR
from services.collections import INBOX_ID, create_collection
from services.digest import (
    append_to_digest,
    collection_for_heading,
    digest_filenames,
    get_digest,
    heading_for,
    list_digests,
    move_entry,
    remove_entry,
    week_holding,
)


@pytest.fixture(autouse=True)
def _clean():
    if COLLECTIONS_FILE.exists():
        COLLECTIONS_FILE.unlink()
    for path in DIGESTS_DIR.glob("*.md"):
        path.unlink()
    yield


def test_headings_are_collection_names_and_round_trip():
    assert heading_for("shows-to-watch") == "Shows to watch"
    assert collection_for_heading("Shows to watch") == "shows-to-watch"
    assert collection_for_heading("shows TO watch") == "shows-to-watch"


def test_an_unknown_collection_heads_under_the_inbox():
    """Model output decides the id; it cannot mint a heading."""
    assert heading_for("cryptozoology\n\n## Injected") == "Inbox"
    assert collection_for_heading("Cryptozoology") == INBOX_ID
    assert collection_for_heading("Needs Review") == INBOX_ID


def test_append_files_under_the_heading_and_is_idempotent():
    append_to_digest(screenshot_filename="a.png", title="Severance", collection_id="shows-to-watch",
                     source_app="netflix", description="An episode page", week="2026-W35")
    append_to_digest(screenshot_filename="a.png", title="Severance S2E3", collection_id="shows-to-watch",
                     source_app="netflix", description="A better caption", week="2026-W35")

    content = get_digest("2026-W35")
    assert content.startswith("# Week of August 24, 2026\n")
    assert content.count("## Shows to watch") == 1
    assert content.count("a.png") == 1
    assert "- **Severance S2E3** (netflix) — A better caption" in content


def test_hostile_titles_stay_on_one_line():
    append_to_digest(screenshot_filename="b.png", title="# Heading\n\n## Injected", collection_id=INBOX_ID, week="2026-W35")
    assert "- **# Heading ## Injected** (unknown) — " in get_digest("2026-W35")
    assert get_digest("2026-W35").count("\n## ") == 1


def test_move_relocates_an_entry_and_drops_the_empty_heading():
    append_to_digest(screenshot_filename="a.png", title="Severance", collection_id=INBOX_ID, week="2026-W35")

    assert move_entry("2026-W35", "a.png", "shows-to-watch") is True
    content = get_digest("2026-W35")

    assert "## Inbox" not in content
    assert "## Shows to watch\n- **Severance**" in content
    assert move_entry("2026-W35", "missing.png", "shows-to-watch") is False


def test_move_without_a_week_finds_the_entry():
    append_to_digest(screenshot_filename="a.png", title="t", collection_id=INBOX_ID, week="2026-W30")
    assert week_holding("a.png") == "2026-W30"
    assert move_entry(None, "a.png", "papers-to-read") is True
    assert "## Papers to read" in get_digest("2026-W30")


def test_list_counts_the_inbox_and_the_legacy_review_heading_as_review():
    append_to_digest(screenshot_filename="a.png", title="t", collection_id=INBOX_ID, week="2026-W35")
    append_to_digest(screenshot_filename="b.png", title="t", collection_id="tech-to-try", week="2026-W35")
    legacy = DIGESTS_DIR / "2026-W20.md"
    legacy.write_text("# Week of May 11, 2026\n\n## Needs Review\n- **Old** (x) — y\n  ![](../screenshots/old.png)\n")

    listed = {d["week"]: d for d in list_digests()}

    assert listed["2026-W35"]["entry_count"] == 2
    assert listed["2026-W35"]["needs_review"] == 1
    assert listed["2026-W20"]["needs_review"] == 1
    assert list(listed) == ["2026-W35", "2026-W20"]
    assert digest_filenames() == {"a.png", "b.png", "old.png"}


def test_a_user_created_collection_gets_its_own_heading():
    create_collection("Books to read")
    append_to_digest(screenshot_filename="c.png", title="Dune", collection_id="books-to-read", week="2026-W35")
    assert "## Books to read" in get_digest("2026-W35")


def test_remove_drops_the_entry_wherever_it_is():
    append_to_digest(screenshot_filename="a.png", title="t", collection_id="tech-to-try", week="2026-W35")
    assert remove_entry("a.png") is True
    assert "a.png" not in get_digest("2026-W35")
    assert remove_entry("a.png") is False
