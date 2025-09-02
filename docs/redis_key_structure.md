# Redis Key Structure

## Overview
All Redis keys follow a consistent pattern using Chatwoot's `inbox_id` and `contact_id` for perfect symmetry with the Chatwoot webhook callbacks.

## Key Format
```
{inbox_id}_{contact_id}:{suffix}
```

## Key Types

### 1. Active Context (1-hour TTL)
**Key**: `{inbox_id}_{contact_id}:active_context`
**Purpose**: Current ReAct session state, reasoning history, task progress
**TTL**: 3600 seconds (1 hour)
**Example**: `74274_12345:active_context`

### 2. Persistent Context (30-day TTL)
**Key**: `{inbox_id}_{contact_id}:persistent_context`  
**Purpose**: Long-term customer data (tour bookings, child info, parent details)
**TTL**: 2,592,000 seconds (30 days)
**Example**: `74274_12345:persistent_context`

### 3. Session Lock (5-minute TTL)
**Key**: `{inbox_id}_{contact_id}:session_lock`
**Purpose**: Prevents concurrent ReAct processing for same contact
**TTL**: 300 seconds (5 minutes)
**Example**: `74274_12345:session_lock`

### 4. New Messages Flag (5-minute TTL)
**Key**: `{inbox_id}_{contact_id}:new_messages`
**Purpose**: Signals that messages arrived during ReAct processing
**TTL**: 300 seconds (5 minutes)
**Example**: `74274_12345:new_messages`

## Data Flow

### Session Start
1. Check `{inbox_id}_{contact_id}:persistent_context` in Redis
2. If not found → Load from Chatwoot additional_params as exact JSON → Cache in Redis (30-day TTL)
3. If found → Use cached data (much faster)
4. Create new `{inbox_id}_{contact_id}:active_context` with 1-hour TTL

### During ReAct Processing
1. Acquire `{inbox_id}_{contact_id}:session_lock` with unique lock_id
2. Update `{inbox_id}_{contact_id}:active_context` after each reasoning cycle
3. Queue incoming messages using `{inbox_id}_{contact_id}:new_messages` flag

### Session End
1. Update persistent context in Redis using model_dump(exclude_none=True)
2. Prepare Chatwoot sync as exact JSON backup (same format as loaded)
3. Delete active context and session lock
4. Persistent context remains cached for 30 days

### Chatwoot Exact Backup Strategy
- **Load**: `PersistentContext(**chatwoot_additional_params)` - direct JSON parsing
- **Save**: `context.persistent.model_dump(exclude_none=True)` - direct JSON stringification  
- **No field mapping** - Chatwoot stores exact Pydantic model format

## Benefits

✅ **Chatwoot Alignment**: Keys match exactly what we receive in webhook callbacks  
✅ **Fast Lookups**: `74274_12345:*` pattern finds all data for a contact  
✅ **Performance**: 30-day persistent context cache reduces Chatwoot API calls  
✅ **Concurrency**: Atomic Redis locks prevent race conditions  
✅ **Cleanup**: TTL ensures automatic memory management  

## Example Usage

```python
# From Chatwoot webhook
inbox_id = 74274
contact_id = "12345"

# Redis operations
redis_manager.get_persistent_context(inbox_id, contact_id)
redis_manager.acquire_session_lock(inbox_id, contact_id, "agent_001")
redis_manager.save_active_context(inbox_id, contact_id, context)
```