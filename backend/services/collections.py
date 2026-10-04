"""Collections: what a screenshot is *for*, and the note that keeps it.

The digest's old categories (news, meme, code, ...) described what a
screenshot looked like. Nobody screenshots a thing because it is a meme;
they screenshot it because they mean to come back to it: a show to watch,
a library to try, a ticker to keep an eye on, a paper to read. A
collection names that intent, and each one is backed by an ordinary
markdown note in NOTES_DIR that accumulates an entry per screenshot. The
note is the user's: it opens in the editor, it can be rewritten, and the
only thing this module relies on is a pair of HTML-comment markers around
each entry so a recategorised screenshot can be moved without touching
anything the user typed.

The set is user-defined and stored in DATA_DIR/collections.json. A first
read seeds sensible defaults; "inbox" is the one fixed member, because the
classifier needs somewhere honest to put what it cannot place.
"""

import json
import logging
import re
import threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from config import COLLECTIONS_FILE, NOTES_DIR
from services.text_utils import as_text, sanitize_filename

logger = logging.getLogger(__name__)

INBOX_ID = "inbox"

MAX_NAME_CHARS = 60
MAX_DESCRIPTION_CHARS = 500
MAX_KEYWORDS = 64
MAX_KEYWORD_CHARS = 40


@dataclass(frozen=True)
class Collection:
    id: str
    name: str
    description: str
    keywords: tuple[str, ...] = ()
    note_id: str = ""
    builtin: bool = False

    @property
    def embedding_text(self) -> str:
        """What the classifier embeds to stand for this collection."""
        hints = f" Keywords: {', '.join(self.keywords)}." if self.keywords else ""
        return f"{self.name}. {self.description}{hints}"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["keywords"] = list(self.keywords)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Collection":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            keywords=tuple(str(k) for k in data.get("keywords", []) if str(k).strip()),
            note_id=str(data.get("note_id", "")),
            builtin=bool(data.get("builtin", False)),
        )


DEFAULT_COLLECTIONS: tuple[Collection, ...] = (
    Collection(
        id="shows-to-watch",
        name="Shows to watch",
        description=(
            "Television series, films, anime and documentaries someone means to watch: "
            "streaming service pages, trailers, ratings pages and recommendations."
        ),
        keywords=(
            "season", "episode", "imdb", "letterboxd", "rotten tomatoes", "netflix",
            "trailer", "streaming", "hbo", "max", "disney+", "prime video", "apple tv",
            "crunchyroll", "hulu", "anime", "documentary", "film", "movie", "series",
            "cast", "director", "tv-ma", "tv-14", "pg-13", "watchlist", "now streaming",
        ),
    ),
    Collection(
        id="tech-to-try",
        name="Tech to try",
        description=(
            "Software libraries, frameworks, developer tools, models and repositories to "
            "try out: GitHub pages, release notes, install commands, documentation and launch posts."
        ),
        keywords=(
            "github", "npm", "pip install", "uv add", "cargo", "brew install", "framework",
            "library", "sdk", "api", "open source", "open-source", "repo", "repository",
            "release", "changelog", "docs", "cli", "rust", "python", "typescript", "swift",
            "react", "kubernetes", "docker", "hugging face", "model", "benchmark", "v1.0",
            "stars", "fork", "readme", "license", "mit", "apache",
        ),
    ),
    Collection(
        id="markets-to-watch",
        name="Markets to watch",
        description=(
            "Stocks, tickers, ETFs, crypto assets, earnings, sectors and macro trends to keep an "
            "eye on: brokerage screens, price charts, market news and analyst notes."
        ),
        keywords=(
            "stock", "ticker", "nasdaq", "nyse", "s&p", "dow", "earnings", "market cap",
            "shares", "etf", "dividend", "portfolio", "bull", "bear", "fed", "inflation",
            "sector", "industry", "ipo", "crypto", "btc", "eth", "bitcoin", "revenue",
            "guidance", "eps", "pre-market", "after hours", "yield", "valuation", "%",
        ),
    ),
    Collection(
        id="papers-to-read",
        name="Papers to read",
        description=(
            "Research papers, arXiv abstracts, preprints and academic articles to read: "
            "titles with author lists, abstracts, conference pages and citations."
        ),
        keywords=(
            "arxiv", "abstract", "et al", "doi", "neurips", "icml", "iclr", "acl", "cvpr",
            "emnlp", "proceedings", "preprint", "paper", "we propose", "we show",
            "our results", "university", "benchmark", "state-of-the-art", "sota",
            "ablation", "appendix", "citation", "journal", "figure 1", "pdf",
        ),
    ),
    Collection(
        id="places-to-go",
        name="Places to go",
        description=(
            "Restaurants, cafes, bars, hotels, neighbourhoods, trips and travel plans: "
            "map pins, review pages, menus, bookings and itineraries."
        ),
        keywords=(
            "restaurant", "cafe", "café", "bar", "menu", "reservation", "google maps",
            "yelp", "tripadvisor", "hotel", "airbnb", "flight", "itinerary", "address",
            "open until", "opens", "closed", "reviews", "miles away", "km away",
            "directions", "booking", "check-in", "check-out", "michelin",
        ),
    ),
    Collection(
        id="recipes-to-cook",
        name="Recipes to cook",
        description="Recipes and dishes to cook: ingredient lists, method steps, servings and cook times.",
        keywords=(
            "recipe", "ingredients", "tbsp", "tsp", "cup", "cups", "oven", "bake",
            "simmer", "servings", "preheat", "minutes", "garlic", "onion", "butter",
            "flour", "sauce", "marinate", "whisk", "grill", "roast", "season with",
        ),
    ),
    Collection(
        id=INBOX_ID,
        name="Inbox",
        description="Screenshots the classifier could not place with confidence. Sort them by hand.",
        keywords=(),
        builtin=True,
    ),
)

