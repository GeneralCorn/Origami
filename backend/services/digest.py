"""Weekly digest: a chronological log of what was captured, by collection.

Digest files are markdown at DATA_DIR/digests/{ISO_WEEK}.md, one heading
per collection. The collection notes (services.collections) are where a
screenshot is *kept*; the digest is where the week is *read back*, and it
survives as the record of screenshots processed before the store did.
"""

import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from config import DIGESTS_DIR
from services import collections
from services.collections import INBOX_ID
from services.text_utils import as_text

logger = logging.getLogger(__name__)

# The heading the pre-collections pipeline used for low-confidence entries.
# Still read, never written.
LEGACY_REVIEW_HEADING = "Needs Review"

# Every write is a read, an edit and a write of one week's file, and a
# batch drop makes several of them at the same moment.
_lock = threading.Lock()


def _current_week() -> str:
    """Return ISO week string like '2026-W10'."""
    now = datetime.now(timezone.utc)
    return f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"


def _week_start_date(week_str: str) -> str:
    """Convert '2026-W10' to a human-readable 'March 9, 2026'."""
    year, w = week_str.split("-W")
    dt = datetime.strptime(f"{year}-W{int(w)}-1", "%G-W%V-%u")
    return dt.strftime("%B %-d, %Y")


def _digest_path(week: str | None = None) -> Path:
    week = week or _current_week()
    return DIGESTS_DIR / f"{week}.md"


def _ensure_digest(week: str | None = None) -> Path:
    path = _digest_path(week)
    week = week or _current_week()
    if not path.exists():
        path.write_text(f"# Week of {_week_start_date(week)}\n", encoding="utf-8")
    return path


def heading_for(collection_id: str) -> str:
    """The digest heading for a collection: its display name.

    Model output decides the collection id, and the id is resolved against
    the store before it gets here, so an invented category can never write
    a heading of its own. Anything unknown files under the inbox.
    """
    collection = collections.get_collection(collection_id)
    if collection is None:
        collection = collections.inbox()
    return " ".join(collection.name.split())


def collection_for_heading(heading: str) -> str:
    """The inverse: a heading read back from a digest to a collection id."""
    cleaned = heading.strip()
    if cleaned == LEGACY_REVIEW_HEADING:
        return INBOX_ID
    for collection in collections.list_collections():
        if collection.name.strip().lower() == cleaned.lower():
            return collection.id
    return INBOX_ID


def _entry_line(title: str, source_app: str, description: str, screenshot_filename: str) -> str:
    title = " ".join(as_text(title).split()) or "Untitled"
    source = " ".join(as_text(source_app).split()) or "unknown"
    description = " ".join(as_text(description).split())
    return f"- **{title}** ({source}) — {description}\n  ![](../screenshots/{screenshot_filename})\n"


def _insert_under(content: str, heading: str, entry: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}$", content, re.MULTILINE)
    if match:
        next_heading = re.search(r"^## ", content[match.end():], re.MULTILINE)
        insert_pos = match.end() + next_heading.start() if next_heading else len(content)
        before = content[:insert_pos].rstrip("\n")
        return before + "\n" + entry + "\n" + content[insert_pos:]
    return content.rstrip("\n") + f"\n\n## {heading}\n{entry}"


def append_to_digest(
    *,
    screenshot_filename: str,
    title: str,
    collection_id: str,
    source_app: str = "",
    description: str = "",
    week: str | None = None,
) -> str:
    """Append (or replace) a screenshot's entry under its collection heading.

    Idempotent by screenshot filename, so the caption pass can rewrite the
    line the OCR pass wrote a few seconds earlier. Returns the week.
    """
    week = week or _current_week()
    heading = heading_for(collection_id)
    entry = _entry_line(title, source_app, description, screenshot_filename)
    with _lock:
        path = _ensure_digest(week)
        content, _ = _cut_entry(path.read_text(encoding="utf-8"), screenshot_filename)
        path.write_text(_insert_under(content, heading, entry), encoding="utf-8")
    logger.info("Digest %s: %s under '%s'", week, screenshot_filename, heading)
    return week


def get_digest(week: str) -> str | None:
    path = _digest_path(week)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _section(content: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}$", content, re.MULTILINE)
    if not match:
        return ""
    rest = content[match.end():]
    next_h = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: next_h.start()] if next_h else rest


