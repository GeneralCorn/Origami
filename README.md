# Origami

Local AI research assistant. Upload PDFs, take Markdown notes, and chat with an LLM that has context over your documents and notes.

**Stack:** FastAPI + LangGraph + ChromaDB + Ollama (backend) | Next.js 16 + React 19 + AI SDK v6 (frontend)

## Prerequisites

- [Ollama](https://ollama.com/) installed and running
- [Bun](https://bun.sh/) (v1.3+)
- [Python](https://www.python.org/) 3.13+
- [uv](https://docs.astral.sh/uv/) (Python package manager)

## Gallery

Light Theme:

![Lightmode](./images/lightmode.png)

Dark Theme:

![Darkmode](./images/darkmode.png)

## Setup

### 1. Ollama

Install Ollama and pull the default model:

```bash
# macOS
brew install ollama

# Start the Ollama server (runs on port 11434)
ollama serve

# In a separate terminal, pull the default model
ollama pull deepseek-r1:8b
```

Make sure `ollama serve` is running before starting the backend.

### 2. Backend

```bash
cd backend

# Create virtual environment and install dependencies
uv sync

# Copy the example env file and adjust if needed
cp .env.example .env.local

# Start the FastAPI server (runs on port 8000)
uv run uvicorn main:app --reload
```

### 3. Frontend

```bash
cd frontend

# Install dependencies
bun install

# Copy the example env file and adjust if needed
cp .env.example .env.local

# Start the dev server (runs on port 3000)
bun run dev
```

### 4. Open the app

Visit [http://localhost:3000](http://localhost:3000).

## Configuration

All config is driven by `.env.local` files (git-ignored). Each directory ships a `.env.example` that you copy and edit. **Only edit `.env.local` — never commit it.** If you add a new variable, update `.env.example` too so others can see what's available.

### Backend (`backend/.env.local`)

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `deepseek-r1:8b` | LLM used for chat, agent, and ingestion |
| `OLLAMA_TIMEOUT` | `120` | Request timeout in seconds |
| `EMBEDDING_MODEL` | `bge-small-en-v1.5` | Sentence-transformer for ChromaDB (re-ingest if changed) |
| `CHROMA_DIR` | `chroma_data` | Path to ChromaDB storage |
| `CHROMA_COLLECTION` | `documents` | ChromaDB collection name |
| `FRONTEND_URL` | `http://localhost:3000` | Allowed CORS origin |
| `CHUNK_SIZE` | `1200` | Characters per chunk during ingestion |
| `CHUNK_OVERLAP` | `300` | Overlap between chunks |

### Frontend (`frontend/.env.local`)

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend API URL |

### Switching models

```bash
ollama pull qwen2.5:7b
# then in backend/.env.local:
OLLAMA_MODEL=qwen2.5:7b
# restart the backend
```

### Adding a new env variable

1. Add it to `backend/config.py` with an `os.getenv()` default
2. Add it to `backend/.env.example` with a comment
3. Add it to your local `backend/.env.local`

## Project Structure

```
Origami/
├── backend/              # FastAPI + Python
│   ├── main.py           # App entry, CORS, routers
│   ├── config.py         # Centralized env var config
│   ├── .env.example      # Template for .env.local
│   ├── routes/           # API endpoints (chat, upload, notes, documents)
│   ├── services/         # Ollama, ChromaDB, RAG, ingestion
│   ├── prompts/          # LLM prompt templates
│   ├── notes/            # Markdown note files
│   └── pyproject.toml
├── frontend/             # Next.js + React
│   ├── app/              # Pages and API routes
│   ├── components/       # Chat, sidebar, UI components
│   ├── lib/api/          # Backend API client
│   ├── .env.example      # Template for .env.local
│   └── package.json
└── package.json          # Root workspace
```
