"""Upload dedup and the "already processed" definition.

Nothing here reaches the VLM or the embedder: the collection stays empty,
which is exactly the state that made both defects visible.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import DIGESTS_DIR, SCREENSHOTS_DIR
import routes.screenshots as screenshots
from services.digest import append_to_digest

_PNG = b"\x89PNG\r\n\x1a\n fake pixels"


@pytest.fixture
def client():
    for directory in (SCREENSHOTS_DIR, DIGESTS_DIR):
        for path in directory.iterdir():
            path.unlink()

    app = FastAPI()
    app.include_router(screenshots.router, prefix="/api")
    return TestClient(app)


def _upload(client, content: bytes, name: str = "shot.png"):
    return client.post("/api/screenshots/upload",
                       files={"files": (name, content, "image/png")}).json()[0]


def test_identical_bytes_upload_once(client):
    """A screenshot does not enter Chroma until /process runs, so a
    Chroma-only dedup left every pending capture outside the window,
    which is the whole window that matters for a capture taken twice."""
    first = _upload(client, _PNG)
    second = _upload(client, _PNG)

    assert first["status"] == "pending"
    assert second["status"] == "duplicate"
    assert second["filename"] == first["filename"]
    assert len(list(SCREENSHOTS_DIR.iterdir())) == 1


def test_the_same_bytes_under_a_different_extension_are_one_screenshot(client):
    """Two files whose names differ only by extension share a stem, and a
    shared stem is what let one screenshot's segments overwrite another's."""
    first = _upload(client, _PNG, "shot.png")
    second = _upload(client, _PNG, "shot.jpg")

    assert second["status"] == "duplicate"
    assert second["filename"] == first["filename"]


def test_different_bytes_upload_separately(client):
    first = _upload(client, _PNG)
    second = _upload(client, _PNG + b" different")

    assert second["status"] == "pending"
    assert second["filename"] != first["filename"]


def test_a_screenshot_recorded_only_in_a_digest_is_not_pending(client):
    """The upgrade case: main never wrote screenshots to Chroma, so a
    store-only check reverted the user's whole capture history to pending
    and re-ran the local VLM over all of it, appending a second copy of
    every digest entry."""
    legacy = SCREENSHOTS_DIR / "cccccccc-0000-0000-0000-000000000003.png"
    legacy.write_bytes(_PNG)
    append_to_digest(
        {"title": "Old capture", "category": "news", "confidence": "high",
         "description": "processed before this branch existed"},
        legacy.name,
        week="2026-W30",
    )

    pending = client.get("/api/screenshots/pending").json()

    assert [entry["filename"] for entry in pending] == []


def test_an_unprocessed_screenshot_is_still_pending(client):
    uploaded = _upload(client, _PNG)

    pending = client.get("/api/screenshots/pending").json()

    assert [entry["filename"] for entry in pending] == [uploaded["filename"]]
