# ReAct School Chatbot Implementation Guide

## Project Overview
Building a conversational school chatbot using ReAct pattern that can:
- Book tours with natural conversation flow
- Reschedule appointments 
- Handle parent callback requests
- Answer FAQs about school/tours
- Handle mid-conversation topic switching gracefully

## Architecture Stack

### Core Components
- **LangGraph**: ReAct agent scaffolding and workflow orchestration
- **LiteLLM**: Unified interface for GPT-4o-mini (~15c/mTok)
- **Redis**: Fast persistent memory for active ReAct state
- **Chatwoot**: Chat interface, conversation history, contact persistence
- **LangSmith**: Graph-level debugging and tracing

### Data Flow
```
User Message → Chatwoot → ReAct Agent (Redis Memory) → Tools → Response → Chatwoot
                                ↓
                         LangSmith (Tracing)
```

## Tool Signatures

### Booking & Scheduling Tools

```python
def check_availability(
    date_range_start: str = None,  # "2025-09-15" (ISO format)
    date_range_end: str = None,    # "2025-09-22" (ISO format) 
    preferred_times: List[str] = None  # ["morning", "afternoon"] or ["10:00", "14:00"]
) -> dict:
    """
    Check available tour slots within date range and time preferences.
    Returns: {"available_slots": [{"date": "2025-09-15", "time": "10:00", "duration": "1h"}]}
    """

def book_tour(
    parent_name: str = None,
    parent_phone: str = None,
    parent_email: str = None,
    child_name: str = None,
    child_age: int = None,
    preferred_date: str = None,      # "2025-09-15"
    preferred_time: str = None,      # "10:00"
    special_requirements: str = None
) -> dict:
    """
    Book a tour - handles CRM complexity internally (create parent, deal, activity).
    Returns: {"status": "missing_fields", "missing": ["parent_phone", "child_age"]}
    Or: {"status": "success", "booking_id": "12345", "confirmation_details": {...}}
    """

def manage_tour_booking(
    booking_id: str,               # Required - from previous booking
    action: str,                   # "reschedule" | "cancel"
    new_date: str = None,         # Required for reschedule
    new_time: str = None,         # Required for reschedule
    cancellation_reason: str = None  # Optional for cancel
) -> dict:
    """
    Reschedule or cancel existing tour booking.
    Returns: {"status": "success", "message": "Tour rescheduled to..."} 
    Or: {"status": "error", "message": "Booking not found"}
    """
```

### Communication Tools

```python
def request_callback(
    parent_name: str,
    parent_phone: str,
    best_time_to_call: str,  # "morning", "afternoon", "evening", or specific time
    topic: str = None        # What they want to discuss
) -> dict:
    """
    Schedule a callback request for parent.
    Returns: {"status": "success", "callback_id": "67890"}
    """

def get_faq_answer(
    question: str
) -> dict:
    """
    Retrieve FAQ answer for school/tour related questions.
    Returns: {"answer": "...", "related_topics": [...]} or {"status": "no_match"}
    """
```

### Context Management Tools

```python
def update_context(
    field_to_update: str,    # "parent_name", "child_age", "preferred_date", etc.
    new_value: str,          # New value for the field
    reason: str = None       # "user_correction", "new_information"
) -> dict:
    """
    Update context when user provides corrections or new information.
    Returns: {"status": "updated", "field": "parent_name", "old_value": "John", "new_value": "Jon"}
    """

def check_unread_messages() -> dict:
    """
    Check for messages that arrived while ReAct was processing.
    Returns: {
        "has_unread": bool,
        "messages": [{"message": "text", "timestamp": "..."}]
    }
    """
```

## Tool Design Comments

### High-Level vs Low-Level Approach
- **book_tour()** handles CRM complexity internally (create parent → deal → activity)
- Agent focuses on conversation flow, not CRM plumbing
- Tool validates requirements and guides agent on missing fields

### Natural Conversation Support  
- **check_unread_messages()** enables mid-task topic switching
- **update_context()** handles corrections gracefully
- **get_faq_answer()** supports knowledge requests during booking flow

