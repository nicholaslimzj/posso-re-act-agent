"""
Shared workflow logic for tools that need parent/child information
"""

from typing import Dict, Any, List, Optional
from loguru import logger


def analyze_data_collection_requirements(
    persistent_context: Any,
    purpose: str,  # "tour_booking" or "callback_request"
    confirmed_fields: List[str] = None
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
    
    # Analyzing data requirements based on current context
    
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
                    "why": "for our records",
                    "required": True
                },
                {
                    "name": "child_dob",
                    "display": "your child's date of birth",
                    "question": "What's your child's date of birth? (This helps us understand which programs are suitable)",
                    "why": "to determine the appropriate program",
                    "required": True,
                    "format": "YYYY-MM-DD"
                },
                {
                    "name": "preferred_enrollment_date",
                    "display": "when you'd like to enroll",
                    "question": "When are you hoping to enroll your child? (You can give us a month like 'January 2024')",
                    "why": "to understand your timeline",
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
    
    # Check for Pipedrive deal
    if not persistent_context.pipedrive_deal_id:
        return {
            "status": "need_deal",
            "stage": "deal_creation",
            "next_action": "create_deal",
            "prompt_for": None,
            "reason": "Creating enrollment opportunity in system",
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