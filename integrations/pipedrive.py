"""
Pipedrive integration functions for tour booking and activity management.
"""

from typing import Optional, Set, Dict, Any
from datetime import datetime
from loguru import logger
import httpx

from config import settings
from models.pipedrive_models import (
    PipedriveActivity,
    PipedriveListResponse,
    TourBookingRequest,
    TourBookingResponse,
    CreateActivityRequest,
    UpdateActivityRequest,
    ChildLevelCalculation,
    CreatePersonRequest,
    CreateDealRequest,
    PipedrivePerson,
    PipedriveDeal
)


async def get_blocked_slots(start_date: str, end_date: str) -> Set[str]:
    """
    Get all blocked time slots from Pipedrive activities.
    
    This includes:
    - All active activities (meetings, calls, tasks, etc.) at specific times
    - Whole-day activities that block entire days
    
    Args:
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD
        
    Returns:
        Set of blocked slots in format:
        - "YYYY-MM-DD_HH:MM" for specific time slots
        - "YYYY-MM-DD_WHOLE_DAY" for whole-day blocks
    """
    try:
        # Build Pipedrive V1 API URL for activities with date range
        api_url = settings.PIPEDRIVE_API_URL  # https://api.pipedrive.com/v1
        api_key = settings.PIPEDRIVE_API_KEY
        
        url = f"{api_url}/activities?start_date={start_date}&end_date={end_date}&api_token={api_key}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code != 200:
                logger.warning(f"Failed to fetch activities from Pipedrive: {response.status_code}")
                return set()
            
            # Parse response with model
            response_data = response.json()
            logger.debug(f"Pipedrive API response success: {response_data.get('success')}")
            
            list_response = PipedriveListResponse(**response_data)
            if not list_response.success or not list_response.data:
                logger.warning("No activities found in Pipedrive response")
                return set()
            
            logger.info(f"Found {len(list_response.data)} activities in Pipedrive")
            
            booked = set()
            for activity_data in list_response.data:
                # Parse each activity with model
                activity = PipedriveActivity(**activity_data)
                
                logger.debug(f"Activity: {activity.subject} - Type: {activity.type} - Done: {activity.done}")
                logger.debug(f"  Due date: {activity.due_date} - Due time: {activity.due_time}")
                
                # Skip only if activity is marked as done/cancelled
                if activity.is_cancelled():
                    logger.debug(f"  Skipping cancelled/done activity")
                    continue
                
                # Check if this is a whole-day activity (no specific time)
                if not activity.due_time:
                    # Block all slots for this day
                    sg_date = activity.due_date  # No timezone conversion needed for all-day events
                    # Add a special marker for whole-day blocking
                    booked.add(f"{sg_date}_WHOLE_DAY")
                    logger.info(f"Blocking entire day {sg_date}: {activity.subject}")
                else:
                    # Block specific time slot
                    sg_date = activity.get_singapore_date()
                    sg_time = activity.get_singapore_time()
                    
                    if sg_date and sg_time:
                        slot_key = f"{sg_date}_{sg_time}"
                        booked.add(slot_key)
                        logger.info(f"Blocking time slot {slot_key}: {activity.subject}")
            
            return booked
            
    except Exception as e:
        logger.error(f"Error fetching booked slots: {e}")
        return set()


