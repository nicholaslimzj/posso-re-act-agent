# Context Update Tools Documentation

## Overview
Tools that allow the ReAct agent to update persistent context based on user corrections or new information.

## Parent Updates

### `updateParentDetails`
Updates parent's preferred contact information. These are separate from WhatsApp profile data.

**Fields:**
- `parent_preferred_name`: Parent's preferred name for communication
- `parent_preferred_email`: Email for official communications  
- `parent_preferred_phone`: Phone number for callbacks/official use

**Behavior:**
- Can update 1 or more fields in a single call
- Unspecified fields remain unchanged
- Empty/null values are allowed (to clear a field)
- Does NOT automatically use WhatsApp name/phone as preferred

**Examples:**
```python
# User: "Please call me Sarah, not Sara"
updateParentDetails(parent_preferred_name="Sarah")

# User: "My email is sarah@example.com and phone is +65-9123-4567"
updateParentDetails(
    parent_preferred_email="sarah@example.com",
    parent_preferred_phone="+65-9123-4567"
)
```

## Child Updates

### `updateChildDetails`
Updates the currently tracked child's information. Assumes we're updating the SAME child.

**Fields:**
- `child_name`: Child's full name
- `child_dob`: Date of birth (YYYY-MM-DD format)
- `child_age`: Age in years (auto-calculated from DOB if provided)
- `preferred_enrollment_date`: When parent wants to enroll (YYYY-MM-DD)

**Behavior:**
- Updates specified fields only
- Other fields remain unchanged
- Maintains existing `pipedrive_deal_id`

**Examples:**
```python
# User: "Actually her birthday is March 16, not March 15"
updateChildDetails(child_dob="2018-03-16")

# User: "We'd prefer to start in September instead"
updateChildDetails(preferred_enrollment_date="2024-09-01")
```

### `trackNewChild` ⚠️ CRITICAL
Switches to tracking a DIFFERENT child. This is a reset operation.

**Behavior:**
- **RESETS pipedrive_deal_id to null** (new child = new deal)
- Clears ALL child fields not explicitly provided
- Use when parent switches from one child to another
- Should prompt agent to confirm the switch

**Fields:** Same as `updateChildDetails` but with reset behavior

**Examples:**
```python
# User: "Actually, I want to enroll my son James instead of Emma"
trackNewChild(
    child_name="James",
    # All other fields (DOB, age, enrollment date) reset to null
    # pipedrive_deal_id is RESET to null
)

# User: "Let me ask about my younger daughter Sophie, she's 3"
trackNewChild(
    child_name="Sophie", 
    child_age=3
    # Previous child's data completely replaced
)
```

## Important Notes

### When to use `trackNewChild` vs `updateChildDetails`

Use `updateChildDetails` when:
- Correcting a typo in the name
- Updating DOB or enrollment date
- Adding missing information
- The parent is still talking about the SAME child

Use `trackNewChild` when:
- Parent mentions a different child
- Parent says "instead of [previous child]"
- Parent wants to inquire about another child
- Clear indication of switching children

### Pipedrive Deal ID Management
- `trackNewChild` ALWAYS resets `pipedrive_deal_id` to null
- This triggers creation of a new deal for the new child
- Previous deal remains in Pipedrive for the previous child
- Critical for accurate sales tracking

### Context Persistence
- All updates modify `PersistentContext`
- Changes are synced to Chatwoot's `additional_attributes`
- Updates persist across sessions
- Redis cache is updated (30-day TTL)

## Implementation Considerations

1. **Validation**:
   - DOB should be reasonable (not future, child age-appropriate)
   - Phone numbers should be validated format
   - Email should be valid format

2. **Confirmation**:
   - Tool should return what was changed
   - Agent should confirm major changes with user
   - Especially important for `trackNewChild`

3. **Audit Trail**:
   - Log all context updates
   - Include reason for update if provided
   - Track which tool was used

## Error Handling

- Invalid date formats → Return error, ask for correct format
- Missing required fields for `trackNewChild` → Warn about reset behavior
- Concurrent updates → Use Redis locking to prevent conflicts