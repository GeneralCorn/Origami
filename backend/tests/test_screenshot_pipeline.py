"""The pipeline end to end, with every engine faked and the store recorded.

The fake_collection fixture stands in for Chroma; a fake OCR engine stands
in for Vision or RapidOCR; a fake analyze_screenshot stands in for Ollama.
What is real is the classifier, the collections store, the notes, the
digest and the record, which is exactly the part that has to compose.
"""

import pytest

from config import COLLECTIONS_FILE, DIGESTS_DIR, NOTES_DIR, OCR_DIR, SCREENSHOTS_DIR
import services.ocr as ocr_service
import services.screenshot_pipeline as pipeline
from services.collections import INBOX_ID, get_collection, find_entry_collection
from services.digest import get_digest, week_holding
from services.ocr import OcrLine, OcrResult, load_record
from services.screenshot_pipeline import Stage, forget, process_screenshot, recategorize

NETFLIX_LINES = ("9:41", "Netflix", "Severance", "Season 2, Episode 3", "Who Is Alive?", "IMDb 8.7 2025 TV-MA", "Play")
PLAIN_LINES = ("Mark and Helly search the severed floor.",)


class FakeOcr:
    name = "fake_ocr"

    def __init__(self, lines):
        self.lines = lines
        self.calls = 0

    def recognize(self, path):
        self.calls += 1
        return OcrResult(engine=self.name, lines=tuple(OcrLine(t, 0.95) for t in self.lines), width=1179, height=2556, elapsed_s=0.5)


class FakeVlm:
    def __init__(self, result: dict, fail: bool = False):
        self.result = result
        self.fail = fail
        self.calls: list[dict] = []

    async def __call__(self, path, *, ocr_text=None, collections=()):
        self.calls.append({"ocr_text": ocr_text, "collections": [c.id for c in collections]})
        if self.fail:
            raise RuntimeError("ollama fell over")
        return dict(self.result)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, fake_collection):
    for directory in (SCREENSHOTS_DIR, DIGESTS_DIR, NOTES_DIR, OCR_DIR):
        for path in directory.iterdir():
            if path.is_file():
                path.unlink()
    if COLLECTIONS_FILE.exists():
        COLLECTIONS_FILE.unlink()
    pipeline.reset_jobs()
    ocr_service.override_engine(None)
    monkeypatch.setattr(pipeline, "_embedder_factory", lambda: None)
    monkeypatch.setattr(pipeline, "set_collection", lambda file_id, cid: True)
    yield
    ocr_service.override_engine(None, resolved=False)
    pipeline.reset_jobs()


@pytest.fixture
def ollama_down(monkeypatch):
    async def down(*, force=False):
        return False
    monkeypatch.setattr(pipeline, "check_ollama_health", down)


@pytest.fixture
def ollama_up(monkeypatch):
    async def up(*, force=False):
        return True
    monkeypatch.setattr(pipeline, "check_ollama_health", up)


def _shot(name="aaaa.png") -> "Path":
    from pathlib import Path

    path: Path = SCREENSHOTS_DIR / name
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + name.encode())
    return path


def _segments(fake_collection, name):
    return [(rid, doc, meta) for rid, doc, meta in fake_collection.records if meta["file_id"] == name]


def _note(collection_id: str) -> str:
    note_id = get_collection(collection_id).note_id
    return (NOTES_DIR / f"{note_id}.md").read_text() if note_id else ""


# ── The fast path ─────────────────────────────────────────────────


