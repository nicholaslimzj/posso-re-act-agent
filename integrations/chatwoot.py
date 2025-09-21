"""
Chatwoot API integration for fetching conversation messages
"""

from typing import List, Dict, Any, Optional
import httpx
from loguru import logger
from config import settings


async def get_conversation_messages(
    account_id: int,
    conversation_id: int,
    api_key: str
) -> List[Dict[str, Any]]:
    """
    Fetch all messages from a Chatwoot conversation.
    
    Args:
        account_id: Chatwoot account ID
        conversation_id: Conversation ID
        api_key: Chatwoot API access token
        
    Returns:
        List of message dictionaries
    """
    try:
        # Build API URL
        base_url = settings.CHATWOOT_API_URL  # e.g., https://app.chatwoot.com
        url = f"{base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages"
        
        headers = {
            "api_access_token": api_key,
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch messages: {response.status_code} - {response.text}")
                return []
            
            data = response.json()
            messages = data.get("payload", [])
            
            logger.info(f"Fetched {len(messages)} messages from conversation {conversation_id}")
            
            # Return messages in chronological order (oldest first)
            return messages
            
    except Exception as e:
        logger.error(f"Error fetching conversation messages: {e}")
        return []


async def send_message(
    account_id: int,
    conversation_id: int,
    message: str,
    api_key: str,
    private: bool = False
) -> Dict[str, Any]:
    """
    Send a message to a Chatwoot conversation.
    
    Args:
        account_id: Chatwoot account ID
        conversation_id: Conversation ID
        message: Message content to send
        api_key: Chatwoot API access token
        private: If True, sends as private note
        
    Returns:
        Response data from Chatwoot
    """
    try:
        base_url = settings.CHATWOOT_API_URL
        url = f"{base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages"
        
        headers = {
            "api_access_token": api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "content": message,
            "message_type": "outgoing",
            "private": private
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code not in [200, 201]:
                logger.error(f"Failed to send message: {response.status_code} - {response.text}")
                return {"success": False, "error": response.text}
            
            return {"success": True, "data": response.json()}
            
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return {"success": False, "error": str(e)}


async def update_contact_attributes(
    account_id: int,
    contact_id: int,
    attributes: Dict[str, Any],
    api_key: str
) -> Dict[str, Any]:
    """
    Update contact's additional attributes in Chatwoot.
    
    Args:
        account_id: Chatwoot account ID
        contact_id: Contact ID
        attributes: Dictionary of attributes to update
        api_key: Chatwoot API access token
        
    Returns:
        Response data from Chatwoot
    """
    try:
        base_url = settings.CHATWOOT_API_URL
        url = f"{base_url}/api/v1/accounts/{account_id}/contacts/{contact_id}"
        
        headers = {
            "api_access_token": api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "additional_attributes": attributes
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.patch(url, json=payload, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Failed to update contact: {response.status_code} - {response.text}")
                return {"success": False, "error": response.text}
            
            return {"success": True, "data": response.json()}
            
    except Exception as e:
        logger.error(f"Error updating contact: {e}")
        return {"success": False, "error": str(e)}


async def assign_conversation_to_agent(
    account_id: int,
    conversation_id: int,
    agent_id: int,
    api_key: str,
    reason: str = None
) -> Dict[str, Any]:
    """
    Assign a conversation to a specific agent in Chatwoot.

    Args:
        account_id: Chatwoot account ID
        conversation_id: Conversation ID
        agent_id: Agent ID to assign to
        api_key: Chatwoot API access token
        reason: Optional reason for assignment

    Returns:
        Response data from Chatwoot
    """
    try:
        base_url = settings.CHATWOOT_API_URL
        url = f"{base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/assignments"

        headers = {
            "api_access_token": api_key,
            "Content-Type": "application/json"
        }

        payload = {
            "assignee_id": agent_id
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)

            if response.status_code not in [200, 201]:
                logger.error(f"Failed to assign conversation {conversation_id} to agent {agent_id}: {response.status_code} - {response.text}")
                return {"success": False, "error": response.text}

            logger.info(f"Successfully assigned conversation {conversation_id} to agent {agent_id}")

            # Add assignment note if reason is provided
            if reason:
                note_content = f"🤖 Conversation assigned to human agent (ID: {agent_id})\nReason: {reason}"
                note_result = await send_message(
                    account_id=account_id,
                    conversation_id=conversation_id,
                    message=note_content,
                    api_key=api_key,
                    private=True
                )
                if not note_result.get("success"):
                    logger.warning(f"Failed to add assignment note: {note_result.get('error')}")

            return {"success": True, "data": response.json()}

    except Exception as e:
        logger.error(f"Error assigning conversation to agent: {e}")
        return {"success": False, "error": str(e)}