_lock = threading.RLock()


def slugify(name: str) -> str:
    return sanitize_filename(name)[:MAX_NAME_CHARS] or "collection"


def _write(collections: list[Collection]) -> None:
    payload = {"version": 1, "collections": [c.to_dict() for c in collections]}
    tmp = COLLECTIONS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(COLLECTIONS_FILE)


def _read() -> list[Collection]:
    """The stored collections, seeding the defaults on first use.

    The inbox is re-added if a hand-edited file lost it, because every
    other module treats it as the guaranteed fallback.
    """
    with _lock:
        if not COLLECTIONS_FILE.exists():
            _write(list(DEFAULT_COLLECTIONS))
            return list(DEFAULT_COLLECTIONS)
        try:
            data = json.loads(COLLECTIONS_FILE.read_text(encoding="utf-8"))
            raw = data.get("collections", []) if isinstance(data, dict) else data
            collections = [Collection.from_dict(item) for item in raw if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            logger.error("collections.json is unreadable (%s); using defaults without overwriting it", exc)
            return list(DEFAULT_COLLECTIONS)
        collections = [c for c in collections if c.id]
        if not any(c.id == INBOX_ID for c in collections):
            collections.append(next(c for c in DEFAULT_COLLECTIONS if c.id == INBOX_ID))
            _write(collections)
        return collections


def list_collections() -> list[Collection]:
    return _read()


def get_collection(collection_id: str) -> Collection | None:
    for collection in _read():
        if collection.id == collection_id:
            return collection
    return None


def inbox() -> Collection:
    found = get_collection(INBOX_ID)
    assert found is not None  # _read guarantees it
    return found


def collection_ids() -> list[str]:
    return [c.id for c in _read()]


def normalize_collection_id(raw: object) -> str:
    """A model's or a client's idea of a collection, resolved to one that exists.

    Anything unknown files under the inbox. Model output decides this
    value, so it cannot be allowed to mint a collection, a heading, or a
    note by itself.
    """
    slug = as_text(raw).lower().replace("_", "-").replace(" ", "-")
    known = set(collection_ids())
    if slug in known:
        return slug
    # Accept the display name too: "Shows to watch" -> "shows-to-watch".
    by_name = {c.name.lower(): c.id for c in _read()}
    return by_name.get(as_text(raw).lower(), INBOX_ID)


def _clean_keywords(keywords) -> tuple[str, ...]:
    cleaned: list[str] = []
    for keyword in list(keywords or [])[:MAX_KEYWORDS]:
        text = " ".join(str(keyword).split())[:MAX_KEYWORD_CHARS].strip()
        if text and text.lower() not in {k.lower() for k in cleaned}:
            cleaned.append(text)
    return tuple(cleaned)


def create_collection(name: str, description: str = "", keywords=()) -> Collection:
    name = " ".join(name.split())[:MAX_NAME_CHARS]
    if not name:
        raise ValueError("A collection needs a name")
    with _lock:
        collections = _read()
        base = slugify(name)
        collection_id = base
        suffix = 2
        while any(c.id == collection_id for c in collections):
            collection_id = f"{base}-{suffix}"
            suffix += 1
        if any(c.name.lower() == name.lower() for c in collections):
            raise ValueError(f"A collection named {name!r} already exists")
        created = Collection(
            id=collection_id,
            name=name,
            description=" ".join(description.split())[:MAX_DESCRIPTION_CHARS],
            keywords=_clean_keywords(keywords),
        )
        collections.append(created)
        _write(collections)
        logger.info("Created collection %s (%s)", created.id, created.name)
        return created


def update_collection(
    collection_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    keywords=None,
    note_id: str | None = None,
) -> Collection:
    with _lock:
        collections = _read()
        for index, collection in enumerate(collections):
            if collection.id != collection_id:
                continue
            changes: dict = {}
            if name is not None:
                cleaned = " ".join(name.split())[:MAX_NAME_CHARS]
                if not cleaned:
                    raise ValueError("A collection needs a name")
                changes["name"] = cleaned
            if description is not None:
                changes["description"] = " ".join(description.split())[:MAX_DESCRIPTION_CHARS]
            if keywords is not None:
                changes["keywords"] = _clean_keywords(keywords)
            if note_id is not None:
                changes["note_id"] = note_id
            updated = replace(collection, **changes)
            collections[index] = updated
            _write(collections)
            return updated
    raise KeyError(collection_id)


def delete_collection(collection_id: str) -> bool:
    """Remove a collection. Its note stays: it is the user's file."""
    if collection_id == INBOX_ID:
        raise ValueError("The inbox cannot be deleted")
    with _lock:
        collections = _read()
        remaining = [c for c in collections if c.id != collection_id]
        if len(remaining) == len(collections):
            return False
        _write(remaining)
        logger.info("Deleted collection %s", collection_id)
        return True


# ── The note behind a collection ──────────────────────────────────


def _note_path(note_id: str) -> Path:
    return NOTES_DIR / f"{note_id}.md"


def ensure_note(collection: Collection) -> str:
    """The id of the note this collection files into, created on first use.

    Lazy so that a default collection the user never fills does not litter
    the notes list with empty files. If the user deleted the note, a new
    one is made rather than resurrecting the old id.

    Under the lock, and re-read there: a batch drop files several
    screenshots into one collection at once, and without it each of them
    created a note, the last id written won, and the others' entries sat
    in duplicate notes nothing linked to.
    """
    with _lock:
        current = get_collection(collection.id) or collection
        if current.note_id and _note_path(current.note_id).exists():
            return current.note_id
        from routes.notes import create_note_file

        created = create_note_file(current.name)
        update_collection(current.id, note_id=created["id"])
        return created["id"]


def note_for(collection_id: str) -> str:
    collection = get_collection(collection_id)
    return collection.note_id if collection else ""


ENTRY_OPEN = "<!-- origami:screenshot {name} -->"
ENTRY_CLOSE = "<!-- /origami:screenshot {name} -->"
MAX_QUOTE_LINES = 12
MAX_QUOTE_CHARS = 700


@dataclass(frozen=True)
class Entry:
    """One screenshot as it appears in a collection note."""

    screenshot: str
    title: str
    captured_at: str
    source_app: str = ""
    description: str = ""
    lines: tuple[str, ...] = ()


def _inline(text: str) -> str:
    """One line of markdown-safe prose: no newlines, no leading heading marks."""
    return " ".join(text.split()).lstrip("#").strip()


def render_entry(entry: Entry) -> str:
    """The markdown block for one screenshot, between its markers.

    The image is referenced by the same relative path the digest uses, so
    the renderer resolves both the same way. The quoted lines are the
    content lines of the OCR, capped: the full text is in the index and
    the record, and a note is for reading rather than archiving.
    """
    title = _inline(entry.title) or "Untitled screenshot"
    meta = [part for part in (_inline(entry.source_app), entry.captured_at[:10]) if part and part != "unknown"]
    meta.append(f"[screenshot](../screenshots/{entry.screenshot})")
    parts = [
        ENTRY_OPEN.format(name=entry.screenshot),
        f"### {title}",
        f"*{' · '.join(meta)}*",
        "",
        f"![{title}](../screenshots/{entry.screenshot})",
    ]
    description = _inline(entry.description)
    if description:
        parts += ["", description]
    quoted: list[str] = []
    used = 0
    for line in entry.lines:
        clean = _inline(line)
        if not clean:
            continue
        if len(quoted) >= MAX_QUOTE_LINES or used + len(clean) > MAX_QUOTE_CHARS:
            quoted.append("> …")
            break
        quoted.append(f"> {clean}")
        used += len(clean)
    if quoted:
        parts += ["", *quoted]
    parts.append(ENTRY_CLOSE.format(name=entry.screenshot))
    return "\n".join(parts)


def _entry_span(content: str, screenshot: str) -> tuple[int, int] | None:
    pattern = re.compile(
        re.escape(ENTRY_OPEN.format(name=screenshot)) + r".*?" + re.escape(ENTRY_CLOSE.format(name=screenshot)),
        re.DOTALL,
    )
    match = pattern.search(content)
    return (match.start(), match.end()) if match else None


def _tidy(content: str) -> str:
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.rstrip("\n") + "\n"


def upsert_entry(collection_id: str, entry: Entry) -> str:
    """Write the entry into the collection's note, replacing an existing one.

    Idempotent by screenshot, so the caption pass can rewrite the block a
    fast OCR-only pass already appended. Returns the note id. The read,
    edit and write happen under the lock because a batch drop files
    several entries into one note at the same time.
    """
    with _lock:
        collection = get_collection(collection_id) or inbox()
        note_id = ensure_note(collection)
        path = _note_path(note_id)
        content = path.read_text(encoding="utf-8") if path.exists() else f"# {collection.name}\n\n"
        block = render_entry(entry)
        span = _entry_span(content, entry.screenshot)
        if span:
            content = content[: span[0]] + block + content[span[1]:]
        else:
            content = content.rstrip("\n") + "\n\n" + block + "\n"
        path.write_text(_tidy(content), encoding="utf-8")
    logger.info("Filed %s under %s", entry.screenshot, collection.id)
    return note_id


def remove_entry(note_id: str, screenshot: str) -> str | None:
    """Cut the entry's block out of a note. Returns the block, or None if absent."""
    path = _note_path(note_id)
    if not note_id or not path.exists():
        return None
    with _lock:
        content = path.read_text(encoding="utf-8")
        span = _entry_span(content, screenshot)
        if not span:
            return None
        block = content[span[0]:span[1]]
        path.write_text(_tidy(content[: span[0]] + content[span[1]:]), encoding="utf-8")
    return block


def find_entry_collection(screenshot: str) -> str | None:
    """Which collection's note currently holds this screenshot, if any."""
    for collection in _read():
        if not collection.note_id:
            continue
        path = _note_path(collection.note_id)
        if path.exists() and _entry_span(path.read_text(encoding="utf-8"), screenshot):
            return collection.id
    return None


def move_entry(screenshot: str, to_collection_id: str, entry: Entry | None = None) -> str:
    """Relocate a screenshot's entry to another collection's note.

    With an Entry the block is re-rendered; without one the existing block
    is carried over verbatim, edits and all. Returns the destination note id.
    """
    with _lock:
        destination = get_collection(to_collection_id) or inbox()
        block: str | None = None
        for collection in _read():
            if collection.id == destination.id or not collection.note_id:
                continue
            found = remove_entry(collection.note_id, screenshot)
            if found is not None:
                block = found
        if entry is not None:
            return upsert_entry(destination.id, entry)
        note_id = ensure_note(destination)
        path = _note_path(note_id)
        content = path.read_text(encoding="utf-8")
        if _entry_span(content, screenshot):
            return note_id
        if block is None:
            return note_id
        path.write_text(_tidy(content.rstrip("\n") + "\n\n" + block + "\n"), encoding="utf-8")
        return note_id
