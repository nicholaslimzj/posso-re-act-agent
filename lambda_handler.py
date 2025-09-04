"""
AWS Lambda handler for Posso ReAct School Chatbot
Optimized for SnapStart with proper initialization separation
"""

import json
import os
from typing import Dict, Any, Optional
from loguru import logger

# SnapStart Phase: These imports and initializations happen during snapshot
from config import settings
from message_handler import MessageHandler
from models.webhook_models import ChatwootWebhook
from context.chatwoot_history_formatter import extract_persistent_context, prepare_chatwoot_update
from context import PersistentContext
from integrations.chatwoot import get_conversation_messages, send_message

# Pre-initialize components during SnapStart (no connections yet)
logger.info("🚀 SnapStart: Pre-initializing Posso ReAct Agent...")

# Initialize message handler (connections established at runtime)
message_handler_instance = None

def get_message_handler() -> MessageHandler:
    """Get or create message handler (lazy initialization for connections)"""
    global message_handler_instance
    if message_handler_instance is None:
        logger.info("Initializing message handler with connections...")
        message_handler_instance = MessageHandler()
    return message_handler_instance

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for Chatwoot webhooks
    
    Args:
        event: Lambda event containing webhook payload
        context: Lambda context (unused)
        
    Returns:
        API Gateway response dict
    """
    try:
        # Parse the webhook payload
        if 'body' in event:
            # API Gateway format
            body = event['body']
            if isinstance(body, str):
                payload = json.loads(body)
            else:
                payload = body
        else:
            # Direct invocation format
            payload = event

        logger.info(f"Received webhook event: {payload.get('event', 'unknown')}")
        
        # Parse webhook
        try:
            webhook = ChatwootWebhook(**payload)
        except Exception as e:
            logger.error(f"Invalid webhook format: {e}")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid webhook format'})
            }
        
        # Only process message created events
        if webhook.event != "message_created":
            logger.info(f"Ignoring event: {webhook.event}")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Event ignored'})
            }
        
        # Extract message details
        message_data = webhook.data
        message_content = message_data.content.strip()
        
        # Skip if message is empty or from bot
        if not message_content or message_data.message_type != 0:  # 0 = incoming
            logger.info("Skipping empty message or bot message")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Message skipped'})
            }
        
        # Get conversation details
        conversation = message_data.conversation
        inbox_id = conversation.inbox_id
        contact_id = str(conversation.contact_last_seen_at or conversation.id)
        
        # Get conversation history
        messages = get_conversation_messages(
            conversation.id, 
            settings.CHATWOOT_ACCOUNT_ID
        )
        
        # Extract persistent context
        persistent_context_dict = extract_persistent_context(
            conversation.additional_attributes, 
            inbox_id
        )
        persistent_context = PersistentContext(**persistent_context_dict)
        
        # Get message handler and process
        handler = get_message_handler()
        result = handler.process_message(
            message=message_content,
            inbox_id=inbox_id,
            contact_id=contact_id,
            messages=messages,
            persistent_context=persistent_context
        )
        
        if result["success"]:
            # Send response via Chatwoot
            send_message(
                conversation_id=conversation.id,
                account_id=settings.CHATWOOT_ACCOUNT_ID,
                message=result["response"]
            )
            
            # Update persistent context if changed
            if "context" in result:
                update_data = prepare_chatwoot_update(
                    result["context"].persistent.model_dump(), 
                    inbox_id
                )
                # TODO: Update conversation additional_attributes via Chatwoot API
            
            logger.info(f"✅ Response sent successfully")
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Message processed successfully',
                    'response': result["response"]
                })
            }
        else:
            logger.error(f"Failed to process message: {result}")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Message processing failed'})
            }
            
    except Exception as e:
        logger.error(f"Lambda handler error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

# Health check handler for ALB/API Gateway health checks
def health_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Health check endpoint"""
    return {
        'statusCode': 200,
        'body': json.dumps({
            'status': 'healthy',
            'service': 'posso-react-chatbot',
            'version': '1.0.0'
        })
    }