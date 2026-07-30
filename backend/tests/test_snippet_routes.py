"""The /api/snippets route's bounds, validation, and interrupted-ingest recovery.

index_item is stubbed throughout: the route's contract is what it accepts,
what it writes to disk, and what it hands the background task. Embedding is
tested elsewhere and would download a model this suite must not need.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import SNIPPETS_DIR
import routes.snippets as snippets


@pytest.fixture
def client(monkeypatch):
    calls: list[tuple] = []

    async def fake_index(item, drafts, *, tags=None, whole_text=""):
        calls.append((item, drafts, tags))
        return len(drafts)

    monkeypatch.setattr(snippets, "index_item", fake_index)
    for path in SNIPPETS_DIR.iterdir():
        path.unlink()

    app = FastAPI()
    app.include_router(snippets.router, prefix="/api")
    test_client = TestClient(app, raise_server_exceptions=False)
    test_client.index_calls = calls
    return test_client


def _files() -> set[str]:
    return {path.name for path in SNIPPETS_DIR.iterdir()}


def test_an_oversized_paste_is_refused(client):
    response = client.post("/api/snippets", json={"text": "x" * (snippets.MAX_TEXT_CHARS + 1)})

    assert response.status_code == 413
    assert _files() == set()


def test_a_paste_at_the_limit_is_accepted(client):
    response = client.post("/api/snippets", json={"text": "x" * snippets.MAX_TEXT_CHARS})

    assert response.status_code == 200


def test_the_caller_supplied_title_is_bounded(client):
    """indexing.py copies the title onto every one of an Item's segments,
    so the store cost is title length times chunk count."""
    response = client.post("/api/snippets", json={"text": "body text", "title": "T" * 200_000})

    assert len(response.json()["title"]) == snippets.MAX_TITLE_CHARS


def test_tags_are_bounded(client):
    response = client.post("/api/snippets", json={
        "text": "body text",
        "tags": ["t" * 500] + [f"tag{i}" for i in range(100)],
    })

    tags = response.json()["tags"]
    assert len(tags) <= snippets.MAX_TAGS
    assert all(len(tag) <= snippets.MAX_TAG_CHARS for tag in tags)


@pytest.mark.parametrize("body", [
    b'{"text": "ordinary body text here", "title": "t \\udfff"}',
    b'{"text": "another body", "tags": ["a \\udc00"]}',
    b'{"text": "abc \\ud800"}',
])
def test_a_lone_surrogate_is_a_400_and_leaves_no_orphan(client, body):
    """A lone surrogate is legal JSON and only raises when something
    encodes it. Reaching the response, that was a 500 raised after the
    handler returned, which is after the .md file was already on disk and
    after nothing could unlink it. No route lists that directory, so the
    file was unreachable and uncollectable."""
    response = client.post("/api/snippets", content=body,
                           headers={"content-type": "application/json"})

    assert response.status_code == 400
    assert _files() == set()


def test_an_interrupted_ingest_can_be_completed_by_re_capturing(client, monkeypatch):
    """find_by_hash matches on the hash the first segment wrote, so a
    truncated Item looked exactly like a complete one and reported the
    re-capture as a duplicate. The user's missing segments were then
    unreachable with no retry path anywhere in the UI or the API."""
    text = "A captured passage worth keeping. " * 40
    first = client.post("/api/snippets", json={"text": text})
    file_id = first.json()["id"]
    expected = first.json()["total_chunks"]

    monkeypatch.setattr(snippets, "find_by_hash",
                        lambda _hash: {"file_id": file_id, "filename": f"{file_id}.md"})
    monkeypatch.setattr(snippets, "item_completion", lambda _id: (1, expected + 3))

    resumed = client.post("/api/snippets", json={"text": text})

    assert resumed.json()["status"] == "processing"
    assert resumed.json()["id"] == file_id


def test_a_complete_item_is_still_reported_as_a_duplicate(client, monkeypatch):
    monkeypatch.setattr(snippets, "find_by_hash",
                        lambda _hash: {"file_id": "already-here", "filename": "already-here.md"})
    monkeypatch.setattr(snippets, "item_completion", lambda _id: (4, 4))

    response = client.post("/api/snippets", json={"text": "a passage"})

    assert response.json() == {"id": "already-here", "duplicate": True, "status": "duplicate"}


def test_an_item_with_no_recorded_total_is_assumed_complete(client, monkeypatch):
    """Every record written before segment_total existed reports 0, and
    guessing "incomplete" there would re-ingest a whole library."""
    monkeypatch.setattr(snippets, "find_by_hash",
                        lambda _hash: {"file_id": "legacy", "filename": "legacy.md"})
    monkeypatch.setattr(snippets, "item_completion", lambda _id: (3, 0))

    assert client.post("/api/snippets", json={"text": "a passage"}).json()["duplicate"] is True
