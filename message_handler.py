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
from tools import update_context_tool, check_unread_messages_tool, clear_unread_messages_tool


class MessageHandler:
    """Handles incoming messages with ReAct processing and concurrency management"""
    
    def __init__(self):
        self.context_loader = context_loader
        self.redis_manager = redis_manager
        self.agent = ReActAgent()
        self.school_manager = school_manager
    
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
            
            # Try to acquire session lock
            lock_acquired = self.redis_manager.acquire_session_lock(
                inbox_id, contact_id, lock_id, timeout_seconds=300
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
                
                # Process message with ReAct agent
                result = self._process_with_react(
                    message_content=message_content,
                    context=context,
                    inbox_id=inbox_id,
                    contact_id=contact_id
                )
                
                # Check for queued messages and process them
                self._process_queued_messages(inbox_id, contact_id, result["context"])
                
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
                
            finally:
                # Always release the lock
                self.redis_manager.release_session_lock(inbox_id, contact_id, lock_id)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return {
                "success": False,
                "error": str(e),
                "response": "I encountered an error processing your message. Please try again."
            }
    
    def _process_with_react(
        self,
        message_content: str,
        context: FullContext,
        inbox_id: int,
        contact_id: str
    ) -> Dict[str, Any]:
        """Process message through ReAct agent"""
        try:
            # TODO: Get Chatwoot history if needed
            chatwoot_history = None  # This would be formatted conversation history
            
            # Process with ReAct agent
            result = self.agent.process_message(
                message=message_content,
                context=context,
                chatwoot_history=chatwoot_history
            )
            
            # Active context now only tracks multi-step task data, not reasoning metadata
            
            # Add context to result for compatibility
            result['context'] = context
            
            return result
            
        except Exception as e:
            logger.error(f"Error in ReAct processing: {e}")
            raise
    
    def _create_context_aware_tools(self, inbox_id: int, contact_id: str) -> list:
        """Create tools that have access to current context"""
        from langchain_core.tools import tool
        
        @tool
        def update_context_aware(field_to_update: str, new_value: str, reason: str = "new_information") -> dict:
            """
            Update context when user provides corrections or new information.
            Args:
                field_to_update: Field name like "parent_preferred_name", "child_name", etc.
                new_value: New value for the field
                reason: Reason for update like "user_correction", "new_information"
            Returns:
                {"status": "updated", "field": field_name, "old_value": old, "new_value": new}
            """
            return update_context_tool(inbox_id, contact_id, field_to_update, new_value, reason)
        
        @tool
        def check_unread_messages_aware() -> dict:
            """
            Check for messages that arrived while ReAct was processing.
            Returns:
                {
                    "has_unread": bool,
                    "messages": [{"message": "text", "timestamp": "..."}],
                    "count": int
                }
            """
            return check_unread_messages_tool(inbox_id, contact_id)
        
        return [update_context_aware, check_unread_messages_aware]
    
    def _process_queued_messages(self, inbox_id: int, contact_id: str, context: FullContext):
        """Process any messages that were queued during ReAct processing"""
        try:
            # Check for unread messages
            unread_result = check_unread_messages_tool(inbox_id, contact_id)
            
            if unread_result.get("has_unread") and unread_result.get("count", 0) > 0:
                logger.info(f"Processing {unread_result['count']} queued messages for {inbox_id}_{contact_id}")
                
                # Process each queued message
                for message in unread_result["messages"]:
                    try:
                        # Process through ReAct (simplified version)
                        result = self._process_with_react(
                            message_content=message["message"],
                            context=context,
                            inbox_id=inbox_id,
                            contact_id=contact_id
                        )
                        
                        # Update context with results
                        context = result["context"]
                        
                        logger.debug(f"Processed queued message: {message['message'][:50]}...")
                        
                    except Exception as e:
                        logger.error(f"Error processing queued message: {e}")
                        continue
                
                # Clear processed messages
                clear_unread_messages_tool(inbox_id, contact_id)
            
        except Exception as e:
            logger.error(f"Error processing queued messages: {e}")

# Global handler instance
message_handler = MessageHandler()