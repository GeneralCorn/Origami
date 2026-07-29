# Origami

A local-first AI research assistant, becoming a personal knowledge base.

Upload PDFs, write Markdown notes, and chat with an agent that has real context over both. Everything runs on your machine. No API key, no account, no data leaving your computer.

**Today:** a working research assistant for documents and notes.
**Next:** a signed macOS desktop app that ingests from the rest of your life. See [Roadmap](#roadmap).

## Gallery

Light Theme:

![Lightmode](./images/lightmode.png)

Dark Theme:

![Darkmode](./images/darkmode.png)

## What works today

- **PDF ingestion** with a Contextual Retrieval pipeline. Every chunk gets a short LLM-generated blurb situating it in the whole document before embedding, which meaningfully improves retrieval over naive chunking.
- **Vector search** over ChromaDB, ranking contextualized chunks by cosine similarity.
- **A LangGraph research agent** that plans, retrieves, reviews its own findings, and loops until it has enough to answer.
- **Markdown notes**, editable alongside the chat and usable as agent context.
- **Streaming chat** over the Vercel AI SDK protocol, including visible reasoning.
- **Your corpus stays on disk.** `bge-small-en-v1.5` does the embeddings locally and Chroma stores them on your machine. Nothing is uploaded and there is no account.

Reasoning currently runs on Anthropic's API and needs your own key: the agent calls Claude Haiku and Sonnet for planning, retrieval review, and answers, which means retrieved passages are sent to Anthropic on those turns. Ingestion, embedding, and storage stay local. Restoring a local generation path is on the roadmap below, and until it lands, treat "local" as describing where your data lives rather than where inference happens.

**Stack:** FastAPI + LangGraph + ChromaDB (backend), Next.js 16 + React 19 + AI SDK v6 (frontend)

## Roadmap

Origami is being rebuilt as a **signed macOS desktop application** and expanded from a document tool into a multimodal personal knowledge base. Think of an Obsidian-shaped tool with retrieval and an agent behind it, running locally, and cheap enough to leave running.

The full planning work lives in [`docs/`](./docs) and is worth reading before contributing:

| Document | What it covers |
|---|---|
| [ELECTRON_PORT_PLAN.md](./docs/ELECTRON_PORT_PLAN.md) | The five architectural decisions and the phase sequence |
| [ARCHITECTURE_V2.md](./docs/ARCHITECTURE_V2.md) | The Item and Segment model, provenance and taint, migration order |
| [INTEGRATIONS_RESEARCH.md](./docs/INTEGRATIONS_RESEARCH.md) | Per-source research on what can and cannot legitimately be ingested |
| [COST_MODEL.md](./docs/COST_MODEL.md) | Where token spend actually goes, and the levers that reduce it |

### Phases

None of the phases below have been built. They are plans.

| Phase | Work | Status |
|---|---|---|
| Prerequisite | Land the in-flight screenshot and vision work | In flight |
| 0 | Portable backend: `ORIGAMI_DATA_DIR`, drop Torch via fastembed, port on stdout | Planned |
| 1 | Electron shell, Python sidecar, renderer moved from Next.js to Vite | Planned |
| 2 | Packaging, Developer ID signing, notarization, macOS permissions | Planned |
| 3 | Item and Segment schema with provenance on every write path | Planned |
| 4 | Cost controls: tool pruning, no polling, model routing | Planned |
| 5 | Connectors, one at a time, starting with snippets and Calendar | Planned |
| 6 | CodeMirror 6 editor and a lower-density interface | Planned |
| 7 | Static launch site on GitHub Pages | Planned |

### What is deliberately not being built

Three commonly requested sources were researched and rejected, with the reasoning recorded in [INTEGRATIONS_RESEARCH.md](./docs/INTEGRATIONS_RESEARCH.md):

- **Google Photos library sync.** The library-read scopes were removed in March 2025 and now return `403 PERMISSION_DENIED`. Apps can only read media they uploaded themselves. Apple Photos via PhotoKit is the primary photo surface instead, with Google Takeout as the bulk import path.
- **Discord.** Automating a user account is a bannable offence, and a bot account can only see servers it is invited to, never your direct messages.
- **WhatsApp.** No sanctioned route exists for personal message history, and unofficial clients get accounts permanently banned.

Also not planned: a hosted cloud tier, Windows or Linux builds, and any form of account or login on the project's public site.

### The principle underneath all of it

Origami will assemble what Simon Willison calls the [lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/): private data, exposure to content written by other people, and an agent that can reach the network. Because that risk is structural rather than something prompt engineering can fix, provenance and taint tagging land in Phase 3, **before** the first connector exists in Phase 5. Content the user did not write is marked untrusted, and any agent turn that retrieves untrusted content loses its ability to communicate outward.

That ordering is the single most important decision in the roadmap, because retrofitting provenance onto an existing store means re-ingesting everything.

## Prerequisites

- [Ollama](https://ollama.com/) installed and running
- [Bun](https://bun.sh/) (v1.3+)
- [Python](https://www.python.org/) 3.13+
- [uv](https://docs.astral.sh/uv/) (Python package manager)

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

All config is driven by `.env.local` files (git-ignored). Each directory ships a `.env.example` that you copy and edit. **Only edit `.env.local`, never commit it.** If you add a new variable, update `.env.example` too so others can see what's available.

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

Any Ollama-compatible model works. Larger models give better agent reasoning at the cost of speed.

```bash
ollama pull qwen2.5:7b
# then in backend/.env.local:
OLLAMA_MODEL=qwen2.5:7b
# restart the backend
```

Changing `EMBEDDING_MODEL` requires re-ingesting every document, because existing vectors live in a different embedding space. Phase 3 fixes this by recording the embedding model per segment, which turns a full re-ingest into an incremental re-embed.

### Adding a new env variable

1. Add it to `backend/config.py` with an `os.getenv()` default
2. Add it to `backend/.env.example` with a comment
3. Add it to your local `backend/.env.local`

## Project Structure

```
Origami/
├── docs/                 # Roadmap and research (read before contributing)
├── backend/              # FastAPI + Python 3.13
│   ├── main.py           # App entry, CORS, routers
│   ├── config.py         # Centralized env var config
│   ├── routes/           # chat, chats, documents, notes, upload
│   ├── services/
│   │   ├── agent.py      # LangGraph research agent
│   │   ├── ingest.py     # Contextual Retrieval pipeline
│   │   ├── rag.py        # Dense vector search
│   │   ├── chroma.py     # Vector store access
│   │   ├── embeddings.py # bge-small-en-v1.5
│   │   └── ollama.py     # Local LLM streaming
│   ├── prompts/          # Prompt templates
│   ├── notes/            # Markdown note files
│   └── pyproject.toml
├── frontend/             # Next.js 16 + React 19
│   ├── app/              # Pages and API routes
│   ├── components/       # chat, editor, reader, sidebar, database, layout, ui
│   ├── lib/api/          # Backend API client
│   └── package.json
└── package.json
```

Note that `frontend/` becomes the static launch site in Phase 7, and the desktop renderer moves to Vite in Phase 1. If you are reading this after those land, the layout will differ.

## Contributing

The roadmap in [`docs/`](./docs) is the source of truth for direction. Two conventions matter:

- Research claims in those documents are tagged `[VERIFIED]`, `[SECONDARY]`, or `[UNVERIFIED]`. Do not build against an `[UNVERIFIED]` claim without testing it first. The tags exist because an earlier draft of this planning was written without primary sources and had to be discarded.
- Phase ordering is not arbitrary. Phase 3 before Phase 5 in particular is load-bearing, for the reason given above.

## License

MIT. See [LICENSE](./LICENSE).
