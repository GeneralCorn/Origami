"""Centralized configuration loaded from environment variables.

All tunables live here. Copy .env.example → .env.local and adjust.
"""

import os
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent

# ── Anthropic ────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
HAIKU_MODEL: str = os.getenv("HAIKU_MODEL", "claude-haiku-4-5-20251001")
SONNET_MODEL: str = os.getenv("SONNET_MODEL", "claude-sonnet-4-6")

# ── Ollama (for VLMs) ───────────────────────────────────────────
OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")
OLLAMA_VLM_MODEL: str = os.getenv("OLLAMA_VLM_MODEL", "qwen2.5-vl:7b")
OLLAMA_TIMEOUT: float = float(os.getenv("OLLAMA_TIMEOUT", "120"))

# ── Screenshots & Digests ──────────────────────────────────────
SCREENSHOTS_DIR: Path = _BACKEND_DIR / "screenshots"
DIGESTS_DIR: Path = _BACKEND_DIR / "digests"

# ── Embeddings ───────────────────────────────────────────────────
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "bge-small-en-v1.5")

# ── ChromaDB ─────────────────────────────────────────────────────
CHROMA_DIR: Path = Path(os.getenv("CHROMA_DIR", str(_BACKEND_DIR / "chroma_data")))
CHROMA_COLLECTION: str = os.getenv("CHROMA_COLLECTION", "documents")

# ── Frontend / CORS ──────────────────────────────────────────────
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

# ── Ingestion ────────────────────────────────────────────────────
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "300"))
