"""
Chatwoot webhook request/response models
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class ChatwootSender(BaseModel):
    """Sender information from Chatwoot"""
    id: int
    name: str
    phone_number: Optional[str] = None
    email: Optional[str] = None
    additional_attributes: Dict[str, Any] = Field(default_factory=dict)
    custom_attributes: Dict[str, Any] = Field(default_factory=dict)
    type: str = "contact"  # "contact" or "user"


class ChatwootMessage(BaseModel):
    """Individual message from Chatwoot"""
    id: int
    content: str
    message_type: int  # 0=incoming, 1=outgoing, 2=system
    content_type: str = "text"
    created_at: int
    sender: Optional[ChatwootSender] = None
    sender_id: Optional[int] = None
    sender_type: Optional[str] = None


class ChatwootContactInbox(BaseModel):
    """Contact inbox information"""
    id: int
    contact_id: int
    inbox_id: int
    source_id: str  # WhatsApp phone number


class ChatwootWebhook(BaseModel):
    """Incoming webhook from Chatwoot"""
    event: str  # e.g., "automation_event.message_created"
    id: int  # conversation_id
    inbox_id: int
    messages: List[ChatwootMessage]
    contact_inbox: ChatwootContactInbox
    meta: Dict[str, Any] = Field(default_factory=dict)
    additional_attributes: Dict[str, Any] = Field(default_factory=dict)
    custom_attributes: Dict[str, Any] = Field(default_factory=dict)
    
    def get_latest_message(self) -> Optional[ChatwootMessage]:
        """Get the most recent incoming message"""
        incoming_messages = [m for m in self.messages if m.message_type == 0]
        return incoming_messages[-1] if incoming_messages else None
    
    def get_contact_info(self) -> Dict[str, Any]:
        """Extract contact information"""
        if self.meta and "sender" in self.meta:
            sender = self.meta["sender"]
            return {
                "id": sender.get("id"),
                "name": sender.get("name"),
                "phone": sender.get("phone_number"),
                "email": sender.get("email"),
                "additional_attributes": sender.get("additional_attributes", {})
            }
        return {}


class ChatwootResponse(BaseModel):
    """Response to send back to Chatwoot"""
    success: bool
    message: str
    additional_attributes: Optional[Dict[str, Any]] = None
    custom_attributes: Optional[Dict[str, Any]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Our school hours are 8:00 AM to 3:00 PM",
                "additional_attributes": {
                    "parent_preferred_name": "Sarah",
                    "child_name": "Emma"
                }
            }
        }


class ChatwootMessagesResponse(BaseModel):
    """Response from get messages API"""
    meta: Dict[str, Any]
    payload: List[ChatwootMessage]
    
    def format_conversation_history(self, limit: int = 10) -> str:
        """Format messages as conversation history"""
        # Take last N messages
        recent_messages = self.payload[-limit:] if len(self.payload) > limit else self.payload
        
        formatted_lines = []
        for msg in recent_messages:
            # Skip system messages
            if msg.message_type == 2:
                continue
                
            # Format based on message type
            if msg.message_type == 0:  # Incoming
                sender_name = "Contact"
                if msg.sender and hasattr(msg.sender, 'name'):
                    sender_name = msg.sender.name
                formatted_lines.append(f"[{sender_name}]: {msg.content}")
            elif msg.message_type == 1:  # Outgoing
                formatted_lines.append(f"[Agent]: {msg.content}")
        
        return "\n".join(formatted_lines)