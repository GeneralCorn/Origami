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