### Error Handling
- Tools return structured responses with clear status/error messages
- Missing fields are explicitly communicated back to agent
- Agent can reason about next steps based on tool responses

## Memory Management Strategy

### Context Data Structure

**Persistent Context (Chatwoot additional_params):**
```python
# Long-term state - survives across sessions, stored in Chatwoot
{
    # Customer Preferred Identity (stored preferences)
    "parent_preferred_name": "John",           # How they want to be addressed
    "parent_preferred_phone": "+65-9123-4567", # Their preferred contact number
    "parent_preferred_email": "john@email.com", # Their email for confirmations
    
    # Child Information
    "child_name": "Sarah",                     # Child's name
    "child_dob": "2017-03-15",                # Child's date of birth (YYYY-MM-DD)
    "child_enrollment_date_preferred": "2025-01-15", # Preferred enrollment start date
    
    # Pipedrive Integration
    "pipedrive_person_id": 456,               # Pipedrive person record ID
    "pipedrive_deal_id": 789,                 # Pipedrive deal record ID
    
    # Tour Booking Information
    "tour_activity_id": 123,                  # Pipedrive activity ID for tour
    "tour_scheduled_date": "2025-09-15",      # Tour date (YYYY-MM-DD)
    "tour_scheduled_time": "10:00",           # Tour time in SGT (HH:MM)
    "tour_booked_at": "2025-09-02T10:30:00Z", # When the tour was booked (UTC)
    "tour_status": "scheduled",               # Tour status: scheduled/completed/cancelled
    
    # Callback Request Information
    "callback_requested": True,               # Whether callback was requested
    "callback_preference": "morning",         # Callback time preference: morning/afternoon/anytime
    "callback_date": "2025-09-03",           # Requested callback date (YYYY-MM-DD)
    "callback_requested_at": "2025-09-02T11:00:00Z", # When callback was requested (UTC)
    "callback_activity_id": 234              # Pipedrive activity ID for callback
}
```

**Runtime Context (Retrieved at startup, not persisted):**
```python
# Retrieved fresh each session - from Chatwoot API and config
{
    # Session Identifiers
    "conversation_id": "chatwoot_conv_123",   # Chatwoot conversation ID
    "inbox_id": 5,                           # Chatwoot inbox ID (determines school)
    "school_id": "tampines",                 # School identifier
    
    # WhatsApp Identity (from WhatsApp profile)
    "whatsapp_name": "John Smith",           # Name from WhatsApp profile
    "whatsapp_phone": "+65-9123-4567",      # Phone from WhatsApp profile
    
    # Conversation History
    "messages": [                            # Recent conversation messages
        {"content": "Hi, I'd like to book a tour", "timestamp": "..."},
        {"content": "Sure! Let me help you with that", "timestamp": "..."}
    ],
    
    # School Configuration (loaded at runtime)
    "school_config": {                       # School-specific configuration
        "available_times": ["09:00", "11:00", "14:00", "16:00"],
        "tour_duration_minutes": 60,
        "max_advance_booking_days": 30,
        "contact_email": "tampines@school.edu.sg"
    },
    
    # Processing Metadata
    "processing_started_at": "2025-09-02T10:29:00Z",
    "has_new_messages": False,
    "is_returning_customer": True
}
```

