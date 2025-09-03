"""
Tool for checking available tour slots.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta, date
from loguru import logger
import pytz
import asyncio

from config.school_manager import SchoolManager
from integrations.pipedrive import get_blocked_slots


def check_tour_slots(
    inbox_id: int,
    contact_id: str,
    preferences: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Check available tour slots based on preferences and existing bookings.
    
    Args:
        inbox_id: Chatwoot inbox ID (used to get school config)
        contact_id: Contact ID (for context)
        preferences: Optional dict with:
            - date: Specific date (YYYY-MM-DD)
            - day_of_week: Day name (Monday, Tuesday, etc.)
            - time_preference: "morning" | "afternoon" | specific time (HH:MM)
            - next_week: bool - if True, check next week instead of this week
    
    Returns:
        Dictionary with available slots organized by date
    """
    try:
        # Get school configuration
        school_manager = SchoolManager()
        school_config = school_manager.get_school_config(str(inbox_id))
        if not school_config:
            # Fallback to default
            school_config = {
                "tour_slots": ["10:00", "13:00", "15:00"],
                "working_days": [1, 2, 3, 4, 5]
            }
        
        tour_slots = school_config.get("tour_slots", ["10:00", "13:00", "15:00"])
        working_days = school_config.get("working_days", [1, 2, 3, 4, 5])
        
        # Determine the reference date based on preferences
        reference_date = _determine_reference_date(preferences)
        
        # Get start of week (Monday) for the reference date
        start_date = _get_week_start(reference_date)
        
        # Calculate end date (14 days from start)
        end_date = start_date + timedelta(days=13)
        
        # Get blocked slots from Pipedrive (all activities, not just tours)
        blocked_slots = asyncio.run(get_blocked_slots(
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        ))
        
        logger.debug(f"Checking availability from {start_date} to {end_date}")
        logger.debug(f"Found {len(blocked_slots)} blocked slots: {blocked_slots}")
        logger.debug(f"Tour slots to check: {tour_slots}")
        logger.debug(f"Working days: {working_days}")
        
        # Build availability map
        availability = {}
        singapore_tz = pytz.timezone('Asia/Singapore')
        today = datetime.now(singapore_tz).date()
        logger.debug(f"Today's date: {today}")
        
        current_date = start_date
        while current_date <= end_date:
            # Skip past dates and today
            if current_date <= today:
                current_date += timedelta(days=1)
                continue
            
            # Skip non-working days
            if current_date.isoweekday() not in working_days:
                current_date += timedelta(days=1)
                continue
            
            date_str = current_date.strftime("%Y-%m-%d")
            day_name = current_date.strftime("%A")
            formatted_date = current_date.strftime("%B %d, %Y")
            
            # Check if entire day is blocked
            whole_day_key = f"{date_str}_WHOLE_DAY"
            if whole_day_key in blocked_slots:
                logger.debug(f"Entire day {date_str} is blocked")
                current_date += timedelta(days=1)
                continue
            
            # Check each tour slot for this date
            available_times = []
            for slot_time in tour_slots:
                # Check if slot matches time preference
                if not _matches_time_preference(slot_time, preferences.get("time_preference") if preferences else None):
                    logger.debug(f"  Slot {slot_time} on {date_str} doesn't match time preference")
                    continue
                
                # Check if slot is already blocked
                slot_key = f"{date_str}_{slot_time}"
                logger.debug(f"  Checking slot key: {slot_key} - Blocked: {slot_key in blocked_slots}")
                if slot_key not in blocked_slots:
                    # Format time for display
                    hour = int(slot_time.split(":")[0])
                    am_pm = "AM" if hour < 12 else "PM"
                    display_hour = hour if hour <= 12 else hour - 12
                    if display_hour == 0:
                        display_hour = 12
                    formatted_time = f"{display_hour}:00 {am_pm}"
                    
                    available_times.append({
                        "time": slot_time,
                        "display": formatted_time,
                        "period": "morning" if hour < 12 else "afternoon"
                    })
            
            if available_times:
                availability[date_str] = {
                    "date": date_str,
                    "day": day_name,
                    "formatted": f"{day_name}, {formatted_date}",
                    "slots": available_times
                }
            
            current_date += timedelta(days=1)
        
        # Check if preferred date/time is available
        preferred_available = False
        if preferences:
            if preferences.get("date") and preferences["date"] in availability:
                if preferences.get("time_preference"):
                    # Check if specific time is available
                    for slot in availability[preferences["date"]]["slots"]:
                        if slot["time"] == preferences.get("time_preference"):
                            preferred_available = True
                            break
                else:
                    preferred_available = True
        
        # Format response
        total_available = sum(len(day["slots"]) for day in availability.values())
        logger.info(f"Availability check complete: {total_available} slots available across {len(availability)} days")
        logger.info(f"Blocked slots: {blocked_slots}")
        
        return {
            "status": "success",
            "available_dates": list(availability.keys()),
            "availability": availability,
            "preferred_available": preferred_available,
            "total_slots": total_available,
            "date_range": {
                "start": start_date.strftime("%Y-%m-%d"),
                "end": end_date.strftime("%Y-%m-%d")
            }
        }
        
    except Exception as e:
        logger.error(f"Error checking tour slots: {e}")
        return {
            "status": "error",
            "error": str(e),
            "available_dates": [],
            "availability": {}
        }


