from typing import Dict, Any, List, Optional
from loguru import logger
import time
import uuid

import config
from domain.chatbot.intent_classifier import IntentClassifier
from domain.chatbot.context_builder import ConversationManager
from handlers.product_info import ProductInfoHandler
from handlers.compare import CompareHandler
from handlers.policy import PolicyHandler
from handlers.cskh import CSKHHandler
from handlers.general import GeneralHandler


class ChatbotOrchestrator:
    """
    Main orchestrator for chatbot.

    Flow:
    1. Load conversation history
    2. Classify intent
    3. Route to appropriate handler
    4. Generate response
    5. Save conversation
    6. Track analytics
    """

    def __init__(self):
        self.intent_classifier = IntentClassifier()
        self.conversation_manager = ConversationManager()

        # Intent handlers
        product_handler = ProductInfoHandler()
        self.handlers = {
            "product_info": product_handler,
            "product_search": product_handler,  # Re-use product handler
            "compare": CompareHandler(),
            "policy": PolicyHandler(),
            "cskh": CSKHHandler(),
            "general": GeneralHandler(),
        }

    async def process_message(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Process user message and generate response.

        Args:
            message: User message
            conversation_id: Conversation ID (create new if None)
            user_id: User ID
            context: Additional context

        Returns:
            Complete response dict
        """
        start_time = time.time()

        # Generate conversation ID if not provided
        if not conversation_id:
            conversation_id = f"conv_{uuid.uuid4().hex[:12]}"

        logger.info(
            f"Processing message for conversation {conversation_id}: "
            f"{message[:50]}..."
        )

        try:
            # Step 1: Load conversation history
            conversation = await self.conversation_manager.get_conversation(
                conversation_id
            )

            # Step 2: Classify intent
            intent, confidence = await self.intent_classifier.classify(
                message=message, conversation_history=conversation.get("messages", [])
            )

            logger.info(f"Intent: {intent} (confidence: {confidence:.2f})")

            # Step 3: Get appropriate handler
            handler = self.handlers.get(intent)
            if not handler:
                logger.warning(
                    f"No handler found for intent '{intent}', falling back to general"
                )
                handler = self.handlers["general"]
                # Update intent to general if handler not found
                intent = "general"

            # Prepare context with intent
            if context is None:
                context = {}
            context["intent"] = intent
            context["intent_confidence"] = confidence

            # Step 4: Generate response
            logger.debug(f"Using handler: {handler.__class__.__name__} for intent: {intent}")
            response_data = await handler.handle(
                query=message,
                conversation_history=conversation.get("messages", []),
                context=context,
            )
            
            # Validate response has type
            if not response_data or "type" not in response_data:
                logger.error(
                    f"Handler {handler.__class__.__name__} returned invalid response: "
                    f"{response_data}"
                )
                # Fallback to general response
                response_data = {
                    "type": "general",
                    "message": "Xin lỗi, đã có lỗi xảy ra khi xử lý yêu cầu của bạn.",
                }
            
            logger.debug(f"Response type: {response_data.get('type')}")

            # Step 5: Save conversation
            await self.conversation_manager.add_message(
                conversation_id=conversation_id,
                role="user",
                content=message,
                metadata={"intent": intent, "confidence": confidence},
            )

            await self.conversation_manager.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=response_data.get("message", ""),
                metadata={
                    "intent": intent,
                    "response_type": response_data.get("type"),
                    "products": [
                        p.get("id") for p in response_data.get("products", [])
                    ],
                },
            )

            # Step 6: Build final response
            response_time_ms = (time.time() - start_time) * 1000

            final_response = {
                "success": True,
                "conversation_id": conversation_id,
                "intent": intent,
                "query": message,
                "response": response_data,
                "metadata": {
                    "response_time_ms": round(response_time_ms, 2),
                    "intent_confidence": confidence,
                    "handler": intent,
                },
            }

            # Step 7: Track analytics (async, don't wait)
            # Analytics tracking can be added later if needed

            logger.info(f"✅ Response generated in {response_time_ms:.2f}ms")

            return final_response

        except Exception as e:
            logger.error(
                f"Error processing message '{message[:50]}...': {e}", 
                exc_info=True
            )
            
            # Return error response
            return {
                "success": False,
                "conversation_id": conversation_id,
                "intent": "error",
                "query": message,
                "response": {
                    "type": "error",
                    "message": "Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại sau.",
                },
                "metadata": {
                    "error": str(e),
                    "response_time_ms": (time.time() - start_time) * 1000,
                },
            }
