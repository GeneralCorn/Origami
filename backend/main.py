import logging
import os
import secrets
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load .env.local before any other imports that read config. A packaged
# build ships the backend inside a read-only signed bundle, so the user's
# own file lives in the writable data dir and the one next to this module
# is only the dev fallback. load_dotenv never overrides a variable that is
# already set, so the launcher's environment still wins over both files.
_BACKEND_DIR = Path(__file__).resolve().parent
_DATA_DIR = Path(os.getenv("ORIGAMI_DATA_DIR", str(_BACKEND_DIR)))
load_dotenv(_DATA_DIR / ".env.local")
load_dotenv(_BACKEND_DIR / ".env.local")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Ensure [LATENCY] logs from agent + chat are visible
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from config import FRONTEND_URL, EXTRA_ALLOWED_ORIGINS, AUTH_TOKEN, MODEL_STUB
from services.migrate import run_migrations
from services.schema import SCHEMA_VERSION
from routes.chat import router as chat_router
from routes.chats import router as chats_router
from routes.documents import router as documents_router
from routes.notes import router as notes_router
from routes.upload import router as upload_router
from routes.screenshots import router as screenshots_router
from routes.snippets import router as snippets_router
from routes.usage import router as usage_router

logger = logging.getLogger(__name__)


def _migrate() -> None:
    """Bring a store that predates the Item/Segment schema onto v2.

    Runs on a worker thread, off the startup path. The whole migration is
    a full-store copy plus a corpus-wide metadata rewrite, and at import
    time all of it landed between process start and the ORIGAMI_PORT= line
    that desktop/main/sidecar.ts allows 30s for. Measured at 6.9s on 30k
    records, so it crosses that deadline somewhere past 100k chunks, and
    sooner on a volume that cannot clone blocks. The app then fails to
    launch with no sign that a migration was the reason.

    Serving before it finishes is safe because services.rag resolves every
    schema field through services.schema.read_schema_fields, whose legacy
    defaults are facts about the pre-Phase-3 pipeline rather than guesses.
    An unmigrated record therefore reads as untrusted rather than as
    missing; it only looks stale to the re-embed job.
    """
    try:
        logger.info(f"Schema v{SCHEMA_VERSION} migration: {run_migrations()}")
    except Exception as exc:
        logger.error(f"Schema v{SCHEMA_VERSION} migration failed: {exc}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if MODEL_STUB:
        logger.warning(
            "ORIGAMI_MODEL_STUB is set: every model call is answered from a local "
            "stub and no request reaches the API. Answers are not real."
        )
    threading.Thread(target=_migrate, name="origami-migrate", daemon=True).start()
    yield


app = FastAPI(title="Origami API", version="0.1.0", lifespan=lifespan)


if AUTH_TOKEN:
    _AUTH_TOKEN_BYTES = AUTH_TOKEN.encode("utf-8")

    @app.middleware("http")
    async def require_auth_token(request: Request, call_next):
        """Reject any request that lacks the launch-scoped shared secret.

        The token arrives as `Authorization: Bearer <token>` from fetch
        calls, or as a `token` query parameter for resources the browser
        loads via src attributes (images, the PDF iframe).
        """
        header = request.headers.get("authorization", "")
        provided = header[7:] if header.startswith("Bearer ") else ""
        if not provided:
            provided = request.query_params.get("token", "")
        # Compared as bytes: compare_digest raises TypeError on str inputs
        # holding non-ASCII, and `provided` is caller-controlled.
        if not secrets.compare_digest(provided.encode("utf-8"), _AUTH_TOKEN_BYTES):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)


# Added after the auth middleware so CORS wraps it: preflights are
# answered before auth runs and 401 responses still carry CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, *EXTRA_ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")
app.include_router(chats_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(notes_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(screenshots_router, prefix="/api")
app.include_router(snippets_router, prefix="/api")
app.include_router(usage_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}


def run() -> None:
    """Run the server, announcing the bound port on stdout.

    Binds the socket before starting uvicorn so that ORIGAMI_PORT=0
    (OS-assigned port) can be resolved and reported to a supervising
    process such as the Electron main process.
    """
    import socket
    import sys

    import uvicorn

    from config import HOST, PORT

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, PORT))
    bound_port = sock.getsockname()[1]
    sys.stdout.write(f"ORIGAMI_PORT={bound_port}\n")
    sys.stdout.flush()

    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=bound_port))
    server.run(sockets=[sock])


if __name__ == "__main__":
    run()
