"""
Intelligent tour booking tool with workflow orchestration.
This tool handles the entire booking flow, determining what data is needed,
what should be confirmed, and what to collect next.
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from loguru import logger
import asyncio

from integrations.pipedrive import (
    create_tour_activity,
    reschedule_tour_activity,
    calculate_child_level,
    create_enrollment_deal
)
from context import redis_manager


def book_or_reschedule_tour(
    inbox_id: int,
    contact_id: str,
    action: str,  # "book" or "reschedule" 
    tour_date: str,
    tour_time: str,
    confirmed_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Intelligent tour booking with workflow orchestration.
    
    This tool:
    1. Checks what data we have in context
    2. Determines what needs confirmation (if data is old/suspicious)
    3. Identifies what's missing and what to collect next
    4. Only books when everything is ready
    
    Args:
        inbox_id: Chatwoot inbox ID
        contact_id: Contact ID
        action: "book" for new booking, "reschedule" for existing
        tour_date: Date in YYYY-MM-DD format
        tour_time: Time in HH:MM format (Singapore time)
        confirmed_fields: List of fields the user has explicitly confirmed in this conversation
    
    Returns:
        Dict with either:
        - Booking success details
        - Missing/unconfirmed data requirements with guided next steps
    """
    try:
        logger.info(f"book_or_reschedule_tour called for {inbox_id}_{contact_id}")
        logger.info(f"  Action: {action}, Date: {tour_date}, Time: {tour_time}")
        
        # Get persistent context
        persistent_context = redis_manager.get_persistent_context(inbox_id, contact_id)
        if not persistent_context:
            from context import PersistentContext
            persistent_context = PersistentContext()
            logger.warning(f"No persistent context found for {inbox_id}_{contact_id}, using defaults")
        else:
            logger.info(f"Loaded persistent context with {len(persistent_context.model_dump())} fields")
        
        confirmed_fields = confirmed_fields or []
        
        # Analyze what we have and what we need
        analysis = _analyze_booking_requirements(
            persistent_context,
            action,
            confirmed_fields
        )
        
        # If we need more info, return structured guidance
        if analysis["status"] != "ready":
            # Special case: Auto-create deal if we have all required info
            if analysis["status"] == "need_deal" and analysis.get("next_action") == "create_deal":
                # We have all the info, just need to create the deal
                logger.info("Auto-creating Pipedrive deal...")
                
                deal_result = asyncio.run(create_enrollment_deal(
                    parent_name=persistent_context.parent_preferred_name,
                    child_name=persistent_context.child_name,
                    parent_phone=persistent_context.parent_preferred_phone,  # Use stored phone
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
                    
                    # Now retry the analysis with the deal created
                    analysis = _analyze_booking_requirements(
                        persistent_context,
                        action,
                        confirmed_fields
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
                    "context_hint": analysis.get("context_hint"),
                    "question": analysis.get("question"),
                    "progress": analysis["progress"]
                }
        
        # All requirements met - proceed with booking
        deal_id = persistent_context.pipedrive_deal_id
        activity_id = persistent_context.tour_activity_id if action == "reschedule" else None
        
        # Calculate child level if we have valid data
        child_level = None
        if (persistent_context.child_dob and 
            persistent_context.preferred_enrollment_date and 
            persistent_context.preferred_enrollment_date != "Unknown"):
            child_level = calculate_child_level(
                persistent_context.child_dob,
                persistent_context.preferred_enrollment_date
            )
        
        # Execute the booking
        if action == "book":
            result = asyncio.run(create_tour_activity(
                deal_id=deal_id,
                tour_date=tour_date,
                tour_time=tour_time,
                child_name=persistent_context.child_name,
                child_level=child_level
            ))
            
            # Update context with booking details
            if result.status == "success":
                persistent_context.tour_activity_id = result.activity_id
                persistent_context.tour_scheduled_date = tour_date
                persistent_context.tour_scheduled_time = tour_time
                persistent_context.tour_booked_at = datetime.utcnow().isoformat()
                redis_manager.save_persistent_context(inbox_id, contact_id, persistent_context)
            
            return {
                "status": result.status,
                "action": "booked",
                "activity_id": result.activity_id,
                "tour_date": result.tour_date,
                "tour_time": result.tour_time,
                "subject": result.subject,
                "message": result.message,
                "error": result.error
            }
            
        else:  # reschedule
            if not activity_id:
                return {
                    "status": "error",
                    "error": "No existing tour found to reschedule"
                }
            
            result = asyncio.run(reschedule_tour_activity(
                activity_id=activity_id,
                tour_date=tour_date,
                tour_time=tour_time,
                child_name=persistent_context.child_name,
                child_level=child_level
            ))
            
            # Update context with new booking details
            if result.status == "success":
                persistent_context.tour_scheduled_date = tour_date
                persistent_context.tour_scheduled_time = tour_time
                redis_manager.save_persistent_context(inbox_id, contact_id, persistent_context)
            
            return {
                "status": result.status,
                "action": "rescheduled",
                "activity_id": result.activity_id,
                "tour_date": result.tour_date,
                "tour_time": result.tour_time,
                "subject": result.subject,
                "message": result.message,
                "error": result.error
            }
        
    except Exception as e:
        logger.error(f"Error in book_or_reschedule_tour: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


def _analyze_booking_requirements(
    persistent_context: Any,
    action: str,
    confirmed_fields: List[str]
) -> Dict[str, Any]:
    """
    Analyze what's needed for booking and determine next action.
    
    Returns workflow guidance including:
    - stage: Where we are in the process
    - next_action: What the bot should do
    - prompt_for: Specific field to ask for
    - reason: Why we need this
    - context_hint: Help for the LLM to ask naturally
    """
    
    # Analyzing booking requirements based on current context and action
    
    # Define the collection workflow stages and fields
    workflow = [
        # Stage 1: Parent Information
        {
            "stage": "parent_info",
            "fields": [
                {
                    "name": "parent_preferred_name",
                    "display": "your preferred name",
                    "question": "What name would you prefer us to use when we contact you?",
                    "why": "for our records",
                    "required": True
                },
                {
                    "name": "parent_preferred_email", 
                    "display": "your email address",
                    "question": "What's the best email to send the tour confirmation to?",
                    "why": "to send tour details",
                    "required": True
                }
            ]
        },
        # Stage 2: Child Information
        {
            "stage": "child_info",
            "fields": [
                {
                    "name": "child_name",
                    "display": "your child's name",
                    "question": "What's your child's name?",
                    "why": "for the tour booking",
                    "required": True
                },
                {
                    "name": "child_dob",
                    "display": "your child's date of birth",
                    "question": "What's your child's date of birth? (This helps us prepare age-appropriate activities for the tour)",
                    "why": "to determine the appropriate program",
                    "required": True,
                    "format": "YYYY-MM-DD"
                },
                {
                    "name": "preferred_enrollment_date",
                    "display": "when you're looking to enroll",
                    "question": "When are you hoping to start? (Month and year is fine)",
                    "why": "to discuss relevant programs during your tour",
                    "required": False,
                    "format": "YYYY-MM or YYYY-MM-DD"
                }
            ]
        },
        # Stage 3: Deal Creation (automatic)
        {
            "stage": "deal_creation",
            "automatic": True,
            "check": "pipedrive_deal_id"
        }
    ]
    
    # Count total required fields for progress tracking
    total_required = sum(
        len([f for f in stage["fields"] if f.get("required", False)])
        for stage in workflow 
        if "fields" in stage
    )
    completed_required = 0
    
    # Check each stage
    for stage in workflow:
        # Handle automatic stages
        if stage.get("automatic"):
            check_field = stage.get("check")
            if check_field and not getattr(persistent_context, check_field, None):
                # Need to create deal
                if action == "book":
                    return {
                        "status": "need_deal",
                        "stage": "deal_creation",
                        "next_action": "create_deal",
                        "prompt_for": None,
                        "reason": "Creating enrollment opportunity in system",
                        "progress": f"{completed_required}/{total_required} required fields collected"
                    }
            continue
        
        # Check fields in this stage
        for field in stage["fields"]:
            field_name = field["name"]
            field_value = getattr(persistent_context, field_name, None)
            is_required = field.get("required", False)
            
            # Debug log field checking
            # Check if field is populated
            
            # Check if field exists
            if not field_value or field_value == "Unknown":
                if is_required:
                    # Missing required field
                    # This is the next required field to collect
                    return {
                        "status": "need_info",
                        "stage": stage["stage"],
                        "next_action": "ask_user",
                        "prompt_for": field_name,
                        "reason": field["why"],
                        "question": field["question"],
                        "context_hint": f"Ask naturally for {field['display']}",
                        "progress": f"{completed_required}/{total_required} required fields collected"
                    }
            else:
                # Field exists
                if is_required:
                    completed_required += 1
                    # Field already has value
                    
                # Skip confirmation logic - if the field has a value, we trust it
                # The user can always correct it if needed
    
    # Check for Pipedrive deal
    if not persistent_context.pipedrive_deal_id:
        return {
            "status": "need_deal",
            "stage": "deal_creation",
            "next_action": "create_deal",
            "prompt_for": None,
            "reason": "Setting up your enrollment record",
            "progress": f"{completed_required}/{total_required} required fields collected"
        }
    
    # All requirements met!
    return {
        "status": "ready",
        "stage": "complete",
        "progress": f"{total_required}/{total_required} required fields collected"
    }