def list_digests() -> list[dict]:
    """List all available weekly digests, newest first.

    needs_review counts the inbox, and the "Needs Review" heading the
    pre-collections pipeline wrote, so an old digest reads the same way.
    """
    digests = []
    inbox_heading = heading_for(INBOX_ID)
    for path in DIGESTS_DIR.glob("*.md"):
        week = path.stem
        content = path.read_text(encoding="utf-8")
        entry_count = len(re.findall(r"^- \*\*", content, re.MULTILINE))
        needs_review = sum(
            len(re.findall(r"^- \*\*", _section(content, heading), re.MULTILINE))
            for heading in {inbox_heading, LEGACY_REVIEW_HEADING}
        )
        digests.append({
            "week": week,
            "label": _week_start_date(week),
            "entry_count": entry_count,
            "needs_review": needs_review,
        })
    digests.sort(key=lambda d: d["week"], reverse=True)
    return digests


def digest_filenames() -> set[str]:
    """Every screenshot filename any digest already has an entry for.

    The store is the record of what was processed, but it only became the
    record on this branch: every screenshot a user processed before it
    exists in a digest and nowhere else. Reading the digests keeps that
    history visible, so an upgrade does not re-run the VLM over the
    user's whole capture history and append a second copy of every entry.
    """
    processed: set[str] = set()
    for path in DIGESTS_DIR.glob("*.md"):
        content = path.read_text(encoding="utf-8")
        for match in re.finditer(r"!\[]\(\.\./screenshots/(.+?)\)", content):
            processed.add(match.group(1))
    return processed


_ENTRY_TEMPLATE = r"^- \*\*.*?\n  !\[]\(\.\./screenshots/{name}\)\n"


def _cut_entry(content: str, screenshot_name: str) -> tuple[str, str | None]:
    """Remove a screenshot's entry wherever it sits. Returns (content, entry)."""
    pattern = re.compile(_ENTRY_TEMPLATE.format(name=re.escape(screenshot_name)), re.MULTILINE)
    match = pattern.search(content)
    if not match:
        return content, None
    entry = match.group(0)
    content = content[: match.start()] + content[match.end():]
    return _drop_empty_sections(content), entry


def _drop_empty_sections(content: str) -> str:
    """Remove any "## heading" whose section no longer holds an entry."""
    for match in list(re.finditer(r"^## (.+)$", content, re.MULTILINE))[::-1]:
        section = _section(content, match.group(1))
        if not re.search(r"^- \*\*", section, re.MULTILINE):
            end = match.end() + len(section)
            content = content[: match.start()].rstrip("\n") + "\n" + content[end:].lstrip("\n")
    return content


def week_holding(screenshot_name: str) -> str | None:
    """Which week's digest has this screenshot's entry, if any."""
    pattern = re.compile(_ENTRY_TEMPLATE.format(name=re.escape(screenshot_name)), re.MULTILINE)
    for path in sorted(DIGESTS_DIR.glob("*.md"), reverse=True):
        if pattern.search(path.read_text(encoding="utf-8")):
            return path.stem
    return None


def move_entry(week: str | None, screenshot_name: str, new_collection_id: str) -> bool:
    """Move a screenshot's entry under another collection's heading.

    With week=None the digests are searched newest first. Returns False
    when no entry exists anywhere.
    """
    week = week or week_holding(screenshot_name)
    if not week:
        return False
    path = _digest_path(week)
    if not path.exists():
        return False
    heading = heading_for(new_collection_id)
    with _lock:
        content, entry = _cut_entry(path.read_text(encoding="utf-8"), screenshot_name)
        if entry is None:
            return False
        path.write_text(_insert_under(content, heading, entry), encoding="utf-8")
    return True


def remove_entry(screenshot_name: str) -> bool:
    """Drop a screenshot from whichever digest holds it (the screenshot was deleted)."""
    week = week_holding(screenshot_name)
    if not week:
        return False
    path = _digest_path(week)
    with _lock:
        content, entry = _cut_entry(path.read_text(encoding="utf-8"), screenshot_name)
        if entry is None:
            return False
        path.write_text(content, encoding="utf-8")
    return True
