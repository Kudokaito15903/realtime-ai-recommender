from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from loguru import logger

# Import both old and new chatbot services
from services.chatbot_service import ChatbotService
from domain.chatbot.chatbot import ChatbotOrchestrator
import time

router = APIRouter()


class ChatRequest(BaseModel):
    user_id: Optional[str] = None
    query: str
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    top_k: Optional[int] = 5


class ChatRequestV2(BaseModel):
    """New chatbot API request model"""
    message: str
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


# Legacy endpoint (using old ChatbotService)
@router.post("/chat")
async def chat(req: ChatRequest):
    """Legacy chatbot endpoint - using ChatbotService"""
    try:
        svc = ChatbotService()
        answer, contexts, intent = svc.answer(
            req.query, top_k=req.top_k, session_id=req.session_id or f"eval_session_{int(time.time())}"
        )

        return {
            "answer": answer,
            "contexts": contexts,
            "intent": intent,
            "capabilities": {
                "product_info": "Trả lời về thông tin sản phẩm",
                "compare": "So sánh sản phẩm",
                "policy": "Thông tin chính sách",
                "cskh": "Chăm sóc khách hàng tự động",
            },
        }
    except Exception as e:
        logger.error(f"Error in legacy chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# New endpoint (using ChatbotOrchestrator)
@router.post("/chat/v2")
async def chat_v2(req: ChatRequestV2):
    """
    New chatbot endpoint using ChatbotOrchestrator.
    
    Features:
    - Intent classification
    - RAG retrieval from vector database
    - Context-aware responses
    - Conversation history management
    """
    try:
        chatbot = ChatbotOrchestrator()
        
        response = await chatbot.process_message(
            message=req.message,
            conversation_id=req.conversation_id,
            user_id=req.user_id,
            context=req.context,
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error in chat v2 endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/capabilities")
async def get_capabilities():
    """Get chatbot capabilities"""
    return {
        "intents": {
            "product_info": "Trả lời về thông tin, tính năng, cấu hình sản phẩm",
            "compare": "So sánh nhiều sản phẩm với nhau",
            "policy": "Giải thích chính sách (bảo hành, đổi trả, thanh toán, vận chuyển)",
            "cskh": "Hỗ trợ khách hàng (kiểm tra đơn hàng, tài khoản, mật khẩu)",
            "general": "Chào hỏi, chitchat, câu hỏi chung",
        },
        "features": [
            "Intent classification",
            "RAG retrieval from vector database",
            "Context-aware responses",
            "Conversation history",
            "Multi-namespace vector search (products, rag_chunks, content)",
        ],
        "endpoints": {
            "legacy": "/chatbot/chat",
            "v2": "/chatbot/chat/v2",
        },
    }