async def create_tour_activity(
    deal_id: int,
    tour_date: str,
    tour_time: str,
    child_name: Optional[str] = None,
    child_level: Optional[str] = None
) -> TourBookingResponse:
    """
    Create a tour activity in Pipedrive.
    
    Args:
        deal_id: Pipedrive deal ID
        tour_date: Date in YYYY-MM-DD format
        tour_time: Time in HH:MM format (Singapore time)
        child_name: Child's name for activity subject
        child_level: Education level for activity subject
        
    Returns:
        TourBookingResponse with activity details or error
    """
    try:
        # Create booking request model
        booking = TourBookingRequest(
            deal_id=deal_id,
            tour_date=tour_date,
            tour_time=tour_time,
            child_name=child_name,
            child_level=child_level
        )
        
        # Get UTC datetime
        utc_date, utc_time = booking.get_utc_datetime()
        subject = booking.get_subject()
        
        # Create activity request
        activity_request = CreateActivityRequest(
            subject=subject,
            type="meeting",
            deal_id=deal_id,
            due_date=utc_date,
            due_time=utc_time,
            duration="01:00"
        )
        
        api_v2_url = settings.PIPEDRIVE_APIV2_URL
        api_key = settings.PIPEDRIVE_API_KEY
        
        url = f"{api_v2_url}/api/v2/activities?api_token={api_key}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=activity_request.dict())
            if response.status_code not in [200, 201]:
                logger.error(f"Failed to create tour activity: {response.text}")
                return TourBookingResponse(
                    status="error",
                    tour_date=tour_date,
                    tour_time=tour_time,
                    subject=subject,
                    message="Failed to create tour booking",
                    error=f"API error: {response.status_code}"
                )
            
            data = response.json()
            activity_data = data.get("data", {})
            
            # Format success message
            display_date = datetime.strptime(tour_date, '%Y-%m-%d').strftime('%A, %B %d, %Y')
            
            return TourBookingResponse(
                status="success",
                activity_id=activity_data.get("id"),
                tour_date=tour_date,
                tour_time=tour_time,
                subject=subject,
                message=f"Tour booked for {display_date} at {tour_time}"
            )
            
    except Exception as e:
        logger.error(f"Error creating tour activity: {e}")
        return TourBookingResponse(
            status="error",
            tour_date=tour_date,
            tour_time=tour_time,
            subject="",
            message="Failed to create tour booking",
            error=str(e)
        )


async def reschedule_tour_activity(
    activity_id: int,
    tour_date: str,
    tour_time: str,
    child_name: Optional[str] = None,
    child_level: Optional[str] = None
) -> TourBookingResponse:
    """
    Reschedule an existing tour activity in Pipedrive.
    
    Args:
        activity_id: Existing activity ID to update
        tour_date: New date in YYYY-MM-DD format
        tour_time: New time in HH:MM format (Singapore time)
        child_name: Child's name for activity subject
        child_level: Education level for activity subject
        
    Returns:
        TourBookingResponse with updated details or error
    """
    try:
        # Create booking request model
        booking = TourBookingRequest(
            deal_id=0,  # Not needed for reschedule but required by model
            tour_date=tour_date,
            tour_time=tour_time,
            child_name=child_name,
            child_level=child_level,
            activity_id=activity_id
        )
        
        # Get UTC datetime
        utc_date, utc_time = booking.get_utc_datetime()
        subject = booking.get_subject()
        
        # Create update request
        update_request = UpdateActivityRequest(
            due_date=utc_date,
            due_time=utc_time,
            subject=subject
        )
        
        api_v2_url = settings.PIPEDRIVE_API_V2_URL
        api_key = settings.PIPEDRIVE_API_KEY
        
        url = f"{api_v2_url}/api/v2/activities/{activity_id}?api_token={api_key}"
        
        async with httpx.AsyncClient() as client:
            # Use dict with exclude_none to only send fields that are set
            response = await client.patch(url, json=update_request.dict(exclude_none=True))
            if response.status_code not in [200, 201]:
                logger.error(f"Failed to reschedule tour activity: {response.text}")
                return TourBookingResponse(
                    status="error",
                    activity_id=activity_id,
                    tour_date=tour_date,
                    tour_time=tour_time,
                    subject=subject,
                    message="Failed to reschedule tour",
                    error=f"API error: {response.status_code}"
                )
            
            # Format success message
            display_date = datetime.strptime(tour_date, '%Y-%m-%d').strftime('%A, %B %d, %Y')
            
            return TourBookingResponse(
                status="success",
                activity_id=activity_id,
                tour_date=tour_date,
                tour_time=tour_time,
                subject=subject,
                message=f"Tour rescheduled to {display_date} at {tour_time}"
            )
            
    except Exception as e:
        logger.error(f"Error rescheduling tour activity: {e}")
        return TourBookingResponse(
            status="error",
            activity_id=activity_id,
            tour_date=tour_date,
            tour_time=tour_time,
            subject="",
            message="Failed to reschedule tour",
            error=str(e)
        )


def calculate_child_level(birth_date: str, enrollment_date: str) -> str:
    """
    Calculate child's education level based on dates.
    
    Args:
        birth_date: Child's birth date (YYYY-MM-DD)
        enrollment_date: Expected enrollment date (YYYY-MM-DD or YYYY-MM)
        
    Returns:
        Level code (IF, PG, N1, N2, K1, K2)
    """
    try:
        # Use model for calculation
        calc = ChildLevelCalculation(
            birth_date=birth_date,
            enrollment_date=enrollment_date
        )
        return calc.calculate_level()
        
    except Exception as e:
        logger.error(f"Error calculating child level: {e}")
        return "TBD"


