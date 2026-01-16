from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from services.chatbot_service import ChatbotService
import time
router = APIRouter()
# Trigger reload for caching update v2

class ChatRequest(BaseModel):
    user_id: Optional[str] = None
    query: str
    session_id: Optional[str] = None
    top_k: Optional[int] = 5

session_id = f"eval_session_{int(time.time())}"


@router.post("/chat")
async def chat(req: ChatRequest):
    try:
        svc = ChatbotService()
        answer, contexts, intent =  svc.answer(req.query, top_k=req.top_k, session_id=session_id)
        
        return {
            "answer": answer,
            "contexts": contexts,
            "intent": intent,
            "capabilities": {
                "product_info": "Trả lời về thông tin sản phẩm",
                "compare": "So sánh sản phẩm",
                "policy": "Thông tin chính sách",
                "cskh": "Chăm sóc khách hàng tự động"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
