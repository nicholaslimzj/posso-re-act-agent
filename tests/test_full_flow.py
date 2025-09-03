#!/usr/bin/env python3
"""
Integration test for full Chatwoot webhook flow
"""

import json
from loguru import logger
from models.webhook_models import ChatwootWebhook
from message_handler import message_handler
from context.chatwoot_history_formatter import extract_persistent_context, prepare_chatwoot_update


def test_webhook_processing():
    """Test processing a Chatwoot webhook payload"""
    
    # Load sample webhook
    with open("samples/chatwoot_webhook.json", "r") as f:
        webhook_data = json.load(f)
    
    # Parse webhook
    webhook = ChatwootWebhook(**webhook_data)
    
    # Extract data
    inbox_id = webhook.inbox_id
    contact_id = str(webhook.contact_inbox.contact_id)
    conversation_id = str(webhook.id)
    
    latest_message = webhook.get_latest_message()
    if latest_message:
        logger.info(f"Processing: {latest_message.content}")
        
        # Process message
        result = message_handler.process_chatwoot_message(
            inbox_id=inbox_id,
            contact_id=contact_id,
            conversation_id=conversation_id,
            message_content=latest_message.content,
            message_id=str(latest_message.id),
            whatsapp_profile={"name": "Test User", "phone": "+65-9999-9999"}
        )
        
        logger.info(f"Response: {result.get('response', 'No response')}")
        assert result["success"], f"Processing failed: {result.get('error')}"


def test_persistent_context_format():
    """Test the persistent context JSON format"""
    
    # Sample additional_attributes from Chatwoot
    additional_attributes = {
        "74274_profile": json.dumps({
            "pipedrive_deal_id": 10,
            "parent_preferred_name": "Neeky",
            "parent_preferred_phone": "+6594315011",
            "child_name": "Cassie Lim",
            "tour_scheduled_date": "2025-09-17",
            "tour_scheduled_time": "09:00"
        })
    }
    
    # Extract context
    context = extract_persistent_context(additional_attributes, 74274)
    
    assert context["parent_preferred_name"] == "Neeky"
    assert context["child_name"] == "Cassie Lim"
    logger.info("✅ Context extraction working")
    
    # Prepare update
    updated = prepare_chatwoot_update(context, 74274)
    assert "74274_profile" in updated
    
    # Verify it's a JSON string
    profile_data = json.loads(updated["74274_profile"])
    assert profile_data["parent_preferred_name"] == "Neeky"
    logger.info("✅ Context update format correct")


if __name__ == "__main__":
    logger.info("🧪 Running integration tests")
    
    test_persistent_context_format()
    test_webhook_processing()
    
    logger.info("✅ All integration tests passed")