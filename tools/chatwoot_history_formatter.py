"""
Chatwoot conversation history formatter
"""
from typing import List, Dict, Any, Optional
from loguru import logger


def format_chatwoot_messages(messages: List[Dict[str, Any]], limit: int = 10) -> str:
    """
    Format Chatwoot messages into readable conversation history
    
    Args:
        messages: List of message dictionaries from Chatwoot
        limit: Maximum number of messages to include
        
    Returns:
        Formatted conversation string
    """
    try:
        # Take only the most recent messages
        recent_messages = messages[-limit:] if len(messages) > limit else messages
        
        formatted_lines = []
        
        for msg in recent_messages:
            # Skip system messages (type 2)
            if msg.get("message_type") == 2:
                continue
            
            content = msg.get("content", "").strip()
            if not content:
                continue
                
            # Determine sender
            if msg.get("message_type") == 0:  # Incoming from contact
                sender_info = msg.get("sender", {})
                sender_name = sender_info.get("name", "Contact")
                formatted_lines.append(f"[{sender_name}]: {content}")
                
            elif msg.get("message_type") == 1:  # Outgoing from agent
                sender_info = msg.get("sender", {})
                if isinstance(sender_info, dict):
                    sender_name = sender_info.get("name", "Agent")
                else:
                    sender_name = "Agent"
                formatted_lines.append(f"[{sender_name}]: {content}")
        
        return "\n".join(formatted_lines) if formatted_lines else ""
        
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