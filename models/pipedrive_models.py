"""
Pydantic models for Pipedrive API integration.
Handles request/response validation and type safety.
"""

from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, date
from pydantic import BaseModel, Field, validator
from loguru import logger


# ============== Request Models ==============

class CreatePersonRequest(BaseModel):
    """Request model for creating a person in Pipedrive"""
    name: str
    phones: Optional[List[Dict[str, str]]] = None
    emails: Optional[List[Dict[str, str]]] = None
    
    @validator('phones', pre=True)
    def format_phones(cls, v, values):
        """Ensure phones are in correct format"""
        if v and isinstance(v[0], str):
            # Convert simple string to proper format
            return [{"value": v[0], "primary": True, "label": "mobile"}]
        return v
    
    @validator('emails', pre=True)
    def format_emails(cls, v, values):
        """Ensure emails are in correct format"""
        if v and isinstance(v[0], str):
            # Convert simple string to proper format
            return [{"value": v[0], "primary": True, "label": "main"}]
        return v


class CreateDealRequest(BaseModel):
    """Request model for creating a deal in Pipedrive"""
    title: str
    person_id: int
    pipeline_id: int
    stage_id: int
    custom_fields: Optional[Dict[str, Any]] = None


class CreateActivityRequest(BaseModel):
    """Request model for creating an activity in Pipedrive"""
    subject: str
    type: Literal["meeting", "call", "task", "deadline", "email", "lunch"]
    deal_id: int
    due_date: str  # YYYY-MM-DD format
    due_time: str  # HH:MM format in UTC
    duration: str = "01:00"  # HH:MM format
    person_id: Optional[int] = None
    
    @validator('due_date')
    def validate_date_format(cls, v):
        """Ensure date is in YYYY-MM-DD format"""
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
    
    @validator('due_time')
    def validate_time_format(cls, v):
        """Ensure time is in HH:MM format"""
        if not v or ':' not in v:
            raise ValueError("Time must be in HH:MM format")
        parts = v.split(':')
        if len(parts) != 2:
            raise ValueError("Time must be in HH:MM format")
        try:
            hour, minute = map(int, parts)
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid time values")
        except ValueError:
            raise ValueError("Time must be in HH:MM format with valid numbers")
        return v


class UpdateActivityRequest(BaseModel):
    """Request model for updating an activity"""
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    subject: Optional[str] = None
    done: Optional[bool] = None


# ============== Response Models ==============

class PipedrivePhone(BaseModel):
    """Phone number in Pipedrive format"""
    value: str
    primary: bool
    label: str


class PipedriveEmail(BaseModel):
    """Email in Pipedrive format"""
    value: str
    primary: bool
    label: str


class PipedrivePerson(BaseModel):
    """Person response from Pipedrive"""
    id: int
    name: str
    phones: Optional[List[PipedrivePhone]] = []
    emails: Optional[List[PipedriveEmail]] = []
    add_time: Optional[str] = None
    update_time: Optional[str] = None
    
    class Config:
        extra = "allow"  # Allow extra fields from API


class PipedriveDeal(BaseModel):
    """Deal response from Pipedrive"""
    id: int
    title: str
    person_id: Optional[int] = None
    pipeline_id: int
    stage_id: int
    status: str
    value: Optional[float] = None
    currency: Optional[str] = None
    add_time: Optional[str] = None
    update_time: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    
    class Config:
        extra = "allow"


class PipedriveActivity(BaseModel):
    """Activity response from Pipedrive"""
    id: int
    subject: str
    type: str
    deal_id: Optional[int] = None
    person_id: Optional[int] = None
    due_date: str
    due_time: Optional[str] = None
    duration: Optional[str] = None
    done: bool = False
    add_time: Optional[str] = None
    marked_as_done_time: Optional[str] = None
    
    class Config:
        extra = "allow"
    
    def is_tour(self) -> bool:
        """Check if this activity is a tour"""
        return self.type == "meeting" and "tour" in self.subject.lower()
    
    def is_cancelled(self) -> bool:
        """Check if this activity is cancelled"""
        return self.done or "CANCELLED" in self.subject.upper()
    
    def get_singapore_time(self) -> Optional[str]:
        """Convert UTC time to Singapore time"""
        if not self.due_time:
            return None
        
        try:
            # Parse time parts (HH:MM or HH:MM:SS)
            time_parts = self.due_time.split(":")
            utc_hour = int(time_parts[0])
            utc_minute = int(time_parts[1]) if len(time_parts) > 1 else 0
            
            # Convert hour to Singapore time (UTC+8)
            sg_hour = (utc_hour + 8) % 24
            
            # Return in HH:MM format
            return f"{sg_hour:02d}:{utc_minute:02d}"
        except Exception as e:
            logger.warning(f"Error parsing time {self.due_time}: {e}")
            return None
    
    def get_singapore_date(self) -> str:
        """Get the date in Singapore timezone"""
        if not self.due_time:
            return self.due_date
        
        try:
            utc_hour = int(self.due_time.split(":")[0])
            if utc_hour + 8 >= 24:
                # Next day in Singapore
                from datetime import datetime, timedelta
                activity_date = datetime.strptime(self.due_date, "%Y-%m-%d").date()
                activity_date = activity_date + timedelta(days=1)
                return activity_date.strftime("%Y-%m-%d")
            return self.due_date
        except:
            return self.due_date


