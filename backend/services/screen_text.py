"""Telling screenshot content from screenshot chrome, without a model.

An iPhone capture opens with the status bar and closes with a tab bar, and
neither has anything to do with why the screenshot was taken. PRODUCT_
DIRECTION.md settles what to do about it: keep the bytes, fix the ranking.
The full OCR stays in the sidecar record, and only the lines worth a vector
reach the embedder. The rules here are the static half of that, the part
that needs no corpus; services.rag adds the frequency half at query time.
"""

import re
from collections.abc import Iterable

# "9:41", "09:41", "9.41", "9:41 AM"
_TIME_RE = re.compile(r"^\s*\d{1,2}[:.]\d{2}(\s*[AaPp]\.?[Mm]\.?)?\s*$")
# "100%", "87 %"
_BATTERY_RE = re.compile(r"^\s*\d{1,3}\s*%\s*$")
# Radio indicators OCR reads as their own line.
_SIGNAL_RE = re.compile(r"^\s*(5G\+?|LTE|4G|3G|E|Wi-?Fi|SOS|No Service|\.{3,})\s*$", re.IGNORECASE)
# The whole status bar read as one row: a clock, then anything, then a
# battery or radio token at the end.
_STATUS_ROW_RE = re.compile(
    r"^\s*\d{1,2}[:.]\d{2}(\s*[AaPp]\.?[Mm]\.?)?\b.*\b(\d{1,3}\s*%|5G\+?|LTE|4G|Wi-?Fi)\s*$",
    re.IGNORECASE,
)
# A line with no letter or digit at all: OCR reading icons as punctuation.
_GLYPHS_ONLY_RE = re.compile(r"^[^\w]*$")

# Single controls that appear on every screen of the applications that show
# them. Matched on the whole line, lowercased, so "Share this recipe" is
# content and "Share" is chrome.
CHROME_WORDS: frozenset[str] = frozenset({
    "back", "done", "cancel", "close", "search", "share", "edit", "more",
    "see all", "see more", "show more", "read more", "learn more",
    "home", "library", "for you", "following", "explore", "profile",
    "settings", "notifications", "messages", "inbox", "discover",
    "reply", "repost", "retweet", "like", "comment", "save", "send", "post",
    "subscribe", "subscribed", "follow", "next", "previous", "menu",
    "ok", "yes", "no", "skip", "continue", "allow", "don't allow",
    "sign in", "log in", "sign up", "open", "install", "get", "update",
    "select", "copy", "paste", "delete", "filter", "sort", "view all",
    "play", "pause", "download", "my list", "watch now", "add to list",
    "buy now", "add to cart", "add to bag", "checkout", "apply",
})


def _is_status_token(token: str) -> bool:
    return bool(
        _TIME_RE.match(token)
        or _BATTERY_RE.match(token)
        or _SIGNAL_RE.match(token)
        or _GLYPHS_ONLY_RE.match(token)
    )


def is_status_bar(line: str) -> bool:
    """The iPhone status bar, whether OCR split it into tokens or kept it as a row.

    A row is the status bar when every whitespace-separated token is a
    clock, a battery level, a radio indicator or an icon read as
    punctuation. "5G 100%" therefore counts, and "5G networks explained"
    does not.
    """
    stripped = line.strip()
    if not stripped:
        return False
    if (
        _TIME_RE.match(stripped)
        or _BATTERY_RE.match(stripped)
        or _SIGNAL_RE.match(stripped)
        or _STATUS_ROW_RE.match(stripped)
    ):
        return True
    return all(_is_status_token(token) for token in stripped.split())


# The back control at the top of most screens: a chevron, which OCR reads
# as "‹", "<" or "«", then "Back" or the name of the previous screen.
_BACK_CONTROL_RE = re.compile(r"^[‹«<←]\s*\S+(\s+\S+)?$")


def is_chrome(line: str) -> bool:
    """A control label, the back control, or an icon read as punctuation."""
    stripped = line.strip()
    if not stripped or _GLYPHS_ONLY_RE.match(stripped) or _BACK_CONTROL_RE.match(stripped):
        return True
    return stripped.lower().rstrip(".:›>") in CHROME_WORDS


def content_lines(lines: Iterable[str], *, min_chars: int = 3) -> list[str]:
    """The lines worth embedding, in reading order, with the chrome dropped.

    Consecutive duplicates collapse because a tab bar label read twice, or
    a repeated header, adds nothing to a vector and a lot to a blockquote.
    Nothing here is lost: the caller keeps the full OCR in the record.
    """
    kept: list[str] = []
    for raw in lines:
        line = " ".join(raw.split())
        if len(line) < min_chars or is_status_bar(line) or is_chrome(line):
            continue
        if kept and kept[-1].casefold() == line.casefold():
            continue
        kept.append(line)
    return kept


def derive_title(lines: Iterable[str], *, max_chars: int = 80) -> str:
    """A title from the text alone, for when no model has named the screenshot.

    The first content line carrying a letter. Headlines sit at the top of
    almost every screen, and a wrong-but-honest first line beats a model
    call the fast path is trying to avoid.
    """
    for line in content_lines(lines):
        if re.search(r"[A-Za-zÀ-￿]", line):
            return line[:max_chars].rstrip()
    return ""
