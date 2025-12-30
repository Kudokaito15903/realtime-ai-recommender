from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from services.content_service import ContentService

router = APIRouter()

class ContentCreate(BaseModel):
    title: str
    content: str
    category: str  # e.g., 'faq', 'policy', 'guide', 'blog', 'cskh'
    tags: Optional[List[str]] = []
    status: Optional[str] = "published"  # 'draft', 'published', 'archived'

class ContentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None

@router.post("/", response_model=Dict[str, Any], status_code=201)
async def create_content(content: ContentCreate):
    try:
        svc = ContentService()
        content_id = svc.create_content(content.dict())
        return {"content_id": content_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=Dict[str, Any])
async def list_content(
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(100, description="Maximum number of results"),
    offset: int = Query(0, description="Offset for pagination"),
    search: Optional[str] = Query(None, description="Search in title and content"),
    status: Optional[str] = Query(None, description="Filter by status (draft, published, archived)")
):
    """
    List all content with filtering and search capabilities.
    Returns paginated results with metadata.
    """
    try:
        svc = ContentService()
        results = svc.list_content(
            category=category, 
            limit=limit, 
            offset=offset,
            search=search,
            status=status
        )
        total = len(results)
        return {
            "items": results,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": total >= limit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search", response_model=Dict[str, Any])
async def search_content(
    q: str = Query(..., description="Search query"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(20, description="Maximum number of results")
):
    """
    Semantic search for content using vector similarity.
    """
    try:
        svc = ContentService()
        results = svc.search_content(query=q, category=category, limit=limit)
        return {
            "query": q,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/categories", response_model=List[str])
async def get_categories():
    """
    Get list of all available content categories.
    """
    try:
        svc = ContentService()
        return svc.get_categories()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{content_id}", response_model=Dict[str, Any])
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

@router.put("/{content_id}", response_model=Dict[str, Any])
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

@router.delete("/{content_id}", response_model=Dict[str, Any])
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