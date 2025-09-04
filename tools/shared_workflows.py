"""
Shared workflow logic for tools that need parent/child information
"""

from typing import Dict, Any, List


def analyze_data_collection_requirements(
    persistent_context: Any,
    purpose: str,  # "tour_booking" or "callback_request"
    confirmed_fields: List[str] = None,
    tour_date: str = None,  # Required for tour_booking
    tour_time: str = None   # Required for tour_booking
) -> Dict[str, Any]:
    """
    Analyze what information needs to be collected for various workflows.
    
    Both tour booking and callback requests need the same parent/child info
    to create a Pipedrive deal before proceeding with their specific actions.
    
    Args:
        persistent_context: Current persistent context
        purpose: What we're collecting data for
        confirmed_fields: Fields already confirmed in this session
        
    Returns:
        Analysis result with next steps
    """
    
    confirmed_fields = confirmed_fields or []
    
    # For tour bookings, check date/time are provided first
    if purpose == "tour_booking":
        if not tour_date or not tour_time:
            return {
                "status": "need_tour_details",
                "stage": "tour_scheduling",
                "next_action": "ask_user",
                "prompt_for": "tour_date_time",
                "reason": "to schedule your tour",
                "context_hint": "Need to know when they want to schedule the tour",
                "progress": "Tour date/time required"
            }
    
    # Analyzing data requirements based on current context
    
    # Define the collection workflow stages and fields
    workflow = [
        # Stage 1: Parent Information
        {
            "stage": "parent_info",
            "fields": [
                {
                    "name": "parent_preferred_name",
                    "display": "your name",
                    "question": "What's your name?",
                    "why": "for our records",
                    "required": True
                },
                {
                    "name": "parent_preferred_email", 
                    "display": "your email address",
                    "question": "What's the best email to reach you at?" if purpose == "callback_request" 
                              else "What's the best email to send the tour confirmation to?",
                    "why": "to send you information" if purpose == "callback_request" 
                          else "to send tour details",
                    "required": True
                },
                {
                    "name": "parent_preferred_phone",
                    "display": "your phone number", 
                    "question": "What's the best phone number to call you back on?" if purpose == "callback_request"
                              else "What's your phone number for our records?",
                    "why": "for the callback" if purpose == "callback_request" 
                          else "for our records",
                    "required": True if purpose == "callback_request" else False
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
                    "why": "for the tour booking" if purpose == "tour_booking" else "for our records",
                    "required": True
                },
                {
                    "name": "child_dob",
                    "display": "your child's date of birth",
                    "question": "What's your child's date of birth? (This helps us prepare age-appropriate activities for the tour)" if purpose == "tour_booking"
                              else "What's your child's date of birth? (This helps us understand which programs are suitable)",
                    "why": "to determine the appropriate program",
                    "required": True,
                    "format": "YYYY-MM-DD"
                },
                {
                    "name": "preferred_enrollment_date",
                    "display": "when you're looking to enroll" if purpose == "tour_booking" else "when you'd like to enroll",
                    "question": "When are you hoping to start? (Month and year is fine)" if purpose == "tour_booking"
                              else "When are you hoping to enroll your child? (You can give us a month like 'January 2024')",
                    "why": "to discuss relevant programs during your tour" if purpose == "tour_booking" 
                          else "to understand your timeline",
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
                return {
                    "status": "need_deal",
                    "stage": "deal_creation",
                    "next_action": "create_deal",
                    "prompt_for": None,
                    "reason": "Creating enrollment opportunity in system",
                    "progress": f"{completed_required}/{total_required} required fields collected"
                }
            continue
        
        # Check fields in this stage - collect ALL missing fields before returning
        missing_required_fields = []
        missing_optional_fields = []
        present_required_fields = []
        
        for field in stage["fields"]:
            field_name = field["name"]
            field_value = getattr(persistent_context, field_name, None)
            is_required = field.get("required", False)
            
            if not field_value or field_value == "Unknown":
                if is_required:
                    missing_required_fields.append(field)
                else:
                    missing_optional_fields.append(field)
            else:
                # Field exists
                if is_required:
                    completed_required += 1
                    present_required_fields.append(field)
        
        # If we have missing required fields in this stage, return batch collection
        if missing_required_fields:
            # Smart skip logic: for tours only, if we have name + email, phone is optional
            if (stage["stage"] == "parent_info" and 
                purpose == "tour_booking" and 
                len(present_required_fields) >= 2):
                # Have name + email, that's enough for tours (phone is optional)
                continue
                
            # Collect all missing fields (required + optional) as a batch
            all_missing_fields = missing_required_fields + missing_optional_fields
            field_names = [f["name"] for f in all_missing_fields]
            questions = {f["name"]: f["question"] for f in all_missing_fields}
            
            # Build context hint based on stage
            if stage["stage"] == "parent_info":
                context_hint = "Collect parent contact details together. You can suggest using their WhatsApp name/phone if available in the context."
            elif stage["stage"] == "child_info":
                required_count = len(missing_required_fields)
                optional_count = len(missing_optional_fields)
                if required_count > 0 and optional_count > 0:
                    context_hint = f"Collect child information together ({required_count} required fields, {optional_count} optional field - try to get all but don't insist on optional)."
                elif required_count > 0:
                    context_hint = f"Collect required child information together."
                else:
                    # Only optional fields missing, skip this stage
                    continue
            else:
                context_hint = f"Collect {stage['stage']} information together."
            
            return {
                "status": "need_info",
                "stage": stage["stage"],
                "next_action": "ask_user_batch",
                "prompt_for": field_names,
                "questions": questions,
                "reason": f"to collect {stage['stage'].replace('_', ' ')}",
                "context_hint": context_hint,
                "progress": f"{completed_required}/{total_required} required fields collected"
            }
    
    # Check for Pipedrive deal (not needed for callback requests that just create notes)
    if not persistent_context.pipedrive_deal_id:
        return {
            "status": "need_deal",
            "stage": "deal_creation",
            "next_action": "create_deal",
            "prompt_for": None,
            "reason": "Setting up your enrollment record" if purpose == "tour_booking" else "Creating enrollment opportunity in system",
            "progress": f"{completed_required}/{total_required} required fields collected"
        }
    
    # All requirements met
    return {
        "status": "ready",
        "stage": "complete",
        "next_action": "proceed",
        "progress": f"{completed_required}/{total_required} required fields collected",
        "deal_id": persistent_context.pipedrive_deal_id
    }