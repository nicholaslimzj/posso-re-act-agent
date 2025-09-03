"""
Callback request tool for handling parent callback requests
"""

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger

from context import redis_manager
from integrations.pipedrive import create_enrollment_deal, add_note_to_deal
from tools.shared_workflows import analyze_data_collection_requirements


def request_callback(
    inbox_id: int,
    contact_id: str,
    callback_preference: str = "anytime",  # "morning", "afternoon", "anytime"
    reason: Optional[str] = None,
    confirmed_fields: List[str] = None
) -> Dict[str, Any]:
    """
    Request a callback - intelligently handles data collection before creating the request.
    
    This tool will:
    1. Check if we have all required parent/child information
    2. Create a Pipedrive deal if needed
    3. Add a callback note to the deal
    4. Update context with callback request status
    
    Args:
        inbox_id: Chatwoot inbox ID
        contact_id: Contact ID from Chatwoot
        callback_preference: When they prefer to be called
        reason: Optional reason for the callback
        confirmed_fields: Fields already confirmed in this session
        
    Returns:
        Either callback confirmation OR guidance on what information to collect next
    """
    try:
        logger.info(f"request_callback called for {inbox_id}_{contact_id}")
        logger.info(f"  Preference: {callback_preference}, Reason: {reason}")
        
        # Get persistent context
        persistent_context = redis_manager.get_persistent_context(inbox_id, contact_id)
        if not persistent_context:
            from context import PersistentContext
            persistent_context = PersistentContext()
            logger.warning(f"No persistent context found for {inbox_id}_{contact_id}, using defaults")
        else:
            logger.info(f"Loaded persistent context with {len(persistent_context.model_dump())} fields")
        
        confirmed_fields = confirmed_fields or []
        
        # Analyze what we have and what we need using shared workflow
        analysis = analyze_data_collection_requirements(
            persistent_context,
            purpose="callback_request",
            confirmed_fields=confirmed_fields
        )
        
        # If we need more info, return structured guidance
        if analysis["status"] != "ready":
            # Special case: Auto-create deal if we have all required info
            if analysis["status"] == "need_deal" and analysis.get("next_action") == "create_deal":
                # We have all the info, just need to create the deal
                logger.info("Auto-creating Pipedrive deal for callback request...")
                
                deal_result = asyncio.run(create_enrollment_deal(
                    parent_name=persistent_context.parent_preferred_name,
                    child_name=persistent_context.child_name,
                    parent_phone=persistent_context.parent_preferred_phone,
                    parent_email=persistent_context.parent_preferred_email,
                    child_dob=persistent_context.child_dob,
                    enrollment_date=persistent_context.preferred_enrollment_date,
                    school_id=str(inbox_id)  # Use inbox_id as school_id
                ))
                
                if deal_result.get("status") == "success":
                    # Save deal ID to context
                    persistent_context.pipedrive_deal_id = deal_result["deal_id"]
                    persistent_context.pipedrive_person_id = deal_result["person_id"]
                    redis_manager.save_persistent_context(inbox_id, contact_id, persistent_context)
                    logger.info(f"Created Pipedrive deal {deal_result['deal_id']} for callback")
                    
                    # Now retry the analysis with the deal created
                    analysis = analyze_data_collection_requirements(
                        persistent_context,
                        purpose="callback_request",
                        confirmed_fields=confirmed_fields
                    )
                    
                    # If still not ready after creating deal, return the new status
                    if analysis["status"] != "ready":
                        return {
                            "status": "need_info",
                            "workflow_stage": analysis["stage"],
                            "next_action": analysis["next_action"],
                            "prompt_for": analysis["prompt_for"],
                            "reason": analysis["reason"],
                            "context_hint": analysis.get("context_hint"),
                            "progress": analysis["progress"]
                        }
                else:
                    return {
                        "status": "error",
                        "error": f"Failed to create enrollment record: {deal_result.get('error')}"
                    }
            else:
                # Regular case - need user input
                return {
                    "status": "need_info",
                    "workflow_stage": analysis["stage"],
                    "next_action": analysis["next_action"],
                    "prompt_for": analysis["prompt_for"],
                    "reason": analysis["reason"],
                    "question": analysis.get("question"),
                    "progress": analysis["progress"]
                }
        
        # All requirements met - create the callback request
        deal_id = persistent_context.pipedrive_deal_id
        
        # Format callback note
        note_content = f"📞 CALLBACK REQUEST\n"
        note_content += f"Parent: {persistent_context.parent_preferred_name}\n"
        note_content += f"Phone: {persistent_context.parent_preferred_phone}\n"
        note_content += f"Email: {persistent_context.parent_preferred_email}\n"
        note_content += f"Child: {persistent_context.child_name}\n"
        
        if persistent_context.child_dob:
            from datetime import datetime
            try:
                dob_date = datetime.strptime(persistent_context.child_dob, "%Y-%m-%d")
                age_years = (datetime.now() - dob_date).days // 365
                age_months = ((datetime.now() - dob_date).days % 365) // 30
                note_content += f"Child Age: {age_years} years {age_months} months\n"
            except:
                pass
        
        note_content += f"\nPreferred Callback Time: {callback_preference}\n"
        
        if reason:
            note_content += f"Reason: {reason}\n"
        
        note_content += f"\nRequested at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # Add note to Pipedrive deal
        result = asyncio.run(add_note_to_deal(
            deal_id=deal_id,
            content=note_content,
            school_id=str(inbox_id)
        ))
        
        if result.get("status") == "success":
            # Update context with callback request info
            persistent_context.callback_requested = True
            persistent_context.callback_preference = callback_preference
            persistent_context.callback_requested_at = datetime.utcnow().isoformat()
            redis_manager.save_persistent_context(inbox_id, contact_id, persistent_context)
            
            # Format response message
            preference_text = {
                "morning": "in the morning",
                "afternoon": "in the afternoon", 
                "anytime": "at your earliest convenience"
            }.get(callback_preference, "")
            
            return {
                "status": "success",
                "action": "callback_requested",
                "message": f"I've recorded your callback request. Our team will call you {preference_text} at {persistent_context.parent_preferred_phone}.",
                "callback_preference": callback_preference,
                "phone": persistent_context.parent_preferred_phone,
                "deal_id": deal_id,
                "note_id": result.get("note_id")
            }
        else:
            return {
                "status": "error",
                "error": f"Failed to create callback request: {result.get('error')}"
            }
        
    except Exception as e:
        logger.error(f"Error in request_callback: {e}")
        return {
            "status": "error",
            "error": str(e)
        }