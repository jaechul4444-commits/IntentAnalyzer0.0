from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.service.search_service import search_service

router = APIRouter(prefix="/api/data")

class SearchRequest(BaseModel):
    query: str

@router.post("/search")
async def search_data(request: SearchRequest):
    try:
        result = await search_service.search(request.query)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
