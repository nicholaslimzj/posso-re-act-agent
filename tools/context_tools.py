from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger

from context import redis_manager, context_loader


def update_contact_info(
    inbox_id: int,
    contact_id: str,
    update_type: str,  # "parent" | "child" | "new_child"
    fields: Dict[str, Any],
    reason: str = "user_provided"
) -> Dict[str, Any]:
    """
    Unified context update tool for parent and child information.
    
    Args:
        inbox_id: Chatwoot inbox ID
        contact_id: Contact ID from Chatwoot
        update_type: Type of update - "parent", "child", or "new_child"
        fields: Dictionary of fields to update
        reason: Reason for update
    
    Returns:
        {"status": "updated", "updated_fields": {...}, "update_type": ...}
    """
    try:
        # Validate update_type
        if update_type not in ["parent", "child", "new_child"]:
            return {
                "status": "error",
                "message": f"Invalid update_type: {update_type}. Must be 'parent', 'child', or 'new_child'"
            }
        
        # Get current persistent context
        persistent_context = redis_manager.get_persistent_context(inbox_id, contact_id)
        if not persistent_context:
            from context import PersistentContext
            persistent_context = PersistentContext()
        
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
                if field_name in ["child_name", "child_dob", "child_age", "preferred_enrollment_date"]:
                    old_value = getattr(persistent_context, field_name, None)
                    setattr(persistent_context, field_name, new_value)
                    updated_fields[field_name] = {
                        "old": old_value,
                        "new": new_value
                    }
            
            # Auto-calculate age if DOB provided
            if "child_dob" in fields and fields["child_dob"]:
                try:
                    dob_date = datetime.strptime(fields["child_dob"], "%Y-%m-%d")
                    age = (datetime.now() - dob_date).days // 365
                    persistent_context.child_age = age
                    if "child_age" not in updated_fields:
                        updated_fields["child_age"] = {
                            "old": persistent_context.child_age,
                            "new": age,
                            "auto_calculated": True
                        }
                except:
                    pass
        
        elif update_type == "new_child":
            # Store previous child info
            previous_child = {
                "name": persistent_context.child_name,
                "dob": persistent_context.child_dob,
                "age": persistent_context.child_age,
                "pipedrive_deal_id": persistent_context.pipedrive_deal_id
            }
            
            # RESET all child fields
            persistent_context.child_name = fields.get("child_name")
            persistent_context.child_dob = fields.get("child_dob")
            persistent_context.child_age = None
            persistent_context.preferred_enrollment_date = fields.get("preferred_enrollment_date")
            
            # CRITICAL: Reset pipedrive_deal_id for new child
            persistent_context.pipedrive_deal_id = None
            
            # Calculate age if DOB provided
            if fields.get("child_dob"):
                try:
                    dob_date = datetime.strptime(fields["child_dob"], "%Y-%m-%d")
                    age = (datetime.now() - dob_date).days // 365
                    persistent_context.child_age = age
                except:
                    pass
            elif fields.get("child_age"):
                persistent_context.child_age = fields["child_age"]
            
            # Track what changed
            updated_fields = {
                "child_name": {"old": previous_child["name"], "new": persistent_context.child_name},
                "child_dob": {"old": previous_child["dob"], "new": persistent_context.child_dob},
                "child_age": {"old": previous_child["age"], "new": persistent_context.child_age},
                "pipedrive_deal_id": {"old": previous_child["pipedrive_deal_id"], "new": None, "reset": True}
            }
        
        if not updated_fields:
            return {
                "status": "no_changes",
                "message": "No valid fields provided to update"
            }
        
        # Save updated context
        success = redis_manager.save_persistent_context(inbox_id, contact_id, persistent_context)
        
        if success:
            logger.info(f"Updated {update_type} info for {inbox_id}_{contact_id}: {updated_fields}")
            
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
        else:
            return {
                "status": "error",
                "message": "Failed to save updated context"
            }
            
    except Exception as e:
        logger.error(f"Error updating {update_type} info: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


