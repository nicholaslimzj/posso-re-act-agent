"""
Callback request tool for handling parent callback requests
"""

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger

from context.models import FullContext, PersistentContext, TaskType, TaskStatus
from integrations.pipedrive import create_enrollment_deal, add_note_to_deal
from tools.shared_workflows import analyze_data_collection_requirements


def request_callback(
    context: FullContext,
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
        context: Full context containing runtime and persistent data
        callback_preference: When they prefer to be called
        reason: Optional reason for the callback
        confirmed_fields: Fields already confirmed in this session
        
    Returns:
        Either callback confirmation OR guidance on what information to collect next
    """
    try:
        # Extract what we need from context
        persistent_context = context.persistent
        runtime_context = context.runtime
        school_id = runtime_context.school_id
        
        logger.info(f"request_callback called for school {school_id}")
        logger.info(f"  Preference: {callback_preference}, Reason: {reason}")
        
        confirmed_fields = confirmed_fields or []
        
        # Analyze what we have and what we need using shared workflow
        analysis = analyze_data_collection_requirements(
            persistent_context,
            purpose="callback_request",
            confirmed_fields=confirmed_fields,
            runtime_context=runtime_context
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
                    school_id=school_id
                ))
                
                if deal_result.get("status") == "success":
                    # Save deal ID to context
                    persistent_context.pipedrive_deal_id = deal_result["deal_id"]
                    persistent_context.pipedrive_person_id = deal_result["person_id"]
                    # Context will be saved by the caller
                    logger.info(f"Created Pipedrive deal {deal_result['deal_id']} for callback")
                    
                    # Now retry the analysis with the deal created
                    analysis = analyze_data_collection_requirements(
                        persistent_context,
                        purpose="callback_request",
                        confirmed_fields=confirmed_fields,
                        runtime_context=runtime_context
                    )
                    
                    # If still not ready after creating deal, return the new status
                    if analysis["status"] != "ready":
                        # Store tool response data for context continuity
                        context.active.active_task_type = TaskType.CALLBACK_REQUEST
                        context.active.active_task_status = TaskStatus.COLLECTING_INFO
                        context.active.active_task_data = {
                            "last_tool_response": {
                                "tool": "request_callback",
                                "status": "need_info",
                                "stage": analysis["stage"],
                                "prompt_for": analysis["prompt_for"],
                                "progress": analysis["progress"],
                                "next_action": "If user provides the missing information, call update_contact_info to save it, then call request_callback again to continue"
                            },
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        # Context will be saved by the caller
                        
                        return {
                            "status": "need_info",
                            "workflow_stage": analysis["stage"],
                            "next_action": analysis["next_action"],
                            "prompt_for": analysis["prompt_for"],
                            "reason": analysis["reason"],
                            "context_hint": analysis.get("context_hint"),
                            "progress": analysis["progress"],
                            "important_note": "CALLBACK REQUEST IS NOT YET COMPLETE - still collecting required information"
                        }
                else:
                    return {
                        "status": "error",
                        "error": f"Failed to create enrollment record: {deal_result.get('error')}"
                    }
            else:
                # Regular case - need user input
                # Store tool response data for context continuity
                context.active.active_task_type = TaskType.CALLBACK_REQUEST
                context.active.active_task_status = TaskStatus.COLLECTING_INFO
                context.active.active_task_data = {
                    "last_tool_response": {
                        "tool": "request_callback",
                        "status": "need_info",
                        "stage": analysis["stage"],
                        "prompt_for": analysis["prompt_for"],
                        "progress": analysis["progress"],
                        "next_action": "If user provides the missing information, call update_contact_info to save it, then call request_callback again to continue"
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }
                # Context will be saved by the caller
                
                return {
                    "status": "need_info",
                    "workflow_stage": analysis["stage"],
                    "next_action": analysis["next_action"],
                    "prompt_for": analysis["prompt_for"],
                    "reason": analysis["reason"],
                    "question": analysis.get("question"),
                    "progress": analysis["progress"],
                    "important_note": "CALLBACK REQUEST IS NOT YET COMPLETE - still collecting required information"
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
            school_id=school_id
        ))
        
        if result.get("status") == "success":
            # Update context with callback request info
            persistent_context.callback_requested = True
            persistent_context.callback_preference = callback_preference
            persistent_context.callback_requested_at = datetime.utcnow().isoformat()
            
            # Clear active task since callback request is complete
            context.active.active_task_type = None
            context.active.active_task_status = None
            context.active.active_task_data = {}
            # Context will be saved by the caller
            
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


# Backward compatibility wrapper removed - use request_callback directly