"""Upload dedup, the "already processed" definition, and the pipeline's HTTP surface.

Nothing here reaches an OCR engine, the VLM or the embedder: the pipeline
entry point is replaced with a recorder, which is exactly the boundary the
routes are responsible for.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import COLLECTIONS_FILE, DIGESTS_DIR, NOTES_DIR, OCR_DIR, SCREENSHOTS_DIR
import routes.collections as collections_routes
import routes.screenshots as screenshots
import services.screenshot_pipeline as pipeline
from services.digest import append_to_digest
from services.ocr import save_record

_PNG = b"\x89PNG\r\n\x1a\n fake pixels"


@pytest.fixture
def client(monkeypatch):
    for directory in (SCREENSHOTS_DIR, DIGESTS_DIR, OCR_DIR, NOTES_DIR):
        for path in directory.iterdir():
            if path.is_file():
                path.unlink()
    if COLLECTIONS_FILE.exists():
        COLLECTIONS_FILE.unlink()
    pipeline.reset_jobs()

    async def healthy(*, force=False):
        return False

    monkeypatch.setattr(screenshots, "check_ollama_health", healthy)
    monkeypatch.setattr(screenshots, "engine_name", lambda: "fake_ocr")

    app = FastAPI()
    app.include_router(screenshots.router, prefix="/api")
    app.include_router(collections_routes.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def recorded_pipeline(monkeypatch):
    calls: list[str] = []

    async def fake_process(path, *, enrich=None):
        calls.append(path.name)
        job = pipeline.Job(filename=path.name, started_at="now", updated_at="now")
        job.title, job.collection = "Recorded", "inbox"
        job.advance(pipeline.Stage.DONE)
        pipeline._jobs[path.name] = job
        return job

    monkeypatch.setattr(pipeline, "process_screenshot", fake_process)
    return calls


def _upload(client, content: bytes, name: str = "shot.png", **params):
    return client.post("/api/screenshots/upload", params=params,
                       files={"files": (name, content, "image/png")}).json()[0]


# ── Upload and dedup ──────────────────────────────────────────────


def test_identical_bytes_upload_once(client, recorded_pipeline):
    first = _upload(client, _PNG)
    second = _upload(client, _PNG)

    assert first["status"] == "processing"
    assert second["status"] == "duplicate"
    assert second["filename"] == first["filename"]
    assert len(list(SCREENSHOTS_DIR.iterdir())) == 1


def test_the_same_bytes_under_a_different_extension_are_one_screenshot(client, recorded_pipeline):
    first = _upload(client, _PNG, "shot.png")
    second = _upload(client, _PNG, "shot.jpg")

    assert second["status"] == "duplicate"
    assert second["filename"] == first["filename"]


def test_different_bytes_upload_separately(client, recorded_pipeline):
    first = _upload(client, _PNG)
    second = _upload(client, _PNG + b" different")

    assert second["status"] == "processing"
    assert second["filename"] != first["filename"]


def test_upload_starts_the_pipeline_unless_told_not_to(client, recorded_pipeline):
    processed = _upload(client, _PNG)
    parked = _upload(client, _PNG + b"2", process="false")

    assert processed["status"] == "processing"
    assert parked["status"] == "pending"
    assert recorded_pipeline == [processed["filename"]]


# ── Pending and status ────────────────────────────────────────────


def test_a_screenshot_recorded_only_in_a_digest_is_not_pending(client):
    """The upgrade case: main never wrote screenshots to Chroma, so a
    store-only check reverted the user's whole capture history to pending
    and re-ran the VLM over all of it, appending a second copy of every
    digest entry."""
    legacy = SCREENSHOTS_DIR / "cccccccc-0000-0000-0000-000000000003.png"
    legacy.write_bytes(_PNG)
    append_to_digest(
        screenshot_filename=legacy.name,
        title="Old capture",
        collection_id="inbox",
        description="processed before this branch existed",
        week="2026-W30",
    )

    pending = client.get("/api/screenshots/pending").json()

    assert [entry["filename"] for entry in pending] == []


def test_an_unprocessed_screenshot_is_still_pending(client):
    uploaded = _upload(client, _PNG, process="false")

    pending = client.get("/api/screenshots/pending").json()

    assert [entry["filename"] for entry in pending] == [uploaded["filename"]]
    assert pending[0]["stage"] is None


def test_status_reports_jobs_engines_and_pending(client, recorded_pipeline):
    uploaded = _upload(client, _PNG)

    body = client.get("/api/screenshots/status").json()

    assert body["engines"] == {"ocr": "fake_ocr", "vision": False}
    assert body["pending"] == 1  # the recorder never indexes, so it stays pending
    assert [job["filename"] for job in body["jobs"]] == [uploaded["filename"]]
    assert body["jobs"][0]["stage"] == "done"


def test_process_runs_every_pending_screenshot_and_summarises(client, recorded_pipeline):
    _upload(client, _PNG, process="false")
    _upload(client, _PNG + b"2", process="false")

    body = client.post("/api/screenshots/process").json()

    assert body["processed"] == 2
    assert body["failed"] == 0
    assert body["needs_review"] == 2
    assert len(recorded_pipeline) == 2


# ── One screenshot ────────────────────────────────────────────────


def test_detail_and_text_come_from_the_record(client):
    uploaded = _upload(client, _PNG, process="false")
    save_record(uploaded["filename"], {
        "screenshot": uploaded["filename"], "title": "Severance", "collection": "shows-to-watch",
        "text": "Severance\nSeason 2", "content_lines": ["Severance", "Season 2"],
    })

    detail = client.get(f"/api/screenshots/{uploaded['filename']}").json()
    text = client.get(f"/api/screenshots/{uploaded['filename']}/text")

    assert detail["title"] == "Severance"
    assert detail["collection"] == "shows-to-watch"
    assert detail["on_disk"] is True
    assert detail["indexed"] is False
    assert text.status_code == 200
    assert text.text == "Severance\nSeason 2"
    assert text.headers["content-type"].startswith("text/plain")


def test_unknown_screenshots_are_404_and_traversal_is_400(client):
    assert client.get("/api/screenshots/nope.png").status_code == 404
    assert client.get("/api/screenshots/nope.png/text").status_code == 404
    assert client.get("/api/screenshots/..%2Fnotes%2Fx.md/text").status_code in (400, 404)


def test_change_collection_validates_both_sides(client, monkeypatch):
    async def fake_recategorize(name, collection_id):
        if collection_id == "cryptozoology":
            raise KeyError(collection_id)
        return {"collection": collection_id, "note_id": "n1"}

    monkeypatch.setattr(pipeline, "recategorize", fake_recategorize)
    uploaded = _upload(client, _PNG, process="false")

    ok = client.patch(f"/api/screenshots/{uploaded['filename']}/collection", json={"collection_id": "shows-to-watch"})
    bad = client.patch(f"/api/screenshots/{uploaded['filename']}/collection", json={"collection_id": "cryptozoology"})
    missing = client.patch("/api/screenshots/missing.png/collection", json={"collection_id": "shows-to-watch"})

    assert ok.json() == {"status": "moved", "collection": "shows-to-watch", "note_id": "n1"}
    assert bad.status_code == 404
    assert missing.status_code == 404


def test_legacy_digest_recategorize_maps_to_the_same_move(client, monkeypatch):
    seen = {}

    async def fake_recategorize(name, collection_id):
        seen.update(name=name, collection_id=collection_id)
        return {"collection": collection_id, "note_id": ""}

    monkeypatch.setattr(pipeline, "recategorize", fake_recategorize)

    body = client.patch("/api/digests/2026-W35/recategorize",
                        json={"screenshot_name": "a.png", "new_category": "Shows to watch"}).json()

    assert seen == {"name": "a.png", "collection_id": "shows-to-watch"}
    assert body["collection"] == "shows-to-watch"


def test_delete_forgets_everything(client, monkeypatch):
    forgotten = []

    async def fake_forget(name):
        forgotten.append(name)

    monkeypatch.setattr(pipeline, "forget", fake_forget)
    monkeypatch.setattr(screenshots, "delete_chunks", lambda name: 3)
    uploaded = _upload(client, _PNG, process="false")

    body = client.delete(f"/api/screenshots/{uploaded['filename']}").json()

    assert body == {"deleted": True, "deleted_chunks": 3}
    assert forgotten == [uploaded["filename"]]
    assert not (SCREENSHOTS_DIR / uploaded["filename"]).exists()


# ── Collections ───────────────────────────────────────────────────


def test_collections_crud_over_http(client):
    listed = client.get("/api/collections").json()
    assert [c["id"] for c in listed][-1] == "inbox"

    created = client.post("/api/collections", json={"name": "Books to read", "keywords": ["goodreads"]})
    assert created.status_code == 201
    assert created.json()["id"] == "books-to-read"

    duplicate = client.post("/api/collections", json={"name": "books to read"})
    assert duplicate.status_code == 400

    updated = client.patch("/api/collections/books-to-read", json={"description": "Novels."})
    assert updated.json()["description"] == "Novels."
    assert client.patch("/api/collections/nope", json={"name": "x"}).status_code == 404

    assert client.delete("/api/collections/books-to-read").json() == {"deleted": True}
    assert client.delete("/api/collections/books-to-read").status_code == 404
    assert client.delete("/api/collections/inbox").status_code == 400