async def test_ocr_alone_files_indexes_and_records_in_one_pass(fake_collection, ollama_down):
    ocr_service.override_engine(FakeOcr(NETFLIX_LINES))
    path = _shot()

    job = await process_screenshot(path)

    assert job.stage == Stage.DONE
    assert job.collection == "shows-to-watch"
    assert job.title == "Netflix"
    assert job.ocr_engine == "fake_ocr"
    assert job.method == "keywords"
    assert job.captioned is False

    segments = _segments(fake_collection, path.name)
    assert [m["modality"] for _, _, m in segments] == ["ocr"]
    _, doc, meta = segments[0]
    assert "9:41" not in doc and "Severance" in doc
    assert meta["collection"] == "shows-to-watch"
    assert meta["ocr_engine"] == "fake_ocr"
    assert meta["ocr_confidence"] == 0.95
    assert meta["title"] == "Netflix"

    assert "### Netflix" in _note("shows-to-watch")
    assert "> Season 2, Episode 3" in _note("shows-to-watch")
    assert "## Shows to watch\n- **Netflix**" in get_digest(week_holding(path.name))

    record = load_record(path.name)
    assert record["collection"] == "shows-to-watch"
    assert record["ocr"]["engine"] == "fake_ocr"
    assert record["text"].startswith("9:41\nNetflix")
    assert record["vision"] is None
    assert record["note_id"] == get_collection("shows-to-watch").note_id


async def test_unplaceable_text_lands_in_the_inbox_not_a_guess(fake_collection, ollama_down):
    ocr_service.override_engine(FakeOcr(PLAIN_LINES))

    job = await process_screenshot(_shot())

    assert job.stage == Stage.DONE
    assert job.collection == INBOX_ID
    assert "Mark and Helly" in _note(INBOX_ID)


# ── No way to read it ─────────────────────────────────────────────


async def test_no_engine_and_no_ollama_leaves_the_screenshot_pending(fake_collection, ollama_down):
    path = _shot()

    job = await process_screenshot(path)

    assert job.stage == Stage.ERROR
    assert "Ollama" in job.error
    assert _segments(fake_collection, path.name) == []
    assert load_record(path.name) is None
    assert list(NOTES_DIR.glob("*.md")) == []


# ── The VLM reads when there is no engine ─────────────────────────


async def test_without_an_engine_the_vlm_transcribes_and_its_vote_counts(fake_collection, ollama_up, monkeypatch):
    vlm = FakeVlm({
        "title": "Attention Is All You Need on arXiv",
        "description": "The arXiv abstract page of the transformer paper.",
        "extracted_text": "arxiv.org/abs/1706.03762\nAttention Is All You Need",
        "collection": "papers-to-read",
        "source_app": "safari",
        "confidence": "high",
    })
    monkeypatch.setattr(pipeline, "analyze_screenshot", vlm)
    path = _shot()

    job = await process_screenshot(path)

    assert job.stage == Stage.DONE
    assert job.ocr_engine == "vlm"
    assert job.collection == "papers-to-read"
    assert "vlm" in job.method
    assert job.captioned is True
    assert vlm.calls == [{"ocr_text": None, "collections": [c for c in vlm.calls[0]["collections"]]}]
    modalities = sorted(m["modality"] for _, _, m in _segments(fake_collection, path.name))
    assert modalities == ["caption", "ocr"]
    assert "The arXiv abstract page" in _note("papers-to-read")


# ── The caption pass ──────────────────────────────────────────────


async def test_the_caption_pass_adds_a_segment_renames_and_refiles(fake_collection, ollama_up, monkeypatch):
    """OCR files a plain line in the inbox; the VLM, having seen the
    picture, moves it to shows and gives it a real title."""
    ocr_service.override_engine(FakeOcr(PLAIN_LINES))
    vlm = FakeVlm({
        "title": "Severance episode synopsis",
        "description": "An episode page for Severance on a streaming service.",
        "collection": "shows-to-watch",
        "source_app": "netflix",
        "confidence": "high",
    })
    monkeypatch.setattr(pipeline, "analyze_screenshot", vlm)
    path = _shot()

    job = await process_screenshot(path)

    assert job.stage == Stage.DONE and job.captioned
    assert job.collection == "shows-to-watch"
    assert job.title == "Severance episode synopsis"
    assert vlm.calls[0]["ocr_text"] == PLAIN_LINES[0]

    segments = {m["modality"]: (rid, doc, m) for rid, doc, m in _segments(fake_collection, path.name)}
    assert set(segments) == {"caption", "ocr"}
    assert segments["caption"][0] == f"{path.name}-0"
    assert segments["caption"][2]["content_source"] == "generated"
    assert segments["ocr"][2]["collection"] == "shows-to-watch"
    assert segments["ocr"][2]["title"] == "Severance episode synopsis"

    assert find_entry_collection(path.name) == "shows-to-watch"
    assert path.name not in _note(INBOX_ID)
    assert "An episode page for Severance" in _note("shows-to-watch")
    digest = get_digest(week_holding(path.name))
    assert "## Inbox" not in digest
    assert "- **Severance episode synopsis** (netflix)" in digest
    assert load_record(path.name)["vision"]["source_app"] == "netflix"


