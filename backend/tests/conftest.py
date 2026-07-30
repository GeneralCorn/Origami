"""Test-wide isolation.

Both environment variables are set at conftest import time, before any test
module imports `config`, because config resolves DATA_DIR and creates its
directory tree at import. Setting them later would point the suite at the
user's real store.
"""

import os
import shutil
import tempfile

_DATA_DIR = tempfile.mkdtemp(prefix="origami-tests-")
os.environ["ORIGAMI_DATA_DIR"] = _DATA_DIR
os.environ["CHROMA_DIR"] = os.path.join(_DATA_DIR, "chroma_data")
os.environ["ORIGAMI_MODEL_STUB"] = "1"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("ORIGAMI_CHEAP_FINAL", None)
os.environ.pop("ORIGAMI_LOOPS_BY_ROUTE", None)

import pytest


@pytest.fixture(autouse=True)
def clean_ledger():
    """Give every test an empty usage directory."""
    from config import USAGE_DIR

    if USAGE_DIR.exists():
        shutil.rmtree(USAGE_DIR)
    USAGE_DIR.mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture
def fake_collection(monkeypatch):
    """A recorder standing in for Chroma.

    A real add would embed, and embedding downloads a model the offline
    test suite must not need. The fastembed model is loaded lazily on
    first __call__, so importing services.chroma stays safe.
    """

    class Recorder:
        """Enough of the Collection surface for index_item.

        upsert replaces by id rather than appending, because that is the
        behaviour index_item now depends on: chromadb's add is a silent
        no-op on an existing id, and a recorder that appended would let a
        regression back to add pass.
        """

        def __init__(self):
            self.records = []

        def _index_of(self, record_id):
            for position, record in enumerate(self.records):
                if record[0] == record_id:
                    return position
            return -1

        def upsert(self, ids, documents, metadatas):
            record = (ids[0], documents[0], metadatas[0])
            position = self._index_of(ids[0])
            if position >= 0:
                self.records[position] = record
            else:
                self.records.append(record)

        def get(self, where=None, include=None):
            file_id = (where or {}).get("file_id")
            matched = [
                record for record in self.records
                if file_id is None or record[2].get("file_id") == file_id
            ]
            return {"ids": [record[0] for record in matched]}

        def delete(self, ids):
            self.records = [record for record in self.records if record[0] not in set(ids)]

    recorder = Recorder()
    monkeypatch.setattr("services.indexing.get_collection", lambda: recorder)
    return recorder
