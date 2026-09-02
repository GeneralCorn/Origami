"""Collections: the categories screenshots are filed into, and their notes."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import collections

router = APIRouter()
logger = logging.getLogger(__name__)


class CreateCollectionRequest(BaseModel):
    name: str
    description: str = ""
    keywords: list[str] = []


class UpdateCollectionRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    keywords: list[str] | None = None


@router.get("/collections")
async def list_all():
    return [c.to_dict() for c in collections.list_collections()]


@router.post("/collections", status_code=201)
async def create(req: CreateCollectionRequest):
    try:
        created = collections.create_collection(req.name, req.description, req.keywords)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return created.to_dict()


@router.patch("/collections/{collection_id}")
async def update(collection_id: str, req: UpdateCollectionRequest):
    try:
        updated = collections.update_collection(
            collection_id, name=req.name, description=req.description, keywords=req.keywords,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Collection not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return updated.to_dict()


@router.delete("/collections/{collection_id}")
async def delete(collection_id: str):
    try:
        deleted = collections.delete_collection(collection_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"deleted": True}
