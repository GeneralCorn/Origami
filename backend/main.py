import logging
from pathlib import Path

from dotenv import load_dotenv

# Load .env.local before any other imports that read config
_env_file = Path(__file__).resolve().parent / ".env.local"
load_dotenv(_env_file)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure [LATENCY] logs from agent + chat are visible
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from config import FRONTEND_URL, EXTRA_ALLOWED_ORIGINS
from routes.chat import router as chat_router
from routes.chats import router as chats_router
from routes.documents import router as documents_router
from routes.notes import router as notes_router
from routes.upload import router as upload_router
from routes.screenshots import router as screenshots_router

app = FastAPI(title="Origami API", version="0.1.0")

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
