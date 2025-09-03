"""
Utilities for managing message queues and context state.
Used by message_handler for managing concurrent messages.
"""

from typing import Dict, Any
from loguru import logger

from context import redis_manager


def check_unread_messages(inbox_id: int, contact_id: str) -> Dict[str, Any]:
    """
    Check for messages that arrived while ReAct was processing.
    
    Args:
        inbox_id: Chatwoot inbox ID
        contact_id: Contact ID from Chatwoot
    
    Returns:
        {
            "has_unread": bool,
            "messages": [{"message": "text", "timestamp": "..."}],
            "count": int
        }
    """
    try:
        # Check if new messages flag exists
        has_new_messages = redis_manager.check_new_messages(inbox_id, contact_id)
        
        if not has_new_messages:
            return {
                "has_unread": False,
                "messages": [],
                "count": 0
            }
        
        # Get active context to retrieve queued messages
        active_context = redis_manager.get_active_context(inbox_id, contact_id)
        
        if not active_context or not active_context.queued_messages:
            return {
                "has_unread": False,
                "messages": [],
                "count": 0
            }
        
        # Extract queued messages
        messages = []
        for queued_msg in active_context.queued_messages:
            messages.append({
                "message": queued_msg.content,
                "timestamp": queued_msg.timestamp,
                "message_id": queued_msg.message_id
            })
        
        logger.info(f"Found {len(messages)} unread messages for {inbox_id}_{contact_id}")
        
        return {
            "has_unread": True,
            "messages": messages,
            "count": len(messages)
        }
        
    except Exception as e:
        logger.error(f"Error checking unread messages: {e}")
        return {
            "has_unread": False,
            "messages": [],
            "count": 0,
            "error": str(e)
        }


def clear_unread_messages(inbox_id: int, contact_id: str) -> Dict[str, Any]:
    """
    Clear unread messages after processing them.
    
    Args:
        inbox_id: Chatwoot inbox ID
        contact_id: Contact ID from Chatwoot
    
    Returns:
        {"status": "cleared", "cleared_count": int}
    """
    try:
        # Get active context
        active_context = redis_manager.get_active_context(inbox_id, contact_id)
        
        if not active_context:
            return {
                "status": "no_context",
                "cleared_count": 0
            }
        
        # Count messages before clearing
        message_count = len(active_context.queued_messages)
        
        # Clear queued messages
        active_context.queued_messages.clear()
        
        # Clear new messages flag
        redis_manager.clear_new_messages_flag(inbox_id, contact_id)
        
        # Save updated context
        success = redis_manager.save_active_context(inbox_id, contact_id, active_context)
        
        if success:
            logger.info(f"Cleared {message_count} unread messages for {inbox_id}_{contact_id}")
            return {
                "status": "cleared",
                "cleared_count": message_count
            }
        else:
            return {
                "status": "error",
                "message": "Failed to save updated context"
            }
        
    except Exception as e:
        logger.error(f"Error clearing unread messages: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


def get_context_summary(inbox_id: int, contact_id: str) -> Dict[str, Any]:
    """
    Get a summary of current context state for debugging.
    
    Args:
        inbox_id: Chatwoot inbox ID
        contact_id: Contact ID from Chatwoot
    
    Returns:
        Summary of persistent and active context
    """
    try:
        # Get contexts
        persistent = redis_manager.get_persistent_context(inbox_id, contact_id)
        active = redis_manager.get_active_context(inbox_id, contact_id)
        
        summary = {
            "inbox_id": inbox_id,
            "contact_id": contact_id,
            "has_persistent_context": persistent is not None,
            "has_active_context": active is not None
        }
        
        if persistent:
            summary["persistent_context"] = {
                "parent_name": persistent.parent_preferred_name,
                "child_name": persistent.child_name,
                "tour_scheduled": persistent.tour_scheduled_date is not None,
                "callback_requested": persistent.callback_requested
            }
        
        if active:
            summary["active_context"] = {
                "active_task": active.active_task_type,
                "task_status": active.active_task_status,
                "reasoning_cycles": len(active.reasoning_history),
                "queued_messages": len(active.queued_messages),
                "session_locked": active.session_locked_by is not None
            }
        
        return {
            "status": "success",
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Error getting context summary: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


# Backward compatibility - keep the _tool suffix versions
check_unread_messages_tool = check_unread_messages
clear_unread_messages_tool = clear_unread_messages
get_context_summary_tool = get_context_summary