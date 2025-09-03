from typing import Dict, Any
from datetime import datetime
from loguru import logger

from context.models import FullContext


def update_contact_info(
    context: FullContext,
    update_type: str,  # "parent" | "child" | "new_child"
    fields: Dict[str, Any],
    reason: str = "user_provided"
) -> Dict[str, Any]:
    """
    Pure function that updates contact information in the provided context.
    
    This function modifies the context in-memory. The caller is responsible
    for persisting the changes to Redis or other storage.
    
    Args:
        context: The full context containing persistent data to update
        update_type: Type of update - "parent", "child", or "new_child"
        fields: Dictionary of fields to update
        reason: Reason for update (for audit trail)
    
    Returns:
        Dict with update status and what was changed
    """
    try:
        # Validate update_type
        if update_type not in ["parent", "child", "new_child"]:
            return {
                "status": "error",
                "message": f"Invalid update_type: {update_type}. Must be 'parent', 'child', or 'new_child'"
            }
        
        # Get the persistent context from the full context
        persistent_context = context.persistent
        
        updated_fields = {}
        previous_child = None
        
        # Handle different update types
        if update_type == "parent":
            # Update parent fields
            for field_name, new_value in fields.items():
                if field_name in ["parent_preferred_name", "parent_preferred_email", "parent_preferred_phone"]:
                    old_value = getattr(persistent_context, field_name, None)
                    setattr(persistent_context, field_name, new_value)
                    updated_fields[field_name] = {
                        "old": old_value,
                        "new": new_value
                    }
        
        elif update_type == "child":
            # Update current child's fields
            for field_name, new_value in fields.items():
                if field_name in ["child_name", "child_dob", "preferred_enrollment_date"]:
                    old_value = getattr(persistent_context, field_name, None)
                    setattr(persistent_context, field_name, new_value)
                    updated_fields[field_name] = {
                        "old": old_value,
                        "new": new_value
                    }
            
            # Note: We don't store age anymore - it's calculated dynamically when needed
            # from DOB and enrollment date for determining child level
        
        elif update_type == "new_child":
            # Store previous child info for audit trail
            previous_child = {
                "name": persistent_context.child_name,
                "dob": persistent_context.child_dob,
                "pipedrive_deal_id": persistent_context.pipedrive_deal_id
            }
            
            # RESET all child fields for new child
            persistent_context.child_name = fields.get("child_name")
            persistent_context.child_dob = fields.get("child_dob")
            persistent_context.preferred_enrollment_date = fields.get("preferred_enrollment_date")
            
            # CRITICAL: Reset pipedrive_deal_id for new child
            persistent_context.pipedrive_deal_id = None
            persistent_context.pipedrive_person_id = None
            persistent_context.tour_activity_id = None
            persistent_context.tour_scheduled_date = None
            persistent_context.tour_scheduled_time = None
            
            # Note: We don't store age - it's calculated dynamically when needed
            
            # Track what changed
            updated_fields = {
                "child_name": {"old": previous_child["name"], "new": persistent_context.child_name},
                "child_dob": {"old": previous_child["dob"], "new": persistent_context.child_dob},
                "pipedrive_deal_id": {"old": previous_child["pipedrive_deal_id"], "new": None, "reset": True}
            }
        
        if not updated_fields:
            return {
                "status": "no_changes",
                "message": "No valid fields provided to update"
            }
        
        # Context has been modified in-place (Python objects are mutable)
        # The caller (agent/message_handler) is responsible for saving to Redis
        
        logger.info(f"Updated {update_type} info in context: {list(updated_fields.keys())}")
        
        response = {
            "status": "updated",
            "update_type": update_type,
            "updated_fields": updated_fields,
            "reason": reason,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Add special fields for new_child
        if update_type == "new_child":
            response["previous_child"] = previous_child
            response["deal_reset"] = True
            response["warning"] = "Pipedrive deal has been reset for new child"
            logger.warning(f"Reset pipedrive_deal_id from {previous_child['pipedrive_deal_id']} to None")
        
        return response
            
    except Exception as e:
        logger.error(f"Error updating {update_type} info: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


# Backward compatibility wrapper removed - use update_contact_info directly