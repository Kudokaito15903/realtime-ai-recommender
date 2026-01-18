"""
Conversation Manager for managing chatbot conversation history
"""

from typing import Dict, Any, List, Optional
from loguru import logger
import uuid


class ConversationManager:
    """
    Manage conversation history for chatbot.
    
    Features:
    - Store conversation messages
    - Retrieve conversation history
    - Manage conversation metadata
    """

    def __init__(self):
        # Simple in-memory storage (can be replaced with database)
        self._conversations: Dict[str, Dict[str, Any]] = {}

    async def get_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """
        Get conversation by ID.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            Conversation dict with messages and metadata
        """
        if conversation_id not in self._conversations:
            # Create new conversation
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
        """
        Add message to conversation.
        
        Args:
            conversation_id: Conversation ID
            role: Message role (user or assistant)
            content: Message content
            metadata: Additional metadata
            
        Returns:
            True if successful
        """
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
        """
        Delete conversation.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            True if successful
        """
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
        """
        List conversations.
        
        Args:
            user_id: Filter by user ID (optional)
            limit: Maximum number of conversations to return
            
        Returns:
            List of conversation summaries
        """
        conversations = list(self._conversations.values())
        
        # Filter by user_id if provided
        if user_id:
            conversations = [
                conv for conv in conversations
                if conv.get("metadata", {}).get("user_id") == user_id
            ]
        
        # Sort by updated_at descending
        conversations.sort(
            key=lambda x: x.get("metadata", {}).get("updated_at", 0),
            reverse=True
        )
        
        # Return summaries
        summaries = []
        for conv in conversations[:limit]:
            summaries.append({
                "conversation_id": conv["conversation_id"],
                "message_count": len(conv.get("messages", [])),
                "last_message": conv["messages"][-1]["content"][:100] if conv["messages"] else "",
                "metadata": conv.get("metadata", {}),
            })
        
        return summaries
