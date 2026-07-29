import logging
import os
import secrets
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

from config import FRONTEND_URL, EXTRA_ALLOWED_ORIGINS, AUTH_TOKEN
from services.migrate import backfill_schema_v2
from routes.chat import router as chat_router
from routes.chats import router as chats_router
from routes.documents import router as documents_router
from routes.notes import router as notes_router
from routes.upload import router as upload_router
from routes.screenshots import router as screenshots_router

app = FastAPI(title="Origami API", version="0.1.0")

# Records that predate the Item/Segment schema get their v2 metadata here.
# A failure must not stop the port binding: every reader resolves missing
# schema fields through services.schema.read_schema_fields, so an
# unmigrated store still serves, it just looks stale to the re-embed job.
try:
    backfill_schema_v2()
except Exception as exc:
    logging.getLogger(__name__).error(f"Schema v2 backfill failed: {exc}", exc_info=True)


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
