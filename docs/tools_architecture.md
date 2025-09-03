# Tools Architecture for ReAct School Chatbot

## Overview
The ReAct agent uses a carefully designed set of 5 tools to handle all parent interactions. Each tool has a clear, distinct purpose to avoid confusion and ensure reliable operation.

## Design Principles
1. **Clear Intent**: Each tool name clearly indicates its purpose
2. **No Overlap**: Tools have distinct boundaries with no ambiguous cases
3. **Action-Oriented**: Tool names start with verbs that specify the action
4. **Appropriate Complexity**: Balance between too many tools (confusion) and too few (overloaded)

## The 5 Core Tools

### 1. answer_question
**Purpose**: Search FAQ knowledge base for school information

**Parameters**:
- `question: str` - Open-ended question from parent

**Use Cases**:
- "What are your school fees?"
- "Tell me about your curriculum"
- "What makes Posso different?"
- "Where are you located?"

**Implementation**: 
- Vector similarity search using sentence-transformers
- Fallback to text search if embeddings unavailable
- Returns relevant FAQ sections

---

### 2. check_tour_slots
**Purpose**: Check available tour dates and times

**Parameters**:
- `date: str` - Specific date (YYYY-MM-DD) or relative ("next Monday")
- `time_preference: str` - "morning" | "afternoon" | "any"

**Use Cases**:
- "What tours do you have next week?"
- "Check Monday morning availability"
- "Any slots available tomorrow?"

**Implementation**:
- Queries school's available tour slots
- Filters by date and time preference
- Returns structured availability data

---

### 3. book_or_reschedule_tour
**Purpose**: Take action on tour bookings

**Parameters**:
- `action: str` - "book" | "reschedule" | "cancel"
- `date: str` - Tour date (YYYY-MM-DD)
- `time: str` - Tour time (HH:MM)
- `reason: str` (optional) - For cancellations/rescheduling

**Use Cases**:
- "Book the 9am slot on Monday"
- "Change my tour to next Tuesday"
- "Cancel my tour booking"

**Implementation**:
- Creates/updates tour booking in system
- Updates Pipedrive deal
- Sends confirmation via Chatwoot

---

### 4. update_contact_info
**Purpose**: Update parent or child information

**Parameters**:
- `update_type: str` - "parent" | "child" | "new_child"
- `fields: dict` - Fields to update

**Sub-types**:
- **parent**: Updates preferred contact details
  - `parent_preferred_name`
  - `parent_preferred_email`
  - `parent_preferred_phone`
  
- **child**: Updates current child's info
  - `child_name`
  - `child_dob`
  - `child_age`
  - `preferred_enrollment_date`
  
- **new_child**: Switches to different child (RESETS Pipedrive deal!)
  - All child fields reset
  - Creates new deal

**Use Cases**:
- "My name is Sarah, not Sara"
- "My daughter is Emma, not Emily"
- "Actually, I want to enroll my son James instead"

**Implementation**:
- Updates PersistentContext in Redis
- Syncs to Chatwoot additional_attributes
- Handles Pipedrive deal management for new_child

---

### 5. manage_callback_request
**Purpose**: Handle callback requests and preferences

**Parameters**:
- `action: str` - "request" | "update_preference" | "add_note"
- `details: str` - Preference details or notes

**Actions**:
- **request**: Create new callback request
- **update_preference**: Change callback timing/method
- **add_note**: Add context for staff

**Use Cases**:
- "Please call me back"
- "Actually call me after 3pm"
- "I prefer WhatsApp over phone calls"
- "I have questions about financial aid"

**Implementation**:
- Creates activity in Pipedrive
- Adds notes to conversation
- Sets callback preferences in context

---

## Tool Selection Logic

The agent follows this decision tree:

```
User Message
    ↓
Is it a question seeking information?
    → YES: answer_question
    → NO: Continue ↓
    
Is it about tour availability?
    → YES: check_tour_slots
    → NO: Continue ↓
    
Is it about booking/changing a tour?
    → YES: book_or_reschedule_tour
    → NO: Continue ↓
    
Is it correcting/providing personal info?
    → YES: update_contact_info
    → NO: Continue ↓
    
Is it about callback/contact preferences?
    → YES: manage_callback_request
    → NO: Fallback to conversation
```

## Why 5 Tools?

### Why Not Fewer?
- **3 tools**: Too much overloading, unclear when to use each
- **4 tools**: Forced combining of unrelated functions

### Why Not More?
- **6-7 tools**: Cognitive overload for agent
- **8+ tools**: Tool selection errors increase dramatically
- **12+ tools**: Original plan - too complex!

### The Sweet Spot: 5 Tools
- Each tool has **one clear job**
- **No ambiguity** in selection
- **Natural conversation flow**
- **Maintainable and debuggable**

## Integration with ReAct Agent

The tools are registered with the ReAct agent in two ways:

1. **Base Tools** (always available):
   - answer_question

2. **Context-Aware Tools** (need inbox_id and contact_id):
   - check_tour_slots
   - book_or_reschedule_tour
   - update_contact_info
   - manage_callback_request

## Error Handling

Each tool implements:
- Input validation
- Graceful error messages
- Fallback behaviors
- Logging for debugging

## Future Considerations

### Potential 6th Tool (if needed):
- **verify_enrollment_eligibility** - Check age requirements, document needs

### Not Separate Tools:
- Pipedrive operations (handled internally by other tools)
- Sending confirmations (automatic after booking)
- FAQ updates (admin function, not agent tool)

## Testing Strategy

Each tool should be tested for:
1. **Correct selection** - Agent picks right tool
2. **Parameter extraction** - Correct params from user input
3. **Error handling** - Graceful failures
4. **Context updates** - Proper state management
5. **Integration** - Works with other tools in sequence