async def test_a_failed_caption_leaves_the_indexed_item_alone(fake_collection, ollama_up, monkeypatch):
    ocr_service.override_engine(FakeOcr(NETFLIX_LINES))
    monkeypatch.setattr(pipeline, "analyze_screenshot", FakeVlm({}, fail=True))
    path = _shot()

    job = await process_screenshot(path)

    assert job.stage == Stage.DONE
    assert job.captioned is False
    assert job.collection == "shows-to-watch"
    assert [m["modality"] for _, _, m in _segments(fake_collection, path.name)] == ["ocr"]


async def test_enrichment_can_be_switched_off(fake_collection, ollama_up, monkeypatch):
    ocr_service.override_engine(FakeOcr(NETFLIX_LINES))
    vlm = FakeVlm({"title": "t", "description": "d", "collection": "shows-to-watch", "source_app": "x", "confidence": "high"})
    monkeypatch.setattr(pipeline, "analyze_screenshot", vlm)

    job = await process_screenshot(_shot(), enrich=False)

    assert job.stage == Stage.DONE and not job.captioned
    assert vlm.calls == []


# ── Jobs ──────────────────────────────────────────────────────────


async def test_a_screenshot_in_flight_is_not_started_twice(fake_collection, ollama_down):
    import asyncio

    started = 0

    class Slow:
        name = "slow"

        def recognize(self, path):
            nonlocal started
            started += 1
            import time
            time.sleep(0.05)
            return OcrResult(engine="slow", lines=(OcrLine("Severance season episode imdb", 0.9),), width=1, height=1, elapsed_s=0)

    ocr_service.override_engine(Slow())
    path = _shot()

    first, second = await asyncio.gather(process_screenshot(path), process_screenshot(path))

    assert started == 1
    assert first is second
    assert len(pipeline.jobs()) == 1
    assert pipeline.in_flight() == set()


# ── Moving and forgetting ─────────────────────────────────────────


async def test_recategorize_moves_store_note_digest_and_record(fake_collection, ollama_down, monkeypatch):
    ocr_service.override_engine(FakeOcr(PLAIN_LINES))
    moved: list[tuple[str, str]] = []
    monkeypatch.setattr(pipeline, "set_collection", lambda file_id, cid: moved.append((file_id, cid)) or True)
    path = _shot()
    await process_screenshot(path)
    assert find_entry_collection(path.name) == INBOX_ID

    record = await recategorize(path.name, "shows-to-watch")

    assert moved == [(path.name, "shows-to-watch")]
    assert record["collection"] == "shows-to-watch"
    assert record["classification"]["method"] == "manual"
    assert find_entry_collection(path.name) == "shows-to-watch"
    assert "> Mark and Helly search the severed floor." in _note("shows-to-watch")
    assert "## Shows to watch" in get_digest(week_holding(path.name))
    assert pipeline.job_for(path.name).collection == "shows-to-watch"
    with pytest.raises(KeyError):
        await recategorize(path.name, "cryptozoology")


async def test_forget_removes_record_note_entry_and_digest_line(fake_collection, ollama_down):
    ocr_service.override_engine(FakeOcr(NETFLIX_LINES))
    path = _shot()
    await process_screenshot(path)
    week = week_holding(path.name)

    await forget(path.name)

    assert load_record(path.name) is None
    assert path.name not in _note("shows-to-watch")
    assert path.name not in (get_digest(week) or "")
    assert pipeline.job_for(path.name) is None
