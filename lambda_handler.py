"""
AWS Lambda handler for Posso ReAct School Chatbot
Optimized for SnapStart with proper initialization separation
"""

import json
import os
import asyncio
import platform
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
        
        # Only process message created events (including automation events)
        if webhook.event not in ["message_created", "automation_event.message_created"]:
            logger.info(f"Ignoring event: {webhook.event}")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Event ignored'})
            }
        
        # Extract latest incoming message
        latest_message = webhook.get_latest_message()
        if not latest_message:
            logger.info("No incoming message found")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'No message to process'})
            }
        
        message_content = latest_message.content.strip()
        
        # Skip if message is empty
        if not message_content:
            logger.info("Skipping empty message")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Message skipped'})
            }
        
        # Get conversation details
        inbox_id = webhook.inbox_id
        contact_id = str(webhook.contact_inbox.contact_id)
        conversation_id = str(webhook.id)
        message_id = str(latest_message.id)
        
        # Extract contact info (like web_app does)
        contact_info = webhook.get_contact_info()
        whatsapp_profile = {
            "name": contact_info.get("name"),
            "phone": contact_info.get("phone")
        }
        
        # Get conversation history from API (like web_app does)
        messages = []
        if settings.CHATWOOT_API_KEY:
            logger.info(f"Fetching conversation messages for conversation {webhook.id}")
            try:
                messages_from_api = asyncio.run(get_conversation_messages(
                    account_id=settings.CHATWOOT_ACCOUNT_ID,
                    conversation_id=webhook.id,
                    api_key=settings.CHATWOOT_API_KEY
                ))
                if messages_from_api:
                    messages = messages_from_api
                    logger.info(f"Fetched {len(messages)} messages from Chatwoot API")
                else:
                    logger.warning("No messages fetched from Chatwoot API")
            except Exception as e:
                logger.error(f"Error fetching messages: {e}")
                
        # Fallback to webhook messages if API fetch failed
        if not messages and webhook.messages:
            messages = [msg.model_dump() for msg in webhook.messages]
            logger.info(f"Using {len(messages)} messages from webhook (fallback)")
        
        # Extract persistent context from contact_info (like web_app does)
        persistent_data = {}
        if contact_info.get("additional_attributes"):
            persistent_data = extract_persistent_context(
                contact_info["additional_attributes"],
                inbox_id
            )
        
        # Get message handler and process (exactly like web_app)
        handler = get_message_handler()
        result = asyncio.run(handler.process_chatwoot_message_async(
            inbox_id=inbox_id,
            contact_id=contact_id,
            conversation_id=conversation_id,
            message_content=message_content,
            message_id=message_id,
            whatsapp_profile=whatsapp_profile,
            chatwoot_additional_params=persistent_data,
            recent_messages=messages
        ))
        
        if result["success"]:
            # Send response via Chatwoot API (using sync wrapper)
            # Skip sending if message was queued (another process will handle it)
            if result.get("response") and not result.get("queued"):
                try:
                    send_result = asyncio.run(send_message(
                        account_id=settings.CHATWOOT_ACCOUNT_ID,
                        conversation_id=webhook.id,
                        message=result["response"],
                        api_key=settings.CHATWOOT_API_KEY
                    ))
                    if send_result.get("success"):
                        logger.info(f"✅ Response sent successfully to conversation {webhook.id}")
                    else:
                        logger.error(f"Failed to send message: {send_result.get('error')}")
                except Exception as e:
                    logger.error(f"Error sending message: {e}")
            
            # Update persistent context if changed (like web_app does)
            if result.get("chatwoot_sync_data"):
                update_data = prepare_chatwoot_update(
                    result["chatwoot_sync_data"],
                    inbox_id
                )
                logger.info(f"Context updated: {len(result['chatwoot_sync_data'])} fields")
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
    """Health check endpoint with system information"""
    
    # Determine architecture type
    machine = platform.machine().lower()
    arch_type = "arm64" if machine == "aarch64" else "x86_64" if machine == "x86_64" else machine
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'status': 'healthy',
            'service': 'posso-react-chatbot',
            'version': '1.0.0',
            'architecture': arch_type,
            'platform_machine': platform.machine(),
            'platform_processor': platform.processor(),
            'python_version': platform.python_version()
        })
    }