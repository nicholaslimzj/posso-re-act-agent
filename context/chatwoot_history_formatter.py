"""
Chatwoot conversation history formatter
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import pytz
from loguru import logger


def format_chatwoot_messages(messages: List[Dict[str, Any]], limit: int = 14, exclude_last: bool = True) -> str:
    """
    Format Chatwoot messages into readable conversation history.
    
    Args:
        messages: List of message dictionaries from Chatwoot
        limit: Maximum number of messages to include (default 14)
        exclude_last: If True, excludes the last user message (since it becomes HumanMessage)
        
    Returns:
        Formatted conversation string
    """
    try:
        if not messages:
            return ""
        
        # Singapore timezone
        singapore_tz = pytz.timezone('Asia/Singapore')
        
        # Take only the most recent messages
        recent_messages = messages[-limit:] if len(messages) > limit else messages
        
        # If exclude_last is True and the last message is from the user, remove it
        if exclude_last and recent_messages:
            last_msg = recent_messages[-1]
            if last_msg.get("message_type") == 0:  # Incoming from contact
                recent_messages = recent_messages[:-1]  # Remove the last message
        
        formatted_lines = []
        prev_timestamp = None
        
        for msg in recent_messages:
            # Skip system messages (type 2)
            if msg.get("message_type") == 2:
                continue
            
            content = msg.get("content", "").strip()
            if not content:
                continue
            
            # Parse timestamp
            timestamp = None
            if msg.get("created_at"):
                try:
                    # Chatwoot sends timestamps as Unix timestamps (seconds)
                    timestamp = datetime.fromtimestamp(msg["created_at"], tz=pytz.UTC)
                    timestamp = timestamp.astimezone(singapore_tz)
                except (ValueError, TypeError):
                    logger.warning(f"Failed to parse timestamp: {msg.get('created_at')}")
            
            # Add date separator if there's a long gap (>1 week)
            if timestamp and prev_timestamp:
                time_gap = timestamp - prev_timestamp
                if time_gap > timedelta(weeks=1):
                    # Add a separator with the date
                    separator_date = timestamp.strftime("%A, %B %d, %Y")
                    formatted_lines.append(f"\n--- {separator_date} ---")
            
            # Format time string
            time_str = ""
            if timestamp:
                time_str = timestamp.strftime("%H:%M")
                prev_timestamp = timestamp
            
            # Determine sender and format message
            if msg.get("message_type") == 0:  # Incoming from contact
                if time_str:
                    formatted_lines.append(f"User [{time_str}]: {content}")
                else:
                    formatted_lines.append(f"User: {content}")
                
            elif msg.get("message_type") == 1:  # Outgoing from agent
                if time_str:
                    formatted_lines.append(f"Assistant [{time_str}]: {content}")
                else:
                    formatted_lines.append(f"Assistant: {content}")
        
        # Join with newlines for readability
        if formatted_lines:
            # Add a header if we have messages
            history = "Recent conversation history:\n"
            history += "\n".join(formatted_lines)
            return history
        
        return ""
        
    except Exception as e:
        logger.error(f"Error formatting Chatwoot messages: {e}")
        return ""


def extract_persistent_context(additional_attributes: Dict[str, Any], inbox_id: int) -> Dict[str, Any]:
    """
    Extract persistent context from Chatwoot additional_attributes
    
    Args:
        additional_attributes: Dict from Chatwoot containing persisted data
        inbox_id: The inbox ID to construct the profile key
        
    Returns:
        Dict with persistent context fields
    """
    import json
    
    # The profile is stored as a JSON string under the key "{inbox_id}_profile"
    profile_key = f"{inbox_id}_profile"
    
    if profile_key not in additional_attributes:
        return {}
    
    try:
        # Parse the JSON string
        profile_json = additional_attributes[profile_key]
        if isinstance(profile_json, str):
            return json.loads(profile_json)
        return profile_json if isinstance(profile_json, dict) else {}
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error extracting persistent context: {e}")
        return {}


def prepare_chatwoot_update(persistent_context_dict: Dict[str, Any], inbox_id: int) -> Dict[str, Any]:
    """
    Prepare persistent context for updating Chatwoot additional_attributes
    
    Args:
        persistent_context_dict: Dict from PersistentContext.model_dump()
        inbox_id: The inbox ID to construct the profile key
        
    Returns:
        Dict ready for Chatwoot additional_attributes update with JSON string value
    """
    import json
    
    # Remove None values
    cleaned_data = {k: v for k, v in persistent_context_dict.items() if v is not None}
    
    # Store as JSON string under the inbox-specific key
    profile_key = f"{inbox_id}_profile"
    
    return {
        profile_key: json.dumps(cleaned_data)
    }