class PipedriveNote(BaseModel):
    """Note response from Pipedrive"""
    id: int
    content: str
    deal_id: Optional[int] = None
    person_id: Optional[int] = None
    add_time: Optional[str] = None
    update_time: Optional[str] = None
    
    class Config:
        extra = "allow"


# ============== API Response Wrappers ==============

class PipedriveResponse(BaseModel):
    """Standard Pipedrive API response wrapper"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    error_info: Optional[str] = None
    
    class Config:
        extra = "allow"


class PipedriveListResponse(BaseModel):
    """Pipedrive API response for list endpoints"""
    success: bool
    data: Optional[List[Dict[str, Any]]] = None
    additional_data: Optional[Dict[str, Any]] = None
    
    class Config:
        extra = "allow"


# ============== Tour-specific Models ==============

class TourSlot(BaseModel):
    """Represents an available tour slot"""
    date: str  # YYYY-MM-DD
    time: str  # HH:MM in Singapore time
    is_available: bool = True
    
    def to_display(self) -> Dict[str, str]:
        """Convert to display format"""
        from datetime import datetime
        
        dt = datetime.strptime(self.date, "%Y-%m-%d")
        hour = int(self.time.split(":")[0])
        am_pm = "AM" if hour < 12 else "PM"
        display_hour = hour if hour <= 12 else hour - 12
        if display_hour == 0:
            display_hour = 12
        
        return {
            "date": self.date,
            "time": self.time,
            "day": dt.strftime("%A"),
            "formatted_date": dt.strftime("%B %d, %Y"),
            "formatted_time": f"{display_hour}:00 {am_pm}",
            "display": f"{dt.strftime('%A, %B %d, %Y')} at {display_hour}:00 {am_pm}"
        }


class TourBookingRequest(BaseModel):
    """Request to book or reschedule a tour"""
    deal_id: int
    tour_date: str  # YYYY-MM-DD
    tour_time: str  # HH:MM in Singapore time
    child_name: Optional[str] = None
    child_level: Optional[str] = None
    activity_id: Optional[int] = None  # For rescheduling
    
    def get_utc_datetime(self) -> tuple[str, str]:
        """Convert Singapore time to UTC date and time"""
        sg_hour, sg_minute = map(int, self.tour_time.split(":"))
        utc_hour = (sg_hour - 8) % 24
        utc_time = f"{utc_hour:02d}:{sg_minute:02d}"
        
        # Adjust date if needed
        actual_date = self.tour_date
        if sg_hour < 8:
            from datetime import datetime, timedelta
            tour_date_obj = datetime.strptime(self.tour_date, "%Y-%m-%d").date()
            actual_date = (tour_date_obj - timedelta(days=1)).strftime("%Y-%m-%d")
        
        return actual_date, utc_time
    
    def get_subject(self) -> str:
        """Generate activity subject"""
        from datetime import datetime
        formatted_date = datetime.strptime(self.tour_date, "%Y-%m-%d").strftime("%b %Y")
        return f"Tour - {self.child_level or 'TBD'} - {formatted_date} - {self.child_name or 'Parent'}"


class TourBookingResponse(BaseModel):
    """Response after booking/rescheduling a tour"""
    status: Literal["success", "error"]
    activity_id: Optional[int] = None
    tour_date: str
    tour_time: str
    subject: str
    message: str
    error: Optional[str] = None


# ============== Validation Helpers ==============

class ChildLevelCalculation(BaseModel):
    """Model for calculating child education level"""
    birth_date: str  # YYYY-MM-DD
    enrollment_date: str  # YYYY-MM-DD or YYYY-MM
    
    def calculate_level(self) -> str:
        """Calculate education level based on dates"""
        from datetime import datetime
        
        # Handle different date formats
        birth = datetime.strptime(self.birth_date, "%Y-%m-%d")
        
        # Handle partial enrollment dates
        if len(self.enrollment_date) == 7:  # YYYY-MM format
            enrollment = datetime.strptime(self.enrollment_date + "-01", "%Y-%m-%d")
        else:
            enrollment = datetime.strptime(self.enrollment_date, "%Y-%m-%d")
        
        # Calculate age in months at enrollment
        months_diff = (enrollment.year - birth.year) * 12 + (enrollment.month - birth.month)
        
        # Infant care: under 18 months
        if months_diff < 18:
            return "IF"
        
        # Age child turns in enrollment year
        age_in_enrollment_year = enrollment.year - birth.year
        
        # Preschool levels
        if age_in_enrollment_year == 2:
            return "PG"  # Playgroup
        elif age_in_enrollment_year == 3:
            return "N1"  # Nursery 1
        elif age_in_enrollment_year == 4:
            return "N2"  # Nursery 2
        elif age_in_enrollment_year == 5:
            return "K1"  # Kindergarten 1
        elif age_in_enrollment_year == 6:
            return "K2"  # Kindergarten 2
        else:
            return "PG" if months_diff >= 18 else "IF"