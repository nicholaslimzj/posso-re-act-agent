from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

class TaskType(str, Enum):
    TOUR_BOOKING = "tour_booking"
    CALLBACK_REQUEST = "callback_request" 
    RESCHEDULE = "reschedule"
    FAQ = "faq"

class TaskStatus(str, Enum):
    COLLECTING_INFO = "collecting_info"
    PROCESSING = "processing"
    COMPLETED = "completed"

class TourStatus(str, Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class PersistentContext(BaseModel):
    """Long-term state stored in Chatwoot additional_params"""
    
    # Customer Preferred Identity
    parent_preferred_name: Optional[str] = None
    parent_preferred_phone: Optional[str] = None
    parent_preferred_email: Optional[str] = None
    
    # Child Information
    child_name: Optional[str] = None
    child_dob: Optional[str] = None  # YYYY-MM-DD format
    preferred_enrollment_date: Optional[str] = None  # YYYY-MM-DD format
    
    # Pipedrive Integration
    pipedrive_person_id: Optional[int] = None
    pipedrive_deal_id: Optional[int] = None
    
    # Tour Booking Information
    tour_activity_id: Optional[int] = None
    tour_scheduled_date: Optional[str] = None  # YYYY-MM-DD
    tour_scheduled_time: Optional[str] = None  # HH:MM
    tour_booked_at: Optional[str] = None  # ISO timestamp
    tour_status: Optional[TourStatus] = None
    
    # Callback Request Information
    callback_requested: bool = False
    callback_preference: Optional[str] = None  # morning/afternoon/anytime
    callback_date: Optional[str] = None  # YYYY-MM-DD
    callback_requested_at: Optional[str] = None  # ISO timestamp
    callback_activity_id: Optional[int] = None

class RuntimeContext(BaseModel):
    """Session data retrieved at startup, not persisted"""
    
    # Session Identifiers
    conversation_id: str
    inbox_id: int
    school_id: str
    contact_id: str  # Unique identifier for the contact
    
    # WhatsApp Identity
    whatsapp_name: Optional[str] = None
    whatsapp_phone: Optional[str] = None
    
    # Conversation History
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    
    # School Configuration
    school_config: Dict[str, Any] = Field(default_factory=dict)
    
    # Processing Metadata
    processing_started_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    has_new_messages: bool = False
    is_returning_customer: bool = False

class ReasoningCycle(BaseModel):
    """Single thought/action/observation cycle"""
    cycle: int
    thought: str
    action: str
    action_params: Dict[str, Any]
    observation: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class QueuedMessage(BaseModel):
    """Message that arrived during processing"""
    message_id: str
    content: str
    timestamp: str
    message_type: str = "incoming"

class ActiveTaskContext(BaseModel):
    """Ephemeral state stored in Redis during active conversations"""
    
    # Current Task Tracking (for multi-step flows)
    active_task_type: Optional[TaskType] = None
    active_task_status: Optional[TaskStatus] = None
    active_task_data: Dict[str, Any] = Field(default_factory=dict)  # e.g., collected fields for booking
    
    # Message Queue Management (for concurrency)
    queued_messages: List[QueuedMessage] = Field(default_factory=list)
    
    # Session Management
    session_started_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    session_expires_at: Optional[str] = None
    session_locked_by: Optional[str] = None  # For concurrency control

class FullContext(BaseModel):
    """Complete context combining all components"""
    persistent: PersistentContext = Field(default_factory=PersistentContext)
    runtime: RuntimeContext
    active: ActiveTaskContext = Field(default_factory=ActiveTaskContext)