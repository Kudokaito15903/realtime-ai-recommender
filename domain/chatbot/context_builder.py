"""
Conversation Manager for managing chatbot conversation history
"""

from typing import Dict, Any, List, Optional
from loguru import logger
import uuid


class ConversationManager:

    def __init__(self):
        self._conversations: Dict[str, Dict[str, Any]] = {}

    async def get_conversation(self, conversation_id: str) -> Dict[str, Any]:
        if conversation_id not in self._conversations:
            self._conversations[conversation_id] = {
                "conversation_id": conversation_id,
                "messages": [],
                "metadata": {
                    "created_at": None,
                    "updated_at": None,
                },
            }
        
        return self._conversations[conversation_id]

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        try:
            conversation = await self.get_conversation(conversation_id)
            
            message = {
                "role": role,
                "content": content,
                "metadata": metadata or {},
            }
            
            conversation["messages"].append(message)
            
            # Update metadata
            import time
            if not conversation["metadata"]["created_at"]:
                conversation["metadata"]["created_at"] = time.time()
            conversation["metadata"]["updated_at"] = time.time()
            
            logger.debug(f"Added message to conversation {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding message: {e}", exc_info=True)
            return False

    async def delete_conversation(self, conversation_id: str) -> bool:
        try:
            if conversation_id in self._conversations:
                del self._conversations[conversation_id]
                logger.debug(f"Deleted conversation {conversation_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting conversation: {e}", exc_info=True)
            return False

    async def list_conversations(
        self, user_id: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        conversations = list(self._conversations.values())
        if user_id:
            conversations = [
                conv for conv in conversations
                if conv.get("metadata", {}).get("user_id") == user_id
            ]        
        conversations.sort(
            key=lambda x: x.get("metadata", {}).get("updated_at", 0),
            reverse=True
        )
        
        summaries = []
        for conv in conversations[:limit]:
            summaries.append({
                "conversation_id": conv["conversation_id"],
                "message_count": len(conv.get("messages", [])),
                "last_message": conv["messages"][-1]["content"][:100] if conv["messages"] else "",
                "metadata": conv.get("metadata", {}),
            })
        
        return summaries
