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

from config import FRONTEND_URL
from routes.chat import router as chat_router
from routes.chats import router as chats_router
from routes.documents import router as documents_router
from routes.notes import router as notes_router
from routes.upload import router as upload_router

app = FastAPI(title="Origami API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")
app.include_router(chats_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(notes_router, prefix="/api")
app.include_router(upload_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