def _determine_reference_date(preferences: Optional[Dict[str, Any]]) -> date:
    """
    Determine the reference date based on preferences.
    
    Args:
        preferences: User preferences
        
    Returns:
        Reference date to start checking from
    """
    singapore_tz = pytz.timezone('Asia/Singapore')
    today = datetime.now(singapore_tz).date()
    
    if not preferences:
        # Default to tomorrow
        return today + timedelta(days=1)
    
    # If specific date provided
    if preferences.get("date"):
        try:
            preferred_date = datetime.strptime(preferences["date"], "%Y-%m-%d").date()
            # Don't allow past dates or today
            if preferred_date <= today:
                return today + timedelta(days=1)
            return preferred_date
        except ValueError:
            pass
    
    # If day of week provided
    if preferences.get("day_of_week"):
        day_name = preferences["day_of_week"].lower()
        day_map = {
            "monday": 1, "tuesday": 2, "wednesday": 3,
            "thursday": 4, "friday": 5, "saturday": 6, "sunday": 7
        }
        
        if day_name in day_map:
            target_day = day_map[day_name]
            current_day = today.isoweekday()
            
            # Calculate days until target day
            if preferences.get("next_week"):
                # Force next week
                days_ahead = target_day - current_day + 7
            else:
                # Find nearest occurrence
                days_ahead = target_day - current_day
                if days_ahead <= 0:  # Target day already happened this week
                    days_ahead += 7
            
            return today + timedelta(days=days_ahead)
    
    # Default to tomorrow
    return today + timedelta(days=1)


def _get_week_start(ref_date: date) -> date:
    """
    Get Monday of the week containing the reference date.
    
    Args:
        ref_date: Reference date
        
    Returns:
        Monday of that week
    """
    # Get Monday of the week (isoweekday: Monday=1, Sunday=7)
    days_since_monday = ref_date.isoweekday() - 1
    return ref_date - timedelta(days=days_since_monday)


def _matches_time_preference(slot_time: str, preference: Optional[str]) -> bool:
    """
    Check if a time slot matches the user's preference.
    
    Args:
        slot_time: Time in HH:MM format
        preference: "morning", "afternoon", or specific time
        
    Returns:
        True if matches or no preference
    """
    if not preference:
        return True
    
    hour = int(slot_time.split(":")[0])
    
    if preference == "morning":
        return hour < 12
    elif preference == "afternoon":
        return hour >= 12
    elif ":" in preference:
        # Specific time requested
        return slot_time == preference
    
    return True