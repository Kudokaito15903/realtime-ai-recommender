from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from services.content_service import ContentService
from data.schemas import (
    ContentCreate,
    ContentUpdate,
    ContentResponse,
    ContentStatusResponse,
    ContentListResponse,
    ContentSearchResponse,
)

router = APIRouter()


# ------------------------------------------------------------------
# Create
# ------------------------------------------------------------------
@router.post("/", response_model=ContentStatusResponse, status_code=201)
async def create_content(content: ContentCreate):
    try:
        svc = ContentService()
        content_id = svc.create_content(content.dict())
        return {"content_id": content_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# List
# ------------------------------------------------------------------
@router.get("/", response_model=ContentListResponse)
async def list_content(
    category: Optional[str] = Query(None),
    limit: int = Query(100, ge=1),
    page: int = Query(1, ge=1),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    try:
        svc = ContentService()
        results, total = svc.list_content(
            category=category,
            limit=limit,
            page=page,
            search=search,
            status=status,
        )

        has_more = (page * limit) < total

        return {
            "items": results,
            "total": total,
            "limit": limit,
            "page": page,
            "has_more": has_more,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Semantic search
# ------------------------------------------------------------------
@router.get("/search", response_model=ContentSearchResponse)
async def search_content(
    q: str = Query(..., min_length=1),
    category: Optional[str] = Query(None),
    limit: int = Query(20, ge=1),
):
    try:
        svc = ContentService()
        results = svc.search_content(query=q, category=category, limit=limit)

        return {
            "query": q,
            "results": results,
            "count": len(results),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Categories
# ------------------------------------------------------------------
@router.get("/categories", response_model=List[str])
async def get_categories():
    try:
        svc = ContentService()
        return svc.get_categories()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Get by id
# ------------------------------------------------------------------
@router.get("/{content_id}", response_model=ContentResponse)
async def get_content(content_id: str):
    try:
        svc = ContentService()
        content = svc.get_content(content_id)
        if not content:
            raise HTTPException(status_code=404, detail="Content not found")
        return content
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Update
# ------------------------------------------------------------------
@router.put("/{content_id}", response_model=ContentStatusResponse)
async def update_content(content_id: str, content: ContentUpdate):
    try:
        svc = ContentService()
        ok = svc.update_content(content_id, content.dict(exclude_unset=True))
        if not ok:
            raise HTTPException(status_code=404, detail="Content not found")
        return {"content_id": content_id, "status": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------
@router.delete("/{content_id}", response_model=ContentStatusResponse)
async def delete_content(content_id: str):
    try:
        svc = ContentService()
        ok = svc.delete_content(content_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Content not found")
        return {"content_id": content_id, "status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
