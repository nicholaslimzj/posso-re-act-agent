"""
Intelligent tour booking tool with workflow orchestration.
This tool handles the entire booking flow, determining what data is needed,
what should be confirmed, and what to collect next.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger
import asyncio

from integrations.pipedrive import (
    create_tour_activity,
    reschedule_tour_activity,
    calculate_child_level,
    create_enrollment_deal
)
from context.models import FullContext, TourStatus, TaskType, TaskStatus
from tools.shared_workflows import analyze_data_collection_requirements


def book_or_reschedule_tour(
    context: FullContext,
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
        context: Full context containing runtime and persistent data
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
        # Extract what we need from context
        persistent_context = context.persistent
        runtime_context = context.runtime
        inbox_id = runtime_context.inbox_id
        school_id = runtime_context.school_id
        
        logger.info(f"book_or_reschedule_tour called for school {school_id}")
        logger.info(f"  Action: {action}, Date: {tour_date}, Time: {tour_time}")
        
        confirmed_fields = confirmed_fields or []
        
        # Analyze what we have and what we need
        analysis = analyze_data_collection_requirements(
            persistent_context,
            purpose="tour_booking",
            confirmed_fields=confirmed_fields,
            tour_date=tour_date,
            tour_time=tour_time,
            runtime_context=runtime_context
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
                    school_id=school_id
                ))
                
                if deal_result.get("status") == "success":
                    # Save deal ID to context
                    persistent_context.pipedrive_deal_id = deal_result["deal_id"]
                    persistent_context.pipedrive_person_id = deal_result["person_id"]
                    # Context will be saved by the caller (agent/message_handler)
                    # We just update the in-memory object
                    
                    # Now retry the analysis with the deal created
                    analysis = analyze_data_collection_requirements(
                        persistent_context,
                        purpose="tour_booking",
                        confirmed_fields=confirmed_fields,
                        tour_date=tour_date,
                        tour_time=tour_time
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
                            "progress": analysis["progress"],
                            "important_note": "TOUR BOOKING IS NOT YET COMPLETE - still collecting required information"
                        }
                else:
                    return {
                        "status": "error",
                        "error": f"Failed to create enrollment record: {deal_result.get('error')}"
                    }
            else:
                # Regular case - need user input
                # Store tool response data for context continuity
                context.active.active_task_type = TaskType.TOUR_BOOKING
                context.active.active_task_status = TaskStatus.COLLECTING_INFO
                context.active.active_task_data = {
                    "last_tool_response": {
                        "tool": "book_tour",
                        "status": "need_info",
                        "stage": analysis["stage"],
                        "prompt_for": analysis["prompt_for"],
                        "progress": analysis["progress"],
                        "next_action": "If user provides the missing information, call update_contact_info to save it, then call book_tour again to continue"
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }
                # Context will be saved by the caller (agent/message_handler)
                
                return {
                    "status": "need_info",
                    "workflow_stage": analysis["stage"],
                    "next_action": analysis["next_action"],
                    "prompt_for": analysis["prompt_for"],
                    "reason": analysis["reason"],
                    "context_hint": analysis.get("context_hint"),
                    "question": analysis.get("question"),
                    "progress": analysis["progress"],
                    "important_note": "TOUR BOOKING IS NOT YET COMPLETE - still collecting required information"
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
                parent_name=persistent_context.parent_preferred_name,
                child_name=persistent_context.child_name,
                child_dob=persistent_context.child_dob,
                enrollment_date=persistent_context.preferred_enrollment_date,
                child_level=child_level
            ))
            
            # Update context with booking details
            if result.status == "success":
                persistent_context.tour_activity_id = result.activity_id
                persistent_context.tour_scheduled_date = tour_date
                persistent_context.tour_scheduled_time = tour_time
                persistent_context.tour_booked_at = datetime.utcnow().isoformat()
                persistent_context.tour_status = TourStatus.SCHEDULED
                
                # Clear active task since booking is complete
                context.active.active_task_type = None
                context.active.active_task_status = None
                context.active.active_task_data = {}
                # Context will be saved by the caller (agent/message_handler)
            
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
                persistent_context.tour_status = TourStatus.SCHEDULED
                
                # Clear active task since reschedule is complete
                context.active.active_task_type = None
                context.active.active_task_status = None
                context.active.active_task_data = {}
                # Context will be saved by the caller (agent/message_handler)
            
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
        import traceback
        logger.error(f"Error in book_or_reschedule_tour: {e}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        return {
            "status": "error",
            "error": str(e)
        }




# Backward compatibility wrapper removed - use book_or_reschedule_tour directly