**Active Task Context (Redis ephemeral state):**
```python
# Key structure: f"react_context:{school_id}_{contact_id}"
# Only exists during active ReAct execution - deleted after session ends
{
  # Active Task State
  "active_task_type": "tour_booking",           # tour_booking/callback_request/reschedule/faq
  "active_task_status": "collecting_info",     # collecting_info/processing/completed
  "active_task_step": "gathering_child_details", # Current step in multi-step tasks
  "active_task_data": {                        # Task-specific working data
    "collected_parent_name": "John",
    "missing_fields": ["child_age", "preferred_date"],
    "available_slots_shown": [
      {"date": "2025-09-15", "time": "10:00"},
      {"date": "2025-09-16", "time": "14:00"}
    ],
    "validation_attempts": 1
  },
  
  # ReAct Execution State
  "reasoning_history": [                       # Recent thought/action/observation cycles
    {
      "cycle": 1,
      "thought": "User wants to book a tour, need to check availability first",
      "action": "check_availability",
      "action_params": {"date_range_start": "2025-09-15", "date_range_end": "2025-09-22"},
      "observation": "Found 3 available slots: Sept 15 10am, Sept 16 2pm, Sept 18 10am",
      "timestamp": "2025-09-02T10:30:00Z"
    },
    {
      "cycle": 2, 
      "thought": "User selected Sept 15 10am, I have all info needed to book",
      "action": "book_tour",
      "action_params": {"parent_name": "John", "child_name": "Sarah", "preferred_date": "2025-09-15"},
      "observation": "Booking successful, tour_activity_id: 123",
      "timestamp": "2025-09-02T10:32:00Z"
    }
  ],
  
  # Message Queue Management
  "queued_messages": [                         # Messages that arrived during processing
    {
      "message_id": "msg_456",
      "content": "What's your STEM program like?", 
      "timestamp": "2025-09-02T10:31:00Z",
      "message_type": "incoming"
    },
    {
      "message_id": "msg_457",
      "content": "Do you provide lunch?", 
      "timestamp": "2025-09-02T10:31:30Z",
      "message_type": "incoming"
    }
  ],
  "last_message_processed_id": "msg_455",
  
  # Session Lifecycle
  "session_started_at": "2025-09-02T10:29:00Z",
  "session_expires_at": "2025-09-02T11:29:00Z",   # 1 hour TTL
  "session_locked_by": "react_agent_instance_1"   # Prevents concurrent access
}
```

### Data Flow Strategy

**Session Start:**
1. Check Redis for active context
2. If not found, load persistent context from Chatwoot
3. Initialize new active task state in Redis

**During ReAct Execution:**
- All working state stored in Redis (fast access)
- Update reasoning_history after each cycle
- Queue incoming messages in Redis

**Session End:**
1. Update important fields in persistent context
2. Sync persistent context back to Chatwoot
3. Delete Redis active context (cleanup)

### Data Flow Strategy

**Session Start:**
1. Check Redis for active context using `f"react_context:{school_id}_{contact_id}"`
2. If not found, load persistent context from Chatwoot additional_params
3. Load runtime context (messages, WhatsApp profile, school config) 
4. Initialize new active task state in Redis with session lock

**During ReAct Execution:**
- All working state stored in Redis (sub-millisecond access)
- Update reasoning_history after each thought/action/observation cycle
- Queue incoming messages in Redis queued_messages array
- Update active_task_data as information is collected
- Maintain session lock to prevent concurrent processing

**Session End:**
1. Process any queued_messages with final ReAct cycle
2. Update important persistent fields (tour bookings, callbacks, etc.)
3. Sync updated persistent context back to Chatwoot additional_params
4. Release session lock and delete Redis active context (cleanup)
5. Log final reasoning_history to LangSmith for debugging

**Single-Threaded Execution Model:**
- One active ReAct session per school_id + contact_id combination
- Other requests check for existing session lock
- If locked: add message to queued_messages and return early
- If unlocked: start new ReAct session
- Agent processes queued messages at end of each cycle

**Concurrency Handling:**
```python
# Check for existing session
redis_key = f"react_context:{school_id}_{contact_id}"
new_messages_key = f"new_messages:{school_id}_{contact_id}"

if redis.exists(redis_key):
    # Session active - queue message and set flag
    redis.lpush(f"{redis_key}:queue", new_message)
    redis.set(new_messages_key, "1")  # Simple flag
    return "Message queued, processing in progress..."
else:
    # Start new ReAct session
    start_react_session(redis_key, context_data)

# At end of ReAct cycle - check for new messages
def check_for_new_messages():
    if redis.exists(new_messages_key):
        queued = redis.lrange(f"{redis_key}:queue", 0, -1)
        redis.delete(new_messages_key)  # Clear flag
        redis.delete(f"{redis_key}:queue")  # Clear queue
        return queued
    return []
```