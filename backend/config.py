"""Centralized configuration loaded from environment variables.

All tunables live here. Copy .env.example → .env.local and adjust.
"""

import os
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent

# ── Data root ────────────────────────────────────────────────────
# Every directory the backend writes lives under DATA_DIR. Unset,
# it is the backend folder itself (the historical dev layout). A
# packaged desktop app sets ORIGAMI_DATA_DIR to a user-writable
# location because it cannot write next to its own binary.
DATA_DIR: Path = Path(os.getenv("ORIGAMI_DATA_DIR", str(_BACKEND_DIR)))

SCREENSHOTS_DIR: Path = DATA_DIR / "screenshots"
DIGESTS_DIR: Path = DATA_DIR / "digests"
UPLOADS_DIR: Path = DATA_DIR / "uploads"
PDFS_DIR: Path = DATA_DIR / "pdfs"
CHATS_DIR: Path = DATA_DIR / "chats"
NOTES_DIR: Path = DATA_DIR / "notes"
CHROMA_DIR: Path = Path(os.getenv("CHROMA_DIR", str(DATA_DIR / "chroma_data")))
MODELS_DIR: Path = DATA_DIR / "models"
SAVED_TAGS_FILE: Path = DATA_DIR / "saved_tags.json"

for _dir in (
    SCREENSHOTS_DIR, DIGESTS_DIR, UPLOADS_DIR, PDFS_DIR,
    CHATS_DIR, NOTES_DIR, CHROMA_DIR, MODELS_DIR,
):
    _dir.mkdir(parents=True, exist_ok=True)

# ── Server ───────────────────────────────────────────────────────
HOST: str = os.getenv("ORIGAMI_HOST", "127.0.0.1")
PORT: int = int(os.getenv("ORIGAMI_PORT", "8000"))

# Optional shared secret. When set, every request must carry it as a
# Bearer token (or ?token= for resources loaded via src attributes).
# Unset, no auth is enforced and the plain dev workflow is unchanged.
AUTH_TOKEN: str = os.getenv("ORIGAMI_AUTH_TOKEN", "")

# ── Anthropic ────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
HAIKU_MODEL: str = os.getenv("HAIKU_MODEL", "claude-haiku-4-5-20251001")
SONNET_MODEL: str = os.getenv("SONNET_MODEL", "claude-sonnet-4-6")

# ── Ollama (for VLMs) ───────────────────────────────────────────
OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")
OLLAMA_VLM_MODEL: str = os.getenv("OLLAMA_VLM_MODEL", "qwen2.5-vl:7b")
OLLAMA_TIMEOUT: float = float(os.getenv("OLLAMA_TIMEOUT", "120"))

# ── Embeddings ───────────────────────────────────────────────────
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "bge-small-en-v1.5")

# ── ChromaDB ─────────────────────────────────────────────────────
CHROMA_COLLECTION: str = os.getenv("CHROMA_COLLECTION", "documents")

# ── Frontend / CORS ──────────────────────────────────────────────
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
EXTRA_ALLOWED_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.getenv("ORIGAMI_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

# ── Ingestion ────────────────────────────────────────────────────
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "300"))
