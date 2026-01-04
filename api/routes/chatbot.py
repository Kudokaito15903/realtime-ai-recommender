from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from services.chatbot_service import ChatbotService

router = APIRouter()

class ChatRequest(BaseModel):
    user_id: Optional[str] = None
    query: str
    top_k: Optional[int] = 5


@router.post("/chat")
async def chat(req: ChatRequest):
    try:
        svc = ChatbotService()
        answer, contexts = await svc.answer(req.query, top_k=req.top_k)
        
        # Detect intent for response metadata
        intent = svc._detect_intent(req.query)
        
        return {
            "answer": answer,
            "contexts": contexts,
            "intent": intent,
            "capabilities": {
                "product_info": "Trả lời về thông tin sản phẩm",
                "compare": "So sánh sản phẩm",
                "policy": "Thông tin chính sách",
                "cskh": "Chăm sóc khách hàng tự động",
                "realtime": "Dữ liệu realtime (tồn kho, giá, đánh giá)"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
