#!/usr/bin/env python3
"""
Message Handler - Orchestrates ReAct agent processing with context management
"""

import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger

from config import settings, school_manager
from context import context_loader, redis_manager, FullContext
from agents import ReActAgent

try:
    from langsmith import Client as LangSmithClient
    from langsmith.run_helpers import traceable
    langsmith_client = LangSmithClient()
    LANGSMITH_ENABLED = True
except ImportError:
    LANGSMITH_ENABLED = False
    logger.warning("LangSmith not installed - error reporting disabled")


class MessageHandler:
    """Handles incoming messages with ReAct processing and concurrency management"""
    
    def __init__(self):
        self.context_loader = context_loader
        self.redis_manager = redis_manager
        self.agent = ReActAgent()
        self.school_manager = school_manager
    
    async def process_chatwoot_message_async(
        self,
        inbox_id: int,
        contact_id: str,
        conversation_id: str,
        message_content: str,
        message_id: Optional[str] = None,
        whatsapp_profile: Optional[Dict[str, Any]] = None,
        chatwoot_additional_params: Optional[Dict[str, Any]] = None,
        recent_messages: Optional[list] = None
    ) -> Dict[str, Any]:
        """Async wrapper for process_chatwoot_message"""
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        # Run the synchronous processing in a thread pool
        with ThreadPoolExecutor() as executor:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                executor,
                self.process_chatwoot_message,
                inbox_id,
                contact_id,
                conversation_id,
                message_content,
                message_id,
                whatsapp_profile,
                chatwoot_additional_params,
                recent_messages
            )
            return result
    
    def process_chatwoot_message(
        self,
        inbox_id: int,
        contact_id: str,
        conversation_id: str,
        message_content: str,
        message_id: Optional[str] = None,
        whatsapp_profile: Optional[Dict[str, Any]] = None,
        chatwoot_additional_params: Optional[Dict[str, Any]] = None,
        recent_messages: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Process a message from Chatwoot webhook
        
        Args:
            inbox_id: Chatwoot inbox ID
            contact_id: Contact ID from Chatwoot
            conversation_id: Conversation ID from Chatwoot
            message_content: The actual message text
            message_id: Optional message ID
            whatsapp_profile: WhatsApp profile data
            chatwoot_additional_params: Persistent context from Chatwoot
            recent_messages: Recent conversation history
        
        Returns:
            Dict with response and processing metadata
        """
        try:
            # Validate school configuration
            if not self.school_manager.is_valid_school(str(inbox_id)):
                logger.warning(f"Unknown inbox_id: {inbox_id}")
                return {
                    "success": False,
                    "error": "Unknown school/inbox configuration",
                    "response": "I'm sorry, there seems to be a configuration issue. Please contact support."
                }
            
            # Generate unique lock ID for this processing attempt
            lock_id = f"handler_{uuid.uuid4().hex[:8]}"
            
            # Try to acquire session lock (2 minute timeout)
            lock_acquired = self.redis_manager.acquire_session_lock(
                inbox_id, contact_id, lock_id, timeout_seconds=120
            )
            
            if not lock_acquired:
                # Session is locked - queue this message
                message_data = {
                    "id": message_id or "unknown",
                    "content": message_content,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                success = self.redis_manager.queue_message(inbox_id, contact_id, message_data)
                
                if success:
                    logger.info(f"Message queued for {inbox_id}_{contact_id} (session locked)")
                    return {
                        "success": True,
                        "queued": True,
                        "response": "Your message has been received and will be processed shortly."
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to queue message",
                        "response": "I'm currently busy. Please try again in a moment."
                    }
            
            try:
                # Load context
                context = self.context_loader.load_context(
                    inbox_id=inbox_id,
                    contact_id=contact_id,
                    conversation_id=conversation_id,
                    whatsapp_profile=whatsapp_profile,
                    chatwoot_additional_params=chatwoot_additional_params,
                    recent_messages=recent_messages
                )

                # Check if we should auto-assign to human agent (if last outgoing message was from human)
                if self._should_auto_assign_to_human(recent_messages):
                    logger.info("Last outgoing message was from human agent - performing silent assignment")


                    from tools.assign_to_human_tool import assign_to_human_tool, HandoverMode
                    import asyncio

                    assignment_result = asyncio.run(assign_to_human_tool(
                        context=context,
                        reason="Continuing conversation with human agent",
                        mode=HandoverMode.SILENT
                    ))

                    if assignment_result.get("status") == "success":
                        # Save context and return without invoking LLM
                        self.context_loader.save_context(inbox_id, contact_id, context)
                        chatwoot_sync_data = self.context_loader.prepare_chatwoot_sync_data(context)

                        return {
                            "success": True,
                            "response": "",  # No response needed for silent assignment
                            "reasoning_cycles": 0,
                            "chatwoot_sync_data": chatwoot_sync_data,
                            "session_id": f"silent_handover_{uuid.uuid4().hex[:8]}",
                            "auto_assigned": True
                        }
                    else:
                        logger.warning(f"Auto-assignment failed: {assignment_result.get('message')}")
                        # Continue with normal processing if assignment fails

                # Process message with ReAct agent
                result = self._process_with_react(
                    message_content=message_content,
                    context=context,
                    inbox_id=inbox_id,
                    contact_id=contact_id,
                    recent_messages=recent_messages
                )
                
                # Note: Queued messages are now handled within the ReAct loop via injection
                
                # Save final context
                self.context_loader.save_context(inbox_id, contact_id, result["context"])
                
                # Prepare Chatwoot sync data
                chatwoot_sync_data = self.context_loader.prepare_chatwoot_sync_data(result["context"])
                
                return {
                    "success": True,
                    "response": result["response"],
                    "reasoning_cycles": result.get("cycles_count", 0),
                    "chatwoot_sync_data": chatwoot_sync_data,
                    "session_id": result.get("session_id", f"session_{uuid.uuid4().hex[:8]}")
                }
                
            except Exception as processing_error:
                # Report to LangSmith before cleanup
                self._report_error_to_langsmith(
                    error=processing_error,
                    context={
                        "inbox_id": inbox_id,
                        "contact_id": contact_id,
                        "message": message_content[:100] if message_content else None,
                        "stage": "message_processing"
                    }
                )
                # Re-raise to be caught by outer except
                raise
                
            finally:
                # Clean up before releasing lock
                try:
                    # Clear any remaining queued messages (that came in during final response)
                    active_context = self.redis_manager.get_active_context(inbox_id, contact_id)
                    if active_context and active_context.queued_messages:
                        logger.info(f"Clearing {len(active_context.queued_messages)} unprocessed messages at end of session")
                        active_context.queued_messages = []
                        self.redis_manager.save_active_context(inbox_id, contact_id, active_context)
                    
                    # Clear new messages flag
                    self.redis_manager.clear_new_messages_flag(inbox_id, contact_id)
                    
                except Exception as cleanup_error:
                    logger.error(f"Error during cleanup: {cleanup_error}")
                
                # Always release the lock
                self.redis_manager.release_session_lock(inbox_id, contact_id, lock_id)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return {
                "success": False,
                "error": str(e),
                "response": "I encountered an error processing your message. Please try again."
            }
    
    def _should_auto_assign_to_human(self, recent_messages: Optional[list]) -> bool:
        """
        Check if we should automatically assign to human agent based on recent message history.
        Returns True if the last outgoing message was from a human agent.
        """
        if not recent_messages:
            return False

        # Get bot agent ID for comparison
        bot_agent_id = self.school_manager.get_bot_agent_id()
        if not bot_agent_id:
            logger.warning("No bot agent ID configured - cannot determine auto-assignment")
            return False

        # Look at messages in reverse order (most recent first), skipping incoming messages
        # to find the most recent outgoing message
        for msg in reversed(recent_messages):
            # Skip system messages (type 2)
            if msg.get("message_type") == 2:
                continue

            # Skip incoming messages (type 0) - we only care about outgoing messages
            if msg.get("message_type") == 0:
                continue

            # Check if this is an outgoing message (type 1)
            if msg.get("message_type") == 1:
                sender = msg.get("sender", {})
                sender_id = sender.get("id") if sender else None

                # If outgoing message is NOT from bot, it's from human agent
                if sender_id and sender_id != bot_agent_id:
                    logger.info(f"Most recent outgoing message was from human agent (ID: {sender_id})")
                    return True
                else:
                    # Most recent outgoing message was from bot
                    logger.debug(f"Most recent outgoing message was from bot (ID: {sender_id})")
                    return False

        # No outgoing messages found
        return False

    def _report_error_to_langsmith(self, error: Exception, context: Dict[str, Any]):
        """Report error to LangSmith for tracking"""
        try:
            if LANGSMITH_ENABLED and settings.LANGCHAIN_TRACING_V2 == "true":
                # Use LangChain's callback to report the error
                # This will show up in the current trace as an error
                from langchain.callbacks import get_openai_callback
                from langchain_core.tracers import LangChainTracer
                
                import traceback
                error_info = {
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "traceback": traceback.format_exc(),
                    "context": context
                }
                
                # Log the error which will be picked up by the active trace
                logger.error(f"ReAct Agent Error: {error_info}")
                
                # If we want to be more explicit, we can use the tracer directly
                tracer = LangChainTracer()
                if tracer:
                    # This will mark the current run as failed
                    tracer.on_chain_error(error, metadata=error_info)
                    
        except Exception as e:
            # Don't let LangSmith errors break the flow
            logger.warning(f"Failed to report to LangSmith: {e}")
    
    def _process_with_react(
        self,
        message_content: str,
        context: FullContext,
        inbox_id: int,
        contact_id: str,
        recent_messages: Optional[list] = None
    ) -> Dict[str, Any]:
        """Process message through ReAct agent"""
        try:
            # Format Chatwoot history if available
            chatwoot_history = None
            if recent_messages:
                logger.info(f"Processing {len(recent_messages)} recent messages for history")
                from context.chatwoot_history_formatter import format_chatwoot_messages

                # Get bot agent ID from school manager
                bot_agent_id = self.school_manager.get_bot_agent_id()

                # Get last 14 messages and exclude the current message
                chatwoot_history = format_chatwoot_messages(
                    messages=recent_messages,
                    limit=14,
                    exclude_last=True,  # Don't include current message in history
                    bot_agent_id=bot_agent_id
                )
                if chatwoot_history:
                    logger.info(f"Formatted {len(recent_messages)} messages into history ({len(chatwoot_history)} chars)")
                else:
                    logger.warning("format_chatwoot_messages returned empty history")
            else:
                logger.info("No recent_messages provided for history formatting")
            
            # Process with ReAct agent
            result = self.agent.process_message(
                message=message_content,
                context=context,
                inbox_id=inbox_id,
                contact_id=contact_id,
                chatwoot_history=chatwoot_history
            )
            
            # Response crafting is now handled within the ReAct graph
            # No external response crafting needed
            
            # Add context to result for compatibility
            result['context'] = context
            
            return result
            
        except Exception as e:
            logger.error(f"Error in ReAct processing: {e}")
            raise
# Global handler instance
message_handler = MessageHandler()