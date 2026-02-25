# Origami — Architecture Summary

**Purpose:** Local AI research assistant. Users upload PDFs, take notes in Markdown, and chat with an LLM (Ollama) that can use the current note and (eventually) RAG over uploaded documents.

---

## Repo layout

```
Origami/
├── backend/          # FastAPI (Python 3.13)
│   ├── main.py       # App entry, CORS, routers
│   ├── routes/
│   │   ├── chat.py   # POST /api/chat (streaming)
│   │   └── upload.py # POST /api/upload (PDF)
│   └── services/
│       ├── ollama.py # Ollama streaming + <think> tag parsing
│       └── rag.py    # hybrid_search() — stub, no Chroma yet
├── frontend/         # Next.js 16 (App Router), React 19
│   ├── app/
│   │   ├── layout.tsx, page.tsx
│   │   └── api/chat/route.ts   # Proxies /api/chat → backend
│   ├── components/
│   │   ├── layout/   workspace-layout.tsx (resizable editor + chat)
│   │   ├── editor/   markdown-editor.tsx (CodeMirror)
│   │   ├── chat/     chat-panel, chat-input, message, thought, animated-text
│   │   └── sidebar/  document-drawer, document-list, upload-dropzone
│   ├── lib/api/      upload.ts (calls backend /api/upload)
│   └── types/        Document, UploadResponse
```

---

## Backend (FastAPI)

- **Entry:** `main.py` — FastAPI app, CORS for `http://localhost:3000`, mounts routers under `/api`.
- **Endpoints:**
  - `GET /health` — health check.
  - `POST /api/chat` — streaming chat. Body: `{ messages: [{ role, content }], current_note: string }`. Uses `services/ollama.stream_completion()` and `services/rag.hybrid_search()` (stub). Streams **Vercel AI SDK data stream** format: `0:"text"\n`, `g:"reasoning"\n`, then `e:...`, `d:...`.
  - `POST /api/upload` — PDF upload. Saves to `uploads/{uuid}.pdf`. Returns `{ id, filename, size, status: "processing" }`. **No ingestion yet** (no text extraction, chunking, or vector store).
- **Ollama (`services/ollama.py`):** `stream_completion(messages, model)` — `httpx` stream to `http://localhost:11434/api/chat`, default model `deepseek-r1:7b`. Parses `<think>...</think>` in the stream and yields `{"type": "reasoning"|"text", "content": "..."}`.
- **RAG (`services/rag.py`):** `hybrid_search(query)` — **stub**: returns `[]`. Planned: ChromaDB + BM25 + reciprocal rank fusion; not implemented.
- **Dependencies (pyproject.toml):** fastapi, uvicorn, httpx, python-multipart, chromadb, langchain, langchain-community, langchain-ollama, langgraph, pymupdf, rank-bm25.

---

## Frontend (Next.js)

- **Stack:** Next 16, React 19, TypeScript, Tailwind 4, Vercel AI SDK (`@ai-sdk/react`, `ai`), Motion, CodeMirror (@uiw/react-codemirror), react-dropzone, react-resizable-panels, Radix/shadcn-style UI.
- **Fonts:** Inter, JetBrains Mono (layout.tsx).
- **Single page:** `app/page.tsx` renders `WorkspaceLayout`.
- **WorkspaceLayout:** Header with sidebar toggle; resizable horizontal panels: **left** = Markdown editor, **right** = Chat panel. Sidebar = slide-out drawer with upload dropzone and document list. Editor content is debounced (300ms) and passed to chat as `currentNote`.
- **Chat:** `ChatPanel` uses `useChat` from `@ai-sdk/react` with `DefaultChatTransport` pointing at `api: "/api/chat"` and `body: () => ({ current_note: noteRef.current })`. Messages rendered by `Message`; each message has `parts` — `reasoning` → `Thought` (collapsible), `text` → `AnimatedText`.
- **API proxy:** `app/api/chat/route.ts` forwards POST to `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`)/api/chat and streams the response back.
- **Upload:** `lib/api/upload.ts` POSTs to `NEXT_PUBLIC_API_URL/api/upload` with FormData; `UploadDropzone` uses `uploadPDF()` and pushes a `Document` into `DocumentDrawer` state (documents are in-memory only, no persistence).

---

## Data flow

1. **Chat:** User types in `ChatInput` → `sendMessage` → Next.js `/api/chat` → FastAPI `/api/chat` → `hybrid_search(userMessage)` (empty) + `_build_system_prompt(current_note, context_chunks)` + `stream_completion(conversation)` → stream with `0:`, `g:` lines → frontend parses into message parts (text/reasoning) and renders.
2. **Notes:** Editor content (debounced) is sent as `current_note` in every chat request body; backend injects it into the system prompt as “Active Research Notes”.
3. **Upload:** PDF → backend saves to `uploads/{id}.pdf`, returns id/filename/size/status; frontend adds a `Document` to sidebar list. No DB, no RAG ingestion yet.

---

## Notable conventions

- Backend runs on port **8000** (uvicorn default). Frontend expects backend at `NEXT_PUBLIC_API_URL` (dev: `http://localhost:8000`).
- Chat stream format is **Vercel AI SDK data stream**: text = `0:JSON\n`, reasoning = `g:JSON\n`, then end tokens.
- **<think>** from Ollama is parsed server-side and emitted as reasoning parts so the UI can show “thought” blocks separately.
- UI: `border-thin`, `text-muted-foreground`, `ScrollArea`, `ResizablePanelGroup`, Motion for drawer and buttons.

---

## TODOs (from code)

- **Backend:** Implement RAG: PDF text extraction (e.g. PyMuPDF), chunking, embeddings, ChromaDB persistence, then real `hybrid_search` (vector + BM25 + RRF). Optional: background job after upload.
- **Frontend:** Document list is ephemeral; could sync with backend or add a “list documents” API and persistence.

Use this as the codebase context when continuing with ChatGPT or other tools.