async def create_or_get_person(
    name: str,
    phone: Optional[str] = None,
    email: Optional[str] = None
) -> Optional[int]:
    """
    Create a person in Pipedrive or get existing person ID.
    
    Args:
        name: Person's full name
        phone: Phone number (optional)
        email: Email address (optional)
        
    Returns:
        Person ID if successful, None if failed
    """
    try:
        # For now, always create new (in production, would check for existing first)
        request = CreatePersonRequest(
            name=name,
            phones=[phone] if phone else None,
            emails=[email] if email else None
        )
        
        api_v2_url = settings.PIPEDRIVE_APIV2_URL
        api_key = settings.PIPEDRIVE_API_KEY
        
        url = f"{api_v2_url}/api/v2/persons?api_token={api_key}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=request.dict(exclude_none=True))
            if response.status_code not in [200, 201]:
                logger.error(f"Failed to create person: {response.text}")
                return None
            
            data = response.json()
            person_data = data.get("data", {})
            person_id = person_data.get("id")
            
            logger.info(f"Created person {person_id}: {name}")
            return person_id
            
    except Exception as e:
        logger.error(f"Error creating person: {e}")
        return None


async def create_enrollment_deal(
    parent_name: str,
    child_name: str,
    parent_phone: Optional[str] = None,
    parent_email: Optional[str] = None,
    child_dob: Optional[str] = None,
    enrollment_date: Optional[str] = None,
    school_id: str = "tampines"
) -> Dict[str, Any]:
    """
    Create an enrollment opportunity (deal) in Pipedrive.
    
    Args:
        parent_name: Parent's name
        child_name: Child's name  
        parent_phone: Parent's phone (optional)
        parent_email: Parent's email (optional)
        child_dob: Child's date of birth (optional)
        enrollment_date: Preferred enrollment date (optional)
        school_id: School branch ID
        
    Returns:
        Dict with deal_id and person_id, or error
    """
    try:
        # First, create or get the person (parent)
        person_id = await create_or_get_person(parent_name, parent_phone, parent_email)
        if not person_id:
            return {
                "status": "error",
                "error": "Failed to create parent contact"
            }
        
        # Get pipeline and stage IDs from config (would come from school config in production)
        pipeline_id = 1  # Default pipeline
        stage_id = 1  # "Lead In" stage
        
        # Calculate child level if we have the data
        child_level = None
        if child_dob and enrollment_date:
            child_level = calculate_child_level(child_dob, enrollment_date)
        
        # Format deal title
        title = f"{parent_name} - {child_name}"
        
        # Prepare custom fields
        custom_fields = {}
        if child_name:
            custom_fields["child_name"] = child_name
        if child_dob:
            custom_fields["child_dob"] = child_dob
        if child_level:
            custom_fields["child_level"] = child_level
        if enrollment_date:
            custom_fields["preferred_enrollment"] = enrollment_date
        
        # Create the deal
        request = CreateDealRequest(
            title=title,
            person_id=person_id,
            pipeline_id=pipeline_id,
            stage_id=stage_id,
            custom_fields=custom_fields if custom_fields else None
        )
        
        api_v2_url = settings.PIPEDRIVE_APIV2_URL
        api_key = settings.PIPEDRIVE_API_KEY
        
        url = f"{api_v2_url}/api/v2/deals?api_token={api_key}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=request.dict(exclude_none=True))
            if response.status_code not in [200, 201]:
                logger.error(f"Failed to create deal: {response.text}")
                return {
                    "status": "error",
                    "error": f"Failed to create enrollment opportunity: {response.status_code}"
                }
            
            data = response.json()
            deal_data = data.get("data", {})
            
            logger.info(f"Created deal {deal_data.get('id')}: {title}")
            
            return {
                "status": "success",
                "deal_id": deal_data.get("id"),
                "person_id": person_id,
                "title": title,
                "message": "Enrollment opportunity created successfully"
            }
            
    except Exception as e:
        logger.error(f"Error creating enrollment deal: {e}")
        return {
            "status": "error",
            "error": str(e)
        }