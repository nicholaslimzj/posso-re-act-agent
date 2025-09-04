"""
Tool for managing existing tours (reschedule/cancel)
"""

import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger

from context.models import FullContext, PersistentContext, TourStatus
from integrations.pipedrive import reschedule_tour_activity, cancel_tour_activity, add_note_to_deal, calculate_child_level


def manage_existing_tour(
    context: FullContext,
    action: str,  # "reschedule" or "cancel"
    new_date: Optional[str] = None,  # For reschedule: YYYY-MM-DD
    new_time: Optional[str] = None,  # For reschedule: HH:MM
    reason: Optional[str] = None  # For cancel: reason
) -> Dict[str, Any]:
    """
    Manage an existing tour booking (reschedule or cancel).
    
    Args:
        context: Full context containing runtime and persistent data
        action: "reschedule" or "cancel"
        new_date: New tour date for reschedule (YYYY-MM-DD)
        new_time: New tour time for reschedule (HH:MM)
        reason: Reason for cancellation
        
    Returns:
        Dict with action result
    """
    try:
        # Extract what we need from context
        persistent_context = context.persistent
        runtime_context = context.runtime
        school_id = runtime_context.school_id
        
        logger.info(f"manage_existing_tour called for school {school_id}")
        logger.info(f"  Action: {action}, New date: {new_date}, New time: {new_time}")
        
        # Check if we have persistent context
        if not persistent_context:
            return {
                "status": "error",
                "error": "No booking information found",
                "message": "I couldn't find any tour booking for you. Would you like to book a new tour?"
            }
        
        # Check if they have an existing tour
        activity_id = persistent_context.tour_activity_id
        if not activity_id:
            return {
                "status": "error", 
                "error": "No existing tour found",
                "message": "I don't see any scheduled tour for you. Would you like to book a new tour?"
            }
        
        if action == "cancel":
            # Cancel the tour
            result = asyncio.run(cancel_tour_activity(
                activity_id=activity_id,
                parent_name=persistent_context.parent_preferred_name,
                reason=reason
            ))
            
            if result.get("status") == "success":
                # Clear tour info from context
                persistent_context.tour_activity_id = None
                persistent_context.tour_scheduled_date = None
                persistent_context.tour_scheduled_time = None
                persistent_context.tour_status = "cancelled"
                # Context will be saved by the caller
                
                # Add note to deal if exists
                if persistent_context.pipedrive_deal_id:
                    note_content = f"❌ TOUR CANCELLED\n"
                    note_content += f"Original date: {persistent_context.tour_scheduled_date} at {persistent_context.tour_scheduled_time}\n"
                    if reason:
                        note_content += f"Reason: {reason}\n"
                    note_content += f"Cancelled at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    
                    asyncio.run(add_note_to_deal(
                        deal_id=persistent_context.pipedrive_deal_id,
                        content=note_content,
                        school_id=school_id
                    ))
                
                return {
                    "status": "success",
                    "action": "cancelled",
                    "message": "Your tour has been cancelled. Would you like to book a new tour for a different date?"
                }
            else:
                return {
                    "status": "error",
                    "error": result.get("error"),
                    "message": "I had trouble cancelling your tour. Please try again or contact us directly."
                }
                
        elif action == "reschedule":
            # Validate new date/time
            if not new_date or not new_time:
                return {
                    "status": "need_info",
                    "prompt_for": "date_time",
                    "message": "What date and time would you like to reschedule to?",
                    "current_booking": f"{persistent_context.tour_scheduled_date} at {persistent_context.tour_scheduled_time}"
                }
            
            # Calculate child level if we have the data
            child_level = None
            if (persistent_context.child_dob and 
                persistent_context.preferred_enrollment_date and 
                persistent_context.preferred_enrollment_date != "Unknown"):
                child_level = calculate_child_level(
                    persistent_context.child_dob,
                    persistent_context.preferred_enrollment_date
                )
            
            # Reschedule the tour
            result = asyncio.run(reschedule_tour_activity(
                activity_id=activity_id,
                tour_date=new_date,
                tour_time=new_time,
                child_name=persistent_context.child_name,
                child_level=child_level
            ))
            
            if result.status == "success":
                # Save old details for the note
                old_date = persistent_context.tour_scheduled_date
                old_time = persistent_context.tour_scheduled_time
                
                # Update context with new tour details
                persistent_context.tour_scheduled_date = new_date
                persistent_context.tour_scheduled_time = new_time
                persistent_context.tour_status = TourStatus.SCHEDULED
                # Context will be saved by the caller
                
                # Add note to deal if exists
                if persistent_context.pipedrive_deal_id:
                    note_content = f"🔄 TOUR RESCHEDULED\n"
                    note_content += f"Old: {old_date} at {old_time}\n"
                    note_content += f"New: {new_date} at {new_time}\n"
                    if reason:
                        note_content += f"Reason: {reason}\n"
                    note_content += f"Rescheduled at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    
                    asyncio.run(add_note_to_deal(
                        deal_id=persistent_context.pipedrive_deal_id,
                        content=note_content,
                        school_id=school_id
                    ))
                
                # Format display date
                display_date = datetime.strptime(new_date, '%Y-%m-%d').strftime('%A, %B %d, %Y')
                
                return {
                    "status": "success",
                    "action": "rescheduled",
                    "message": f"Your tour has been rescheduled to {display_date} at {new_time}.",
                    "old_date": old_date,
                    "old_time": old_time,
                    "new_date": new_date,
                    "new_time": new_time
                }
            else:
                return {
                    "status": "error",
                    "error": result.error,
                    "message": "I had trouble rescheduling your tour. Please try again or contact us directly."
                }
        else:
            return {
                "status": "error",
                "error": f"Invalid action: {action}",
                "message": "I can only reschedule or cancel tours."
            }
            
    except Exception as e:
        logger.error(f"Error in manage_existing_tour: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


# Backward compatibility wrapper removed - use manage_existing_tour directly