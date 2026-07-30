"""Item and Segment: the shared schema beneath every source.

Chroma stores flat scalar metadata per record, so Item fields are
denormalised onto every one of its Segments. That is deliberate:
ARCHITECTURE_V2 section 6 wants source, time range and trust to be cheap
pre-filters, and a filter cannot join.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from config import DATA_DIR

SCHEMA_VERSION = 2

SourceType = Literal["pdf", "note", "snippet", "screenshot", "photo", "calendar", "message"]
Modality = Literal["text", "ocr", "caption", "transcript"]
ContentSource = Literal["extracted", "generated"]
Origin = Literal["self", "counterparty", "public", "unknown"]
Trust = Literal["trusted", "untrusted"]
ContextStatus = Literal["ok", "failed", "skipped", "unknown"]


@dataclass(frozen=True)
class Provenance:
    origin: Origin
    trust: Trust
    channel: str
    author: str = ""


@dataclass(frozen=True)
class Item:
    """The addressable thing a human would name: one PDF, one screenshot.

    provenance has no default on purpose. "Provenance on every write path"
    is enforced by this constructor rather than by discipline, so a caller
    cannot build an Item without deciding whether its bytes are trusted.
    """

    id: str
    source_type: SourceType
    source_id: str
    title: str
    created_at: str
    ingested_at: str
    provenance: Provenance
    raw_ref: str


@dataclass(frozen=True)
class Segment:
    ordinal: int
    modality: Modality
    content: str
    content_source: ContentSource
    embedding_model: str
    context_status: ContextStatus
    span: dict[str, int | str] = field(default_factory=dict)


def segment_id(item_id: str, ordinal: int) -> str:
    """The Chroma record id. Byte-identical to the pre-Phase-3 format."""
    return f"{item_id}-{ordinal}"


def provenance_for_upload() -> Provenance:
    """A PDF the user chose from their own machine.

    origin is `self` per ARCHITECTURE_V2 section 7 step 2. trust is
    `untrusted` because section 3 scopes trust to the bytes rather than to
    the person: a paper the user downloaded was written by someone else
    and its text can carry instructions aimed at the agent.
    """
    return Provenance(origin="self", trust="untrusted", channel="upload")


def provenance_for_screenshot() -> Provenance:
    """A screenshot, of content Origami cannot attribute.

    trust is `untrusted` and section 3 names this case verbatim: "the OCR
    of a screenshot of a web page" is on its untrusted list.

    origin is `unknown` rather than `self`. The upload factory's `self`
    rests on the user having chosen a file from their own machine, which
    says something about the file. A screenshot is a picture of an
    application surface whose content may be the user's own draft, a
    colleague's message, or a public page, and the only signal available
    is the VLM's source_app guess, which is model output and must never
    decide a security-adjacent field.
    """
    return Provenance(origin="unknown", trust="untrusted", channel="screenshot")


def provenance_for_snippet() -> Provenance:
    """Text the user captured from somewhere else.

    Section 3 reads "content Origami did not receive from the user
    directly is untrusted", and its own gloss settles what "directly"
    means: "the text inside a PDF someone emailed" is untrusted even
    though the user handed the PDF over. The test is authorship, not
    delivery, because the rule "is a statement about whether the bytes
    could contain instructions aimed at the agent". Pasted bytes can.
    Typing is the only act section 3 calls trusted, and pasting into
    Origami's own textarea is not typing.
    """
    return Provenance(origin="unknown", trust="untrusted", channel="snippet")


def data_relative(path: Path) -> str:
    """raw_ref as a DATA_DIR-relative POSIX path.

    Absolute paths do not survive the dev-to-packaged move, where DATA_DIR
    changes from the backend folder to Application Support.
    """
    return path.resolve().relative_to(DATA_DIR.resolve()).as_posix()


def segment_metadata(item: Item, segment: Segment, extra: dict | None = None) -> dict:
    """Flatten an Item plus a Segment into one Chroma metadata record."""
    meta = {
        "schema_version": SCHEMA_VERSION,
        "file_id": item.id,
        "source_type": item.source_type,
        "source_id": item.source_id,
        "title": item.title,
        "created_at": item.created_at,
        "ingested_at": item.ingested_at,
        "raw_ref": item.raw_ref,
        "prov_origin": item.provenance.origin,
        "prov_trust": item.provenance.trust,
        "prov_channel": item.provenance.channel,
        "prov_author": item.provenance.author,
        "chunk_index": segment.ordinal,
        "modality": segment.modality,
        "content_source": segment.content_source,
        "embedding_model": segment.embedding_model,
        "context_status": segment.context_status,
    }
    meta.update(segment.span)
    if extra:
        meta.update(extra)
    # Chroma rejects an empty list value. The on-disk shape for an untagged
    # document is the key being absent, which every reader already handles
    # through meta.get("tags", []).
    return {key: value for key, value in meta.items() if not (isinstance(value, list) and not value)}


_LEGACY_DEFAULTS = {
    "source_type": "pdf",
    "source_id": "",
    "created_at": "",
    "ingested_at": "",
    "raw_ref": "",
    "modality": "text",
    "content_source": "extracted",
    "embedding_model": "",
    "prov_origin": "self",
    "prov_trust": "untrusted",
    "prov_channel": "upload",
    "prov_author": "",
    "context_status": "unknown",
}


def read_schema_fields(meta: dict) -> dict:
    """Schema fields for one record, filling v1 records with legacy defaults.

    A v1 record predates Phase 3, when ingest.py was the only writer, so
    every default here is a fact about that pipeline rather than a guess.

    Two defaults are load-bearing. `embedding_model` is "" rather than the
    current model, so an unrecorded vector sorts *into* the re-embed job's
    work queue rather than out of it. `prov_trust` is "untrusted", so a
    record that predates provenance fails closed.
    """
    return {key: meta.get(key, default) for key, default in _LEGACY_DEFAULTS.items()}
