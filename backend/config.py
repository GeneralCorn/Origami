"""Centralized configuration loaded from environment variables.

All tunables live here. Copy .env.example → .env.local and adjust.
"""

import os
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent

# ── Ollama ───────────────────────────────────────────────────────
OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")
OLLAMA_TIMEOUT: float = float(os.getenv("OLLAMA_TIMEOUT", "120"))

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
