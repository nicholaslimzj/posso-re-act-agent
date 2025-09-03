# Context Update Tool Documentation

## Overview
A unified tool that allows the ReAct agent to update persistent context for parent and child information based on user corrections or new information.

## The Unified Tool: `update_contact_info`

### Parameters
- `update_type: str` - Type of update: "parent" | "child" | "new_child"
- `fields: dict` - Dictionary of fields to update
- `reason: str` (optional) - Reason for update

### Update Types

## 1. Parent Updates (`update_type: "parent"`)

Updates parent's preferred contact information. These are separate from WhatsApp profile data.

**Available Fields:**
- `parent_preferred_name`: Parent's preferred name for communication
- `parent_preferred_email`: Email for official communications  
- `parent_preferred_phone`: Phone number for callbacks/official use

**Behavior:**
- Updates only specified fields
- Other fields remain unchanged
- Does NOT automatically use WhatsApp name/phone as preferred

**Examples:**
```python
# User: "Please call me Sarah, not Sara"
update_contact_info(
    update_type="parent",
    fields={"parent_preferred_name": "Sarah"}
)

# User: "My email is sarah@example.com and phone is +65-9123-4567"
update_contact_info(
    update_type="parent",
    fields={
        "parent_preferred_email": "sarah@example.com",
        "parent_preferred_phone": "+65-9123-4567"
    }
)
```

## 2. Child Updates (`update_type: "child"`)

Updates the currently tracked child's information. Assumes we're updating the SAME child.

**Available Fields:**
- `child_name`: Child's full name
- `child_dob`: Date of birth (YYYY-MM-DD format)
- `child_age`: Age in years (auto-calculated from DOB if provided)
- `preferred_enrollment_date`: When parent wants to enroll (YYYY-MM-DD)

**Behavior:**
- Updates specified fields only
- Other fields remain unchanged
- Maintains existing `pipedrive_deal_id`
- Auto-calculates age from DOB when provided

**Examples:**
```python
# User: "Actually her birthday is March 16, not March 15"
update_contact_info(
    update_type="child",
    fields={"child_dob": "2018-03-16"}
)

# User: "Her name is Emma Smith and we'd prefer September enrollment"
update_contact_info(
    update_type="child",
    fields={
        "child_name": "Emma Smith",
        "preferred_enrollment_date": "2024-09-01"
    }
)
```

## 3. New Child Tracking (`update_type: "new_child"`)

Switches to tracking a DIFFERENT child. This is a reset operation with significant consequences.

**⚠️ CRITICAL BEHAVIOR:**
- **RESETS pipedrive_deal_id to null** (new child = new deal)
- Clears ALL child fields not explicitly provided
- Previous child's data is completely replaced
- Should prompt agent to confirm the switch

**Available Fields:** 
Same as child updates, but with reset behavior

**Examples:**
```python
# User: "Actually, I want to enroll my son James instead of Emma"
update_contact_info(
    update_type="new_child",
    fields={
        "child_name": "James",
        # All other fields (DOB, age, enrollment date) reset to null
        # pipedrive_deal_id is RESET to null
    }
)

# User: "Let me ask about my younger daughter Sophie, she's 3"
update_contact_info(
    update_type="new_child",
    fields={
        "child_name": "Sophie",
        "child_age": 3
        # Previous child's data completely replaced
    }
)
```

## Important Decision Points

### When to use each update_type:

**Use `"parent"`** when:
- Parent provides their contact preferences
- Correcting parent's name/email/phone
- Parent explicitly states preferences

**Use `"child"`** when:
- Correcting a typo in the child's name
- Updating DOB or enrollment date
- Adding missing information
- The parent is still talking about the SAME child

**Use `"new_child"`** when:
- Parent mentions a different child by name
- Parent says "instead of [previous child]"
- Parent wants to inquire about another child
- Clear indication of switching children

## Response Format

The tool returns a structured response:

```json
{
    "status": "updated",
    "update_type": "child",
    "updated_fields": {
        "child_name": {
            "old": "Emily",
            "new": "Emma"
        }
    },
    "reason": "user_correction",
    "updated_at": "2024-09-02T15:30:00"
}
```

For `new_child` updates, additional fields are included:
```json
{
    "status": "updated",
    "update_type": "new_child",
    "previous_child": {
        "name": "Emma",
        "dob": "2018-03-15",
        "age": 6,
        "pipedrive_deal_id": 123
    },
    "deal_reset": true,
    "warning": "Pipedrive deal has been reset for new child"
}
```

## Context Persistence

- All updates modify `PersistentContext`
- Changes are synced to Chatwoot's `additional_attributes`
- Updates persist across sessions
- Redis cache is updated (30-day TTL)

## Error Handling

The tool validates:
- `update_type` must be one of: "parent", "child", "new_child"
- Date formats (YYYY-MM-DD)
- Field names must be valid for the update type
- Returns clear error messages for invalid inputs

## Integration with Agent

The agent's system prompt guides it to:
1. Identify what type of update is needed
2. Extract the relevant fields from user input
3. Choose the correct `update_type`
4. Confirm with user for `new_child` updates
5. Acknowledge successful updates

## Best Practices

1. **Always confirm `new_child`** - This resets the Pipedrive deal
2. **Validate dates** - Ensure DOB is reasonable for a child
3. **Don't assume** - Don't use WhatsApp profile as preferred unless explicitly stated
4. **Log changes** - All updates are logged for audit trail
5. **Handle errors gracefully** - Provide helpful error messages