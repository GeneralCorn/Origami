"""Weekly digest file management.

Digest files are markdown files at backend/digests/{ISO_WEEK}.md
grouped by category headings.
"""

import re
import logging
from datetime import datetime, timezone
from pathlib import Path

from config import DIGESTS_DIR

logger = logging.getLogger(__name__)

# Categories that map to ## headings (order preserved in file)
CATEGORY_ORDER = [
    "news", "social_media", "code", "documentation",
    "conversation", "recipe", "shopping", "finance", "other",
]


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
    """Get path to a digest file."""
    week = week or _current_week()
    return DIGESTS_DIR / f"{week}.md"


def _ensure_digest(week: str | None = None) -> Path:
    """Create digest file with header if it doesn't exist."""
    path = _digest_path(week)
    week = week or _current_week()
    if not path.exists():
        header = f"# Week of {_week_start_date(week)}\n"
        path.write_text(header, encoding="utf-8")
    return path


def _format_category(cat: str) -> str:
    """Convert category slug to heading: 'social_media' → 'Social Media'."""
    return cat.replace("_", " ").title()


def _category_slug(heading: str) -> str:
    """Convert heading back to slug: 'Social Media' → 'social_media'."""
    return heading.strip().lower().replace(" ", "_")


def append_to_digest(
    vision_result: dict,
    screenshot_filename: str,
    week: str | None = None,
) -> None:
    """Append a screenshot entry under the correct category heading."""
    path = _ensure_digest(week)
    content = path.read_text(encoding="utf-8")

    category = vision_result.get("category", "other").lower().replace(" ", "_")
    confidence = vision_result.get("confidence", "high")
    title = vision_result.get("title", "Untitled")
    source = vision_result.get("source_app", "unknown")
    description = vision_result.get("description", "")

    # Low confidence → file under "Needs Review"
    if confidence == "low":
        heading = "Needs Review"
    else:
        heading = _format_category(category)

    entry = f"- **{title}** ({source}) — {description}\n  ![](../screenshots/{screenshot_filename})\n"

    # Find the heading section and append, or create it
    heading_pattern = re.compile(rf"^## {re.escape(heading)}$", re.MULTILINE)
    match = heading_pattern.search(content)

    if match:
        # Find the end of this section (next ## or EOF)
        next_heading = re.search(r"^## ", content[match.end():], re.MULTILINE)
        if next_heading:
            insert_pos = match.end() + next_heading.start()
        else:
            insert_pos = len(content)
        # Insert entry before next heading (or at end), ensure blank line
        before = content[:insert_pos].rstrip("\n")
        after = content[insert_pos:]
        content = before + "\n" + entry + "\n" + after
    else:
        # Add new section at end
        content = content.rstrip("\n") + f"\n\n## {heading}\n{entry}"

    path.write_text(content, encoding="utf-8")
    logger.info(f"Appended {screenshot_filename} under '{heading}' in {path.name}")


def get_digest(week: str) -> str | None:
    """Read a digest markdown file. Returns None if not found."""
    path = _digest_path(week)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def list_digests() -> list[dict]:
    """List all available weekly digests, newest first."""
    digests = []
    for path in DIGESTS_DIR.glob("*.md"):
        week = path.stem  # e.g. "2026-W10"
        content = path.read_text(encoding="utf-8")
        # Count entries (lines starting with "- **")
        entry_count = len(re.findall(r"^- \*\*", content, re.MULTILINE))
        # Count needs-review entries
        needs_review = 0
        nr_match = re.search(r"^## Needs Review$", content, re.MULTILINE)
        if nr_match:
            section = content[nr_match.end():]
            next_h = re.search(r"^## ", section, re.MULTILINE)
            section = section[:next_h.start()] if next_h else section
            needs_review = len(re.findall(r"^- \*\*", section, re.MULTILINE))

        digests.append({
            "week": week,
            "label": _week_start_date(week),
            "entry_count": entry_count,
            "needs_review": needs_review,
        })
    digests.sort(key=lambda d: d["week"], reverse=True)
    return digests


def move_from_review(week: str, screenshot_name: str, new_category: str) -> bool:
    """Move a screenshot entry from 'Needs Review' to a real category.

    Returns True if the move succeeded.
    """
    path = _digest_path(week)
    if not path.exists():
        return False

    content = path.read_text(encoding="utf-8")

    # Find the entry line in Needs Review by screenshot filename
    entry_pattern = re.compile(
        rf"^- \*\*.*?\n  !\[]\(\.\./screenshots/{re.escape(screenshot_name)}\)\n",
        re.MULTILINE,
    )
    match = entry_pattern.search(content)
    if not match:
        return False

    entry_text = match.group(0)

    # Remove from current position
    content = content[:match.start()] + content[match.end():]

    # Clean up empty "Needs Review" section if no entries left
    nr_match = re.search(r"^## Needs Review\n", content, re.MULTILINE)
    if nr_match:
        after = content[nr_match.end():]
        next_h = re.search(r"^## ", after, re.MULTILINE)
        section = after[:next_h.start()] if next_h else after
        if not re.search(r"^- \*\*", section, re.MULTILINE):
            # Remove the empty heading
            end_pos = nr_match.end() + (next_h.start() if next_h else len(section))
            content = content[:nr_match.start()] + content[end_pos:]

    # Write back, then re-append under correct category
    path.write_text(content, encoding="utf-8")

    # Build a minimal vision_result to reuse append_to_digest
    # Parse the entry to extract fields
    title_match = re.search(r"\*\*(.+?)\*\*", entry_text)
    source_match = re.search(r"\*\* \((.+?)\)", entry_text)
    desc_match = re.search(r"— (.+)$", entry_text.split("\n")[0])

    vision_result = {
        "title": title_match.group(1) if title_match else "Untitled",
        "source_app": source_match.group(1) if source_match else "unknown",
        "description": desc_match.group(1) if desc_match else "",
        "category": new_category,
        "confidence": "high",
    }
    append_to_digest(vision_result, screenshot_name, week=week)
    return True


def get_processed_filenames() -> set[str]:
    """Scan all digest files and return set of screenshot filenames already processed."""
    processed = set()
    for path in DIGESTS_DIR.glob("*.md"):
        content = path.read_text(encoding="utf-8")
        # Match ![](../screenshots/FILENAME)
        for m in re.finditer(r"!\[]\(\.\./screenshots/(.+?)\)", content):
            processed.add(m.group(1))
    return processed
