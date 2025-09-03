from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger

from context import redis_manager, context_loader


def update_parent_details(
    inbox_id: int,
    contact_id: str,
    parent_preferred_name: Optional[str] = None,
    parent_preferred_email: Optional[str] = None,
    parent_preferred_phone: Optional[str] = None,
    reason: str = "user_provided"
) -> Dict[str, Any]:
    """
    Update parent's preferred contact details.
    
    Args:
        inbox_id: Chatwoot inbox ID
        contact_id: Contact ID from Chatwoot
        parent_preferred_name: Parent's preferred name
        parent_preferred_email: Parent's preferred email
        parent_preferred_phone: Parent's preferred phone
        reason: Reason for update
    
    Returns:
        {"status": "updated", "updated_fields": {...}, "reason": ...}
    """
    try:
        # Get current persistent context
        persistent_context = redis_manager.get_persistent_context(inbox_id, contact_id)
        if not persistent_context:
            from context import PersistentContext
            persistent_context = PersistentContext()
        
        updated_fields = {}
        
        # Update specified fields
        if parent_preferred_name is not None:
            old_value = persistent_context.parent_preferred_name
            persistent_context.parent_preferred_name = parent_preferred_name
            updated_fields["parent_preferred_name"] = {
                "old": old_value,
                "new": parent_preferred_name
            }
        
        if parent_preferred_email is not None:
            old_value = persistent_context.parent_preferred_email
            persistent_context.parent_preferred_email = parent_preferred_email
            updated_fields["parent_preferred_email"] = {
                "old": old_value,
                "new": parent_preferred_email
            }
        
        if parent_preferred_phone is not None:
            old_value = persistent_context.parent_preferred_phone
            persistent_context.parent_preferred_phone = parent_preferred_phone
            updated_fields["parent_preferred_phone"] = {
                "old": old_value,
                "new": parent_preferred_phone
            }
        
        if not updated_fields:
            return {
                "status": "no_changes",
                "message": "No fields provided to update"
            }
        
        # Save updated context
        success = redis_manager.save_persistent_context(inbox_id, contact_id, persistent_context)
        
        if success:
            logger.info(f"Updated parent details for {inbox_id}_{contact_id}: {updated_fields}")
            return {
                "status": "updated",
                "updated_fields": updated_fields,
                "reason": reason,
                "updated_at": datetime.utcnow().isoformat()
            }
        else:
            return {
                "status": "error",
                "message": "Failed to save updated context"
            }
            
    except Exception as e:
        logger.error(f"Error updating parent details: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


def update_child_details(
    inbox_id: int,
    contact_id: str,
    child_name: Optional[str] = None,
    child_dob: Optional[str] = None,
    child_age: Optional[int] = None,
    preferred_enrollment_date: Optional[str] = None,
    reason: str = "user_correction"
) -> Dict[str, Any]:
    """
    Update current child's details (same child, correcting/adding info).
    
    Args:
        inbox_id: Chatwoot inbox ID
        contact_id: Contact ID from Chatwoot
        child_name: Child's name
        child_dob: Child's date of birth (YYYY-MM-DD)
        child_age: Child's age in years
        preferred_enrollment_date: Preferred enrollment date (YYYY-MM-DD)
        reason: Reason for update
    
    Returns:
        {"status": "updated", "updated_fields": {...}, "reason": ...}
    """
    try:
        # Get current persistent context
        persistent_context = redis_manager.get_persistent_context(inbox_id, contact_id)
        if not persistent_context:
            from context import PersistentContext
            persistent_context = PersistentContext()
        
        updated_fields = {}
        
        # Update specified fields
        if child_name is not None:
            old_value = persistent_context.child_name
            persistent_context.child_name = child_name
            updated_fields["child_name"] = {
                "old": old_value,
                "new": child_name
            }
        
        if child_dob is not None:
            old_value = persistent_context.child_dob
            persistent_context.child_dob = child_dob
            updated_fields["child_dob"] = {
                "old": old_value,
                "new": child_dob
            }
            # Auto-calculate age if DOB provided
            try:
                dob_date = datetime.strptime(child_dob, "%Y-%m-%d")
                age = (datetime.now() - dob_date).days // 365
                persistent_context.child_age = age
                updated_fields["child_age"] = {
                    "old": persistent_context.child_age,
                    "new": age,
                    "auto_calculated": True
                }
            except:
                pass
        
        if child_age is not None and child_dob is None:
            # Only update age if DOB wasn't provided (DOB takes precedence)
            old_value = persistent_context.child_age
            persistent_context.child_age = child_age
            updated_fields["child_age"] = {
                "old": old_value,
                "new": child_age
            }
        
        if preferred_enrollment_date is not None:
            old_value = persistent_context.preferred_enrollment_date
            persistent_context.preferred_enrollment_date = preferred_enrollment_date
            updated_fields["preferred_enrollment_date"] = {
                "old": old_value,
                "new": preferred_enrollment_date
            }
        
        if not updated_fields:
            return {
                "status": "no_changes",
                "message": "No fields provided to update"
            }
        
        # Save updated context
        success = redis_manager.save_persistent_context(inbox_id, contact_id, persistent_context)
        
        if success:
            logger.info(f"Updated child details for {inbox_id}_{contact_id}: {updated_fields}")
            return {
                "status": "updated",
                "updated_fields": updated_fields,
                "child_name": persistent_context.child_name,
                "reason": reason,
                "updated_at": datetime.utcnow().isoformat()
            }
        else:
            return {
                "status": "error",
                "message": "Failed to save updated context"
            }
            
    except Exception as e:
        logger.error(f"Error updating child details: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


def track_new_child(
    inbox_id: int,
    contact_id: str,
    child_name: Optional[str] = None,
    child_dob: Optional[str] = None,
    child_age: Optional[int] = None,
    preferred_enrollment_date: Optional[str] = None,
    reason: str = "switching_child"
) -> Dict[str, Any]:
    """
    Switch to tracking a different child. RESETS all unspecified fields and pipedrive_deal_id.
    
    Args:
        inbox_id: Chatwoot inbox ID
        contact_id: Contact ID from Chatwoot
        child_name: New child's name
        child_dob: New child's date of birth (YYYY-MM-DD)
        child_age: New child's age in years
        preferred_enrollment_date: Preferred enrollment date (YYYY-MM-DD)
        reason: Reason for switch
    
    Returns:
        {"status": "switched", "previous_child": ..., "new_child": ..., "deal_reset": True}
    """
    try:
        # Get current persistent context
        persistent_context = redis_manager.get_persistent_context(inbox_id, contact_id)
        if not persistent_context:
            from context import PersistentContext
            persistent_context = PersistentContext()
        
        # Store previous child info for response
        previous_child = {
            "name": persistent_context.child_name,
            "dob": persistent_context.child_dob,
            "age": persistent_context.child_age,
            "pipedrive_deal_id": persistent_context.pipedrive_deal_id
        }
        
        # RESET all child fields
        persistent_context.child_name = child_name
        persistent_context.child_dob = child_dob
        persistent_context.child_age = None  # Will be set below if needed
        persistent_context.preferred_enrollment_date = preferred_enrollment_date
        
        # CRITICAL: Reset pipedrive_deal_id for new child
        persistent_context.pipedrive_deal_id = None
        
        # Calculate age if DOB provided
        if child_dob:
            try:
                dob_date = datetime.strptime(child_dob, "%Y-%m-%d")
                age = (datetime.now() - dob_date).days // 365
                persistent_context.child_age = age
            except:
                pass
        elif child_age is not None:
            persistent_context.child_age = child_age
        
        # Save updated context
        success = redis_manager.save_persistent_context(inbox_id, contact_id, persistent_context)
        
        if success:
            logger.info(f"Switched to new child for {inbox_id}_{contact_id}: {previous_child['name']} -> {child_name}")
            logger.warning(f"Reset pipedrive_deal_id from {previous_child['pipedrive_deal_id']} to None")
            
            return {
                "status": "switched",
                "previous_child": previous_child,
                "new_child": {
                    "name": persistent_context.child_name,
                    "dob": persistent_context.child_dob,
                    "age": persistent_context.child_age,
                    "enrollment_date": persistent_context.preferred_enrollment_date
                },
                "deal_reset": True,
                "pipedrive_deal_id": None,
                "reason": reason,
                "updated_at": datetime.utcnow().isoformat()
            }
        else:
            return {
                "status": "error",
                "message": "Failed to save updated context"
            }
            
    except Exception as e:
        logger.error(f"Error tracking new child: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


def check_unread_messages_tool(inbox_id: int, contact_id: str) -> Dict[str, Any]:
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


def clear_unread_messages_tool(inbox_id: int, contact_id: str) -> Dict[str, Any]:
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


def get_context_summary_tool(inbox_id: int, contact_id: str) -> Dict[str, Any]:
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