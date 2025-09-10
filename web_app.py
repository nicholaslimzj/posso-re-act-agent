#!/usr/bin/env python3
"""
FastAPI web server for Chatwoot webhook integration
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any
from loguru import logger
import json

from models.webhook_models import ChatwootWebhook, ChatwootResponse
from message_handler import message_handler
from context.chatwoot_history_formatter import (
    extract_persistent_context,
    prepare_chatwoot_update
)
from context import PersistentContext
from integrations.chatwoot import get_conversation_messages, send_message, update_contact_attributes
from config import settings

app = FastAPI(title="Posso ReAct School Chatbot", version="1.0.0")


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Posso ReAct School Chatbot is running"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "posso-react-chatbot"}


@app.post("/webhook/chatwoot")
async def chatwoot_webhook(request: Request):
    """
    Handle incoming Chatwoot webhook
    """
    try:
        # Get raw payload
        payload = await request.json()
        logger.info(f"Received webhook event: {payload.get('event', 'unknown')}")
        
        # Parse webhook
        webhook = ChatwootWebhook(**payload)
        
        # Only process message created events
        if "message_created" not in webhook.event:
            return JSONResponse(
                content={"success": True, "message": "Event ignored"},
                status_code=200
            )
        
        # Get the latest incoming message
        latest_message = webhook.get_latest_message()
        if not latest_message:
            logger.warning("No incoming message found in webhook")
            return JSONResponse(
                content={"success": True, "message": "No message to process"},
                status_code=200
            )
        
        # Extract key identifiers
        inbox_id = webhook.inbox_id
        contact_id = str(webhook.contact_inbox.contact_id)
        conversation_id = str(webhook.id)
        message_content = latest_message.content
        message_id = str(latest_message.id)
        
        # Extract contact info
        contact_info = webhook.get_contact_info()
        whatsapp_profile = {
            "name": contact_info.get("name"),
            "phone": contact_info.get("phone")
        }
        
        # Extract persistent context from additional_attributes
        persistent_data = {}
        if contact_info.get("additional_attributes"):
            persistent_data = extract_persistent_context(
                contact_info["additional_attributes"],
                inbox_id
            )
        
        # Fetch full conversation history from Chatwoot API
        recent_messages = []
        if settings.CHATWOOT_API_KEY:
            logger.info(f"Fetching conversation messages for conversation {conversation_id}")
            messages_from_api = await get_conversation_messages(
                account_id=settings.CHATWOOT_ACCOUNT_ID,
                conversation_id=int(conversation_id),
                api_key=settings.CHATWOOT_API_KEY
            )
            if messages_from_api:
                recent_messages = messages_from_api
                logger.info(f"Fetched {len(recent_messages)} messages from Chatwoot API")
            else:
                logger.warning("No messages fetched from Chatwoot API")
        else:
            # Fallback to webhook messages if API key not configured
            if webhook.messages:
                recent_messages = [msg.model_dump() for msg in webhook.messages]
                logger.info(f"Using {len(recent_messages)} messages from webhook (no API key)")
            else:
                logger.info("No conversation history available")
        
        logger.info(f"Processing message from contact {contact_id}: {message_content[:50]}...")
        
        # Process with message handler (async to not block)
        result = await message_handler.process_chatwoot_message_async(
            inbox_id=inbox_id,
            contact_id=contact_id,
            conversation_id=conversation_id,
            message_content=message_content,
            message_id=message_id,
            whatsapp_profile=whatsapp_profile,
            chatwoot_additional_params=persistent_data,
            recent_messages=recent_messages
        )
        
        if result["success"]:
            # Send the response message to Chatwoot via API
            if settings.CHATWOOT_API_KEY and result.get("response"):
                send_result = await send_message(
                    account_id=settings.CHATWOOT_ACCOUNT_ID,
                    conversation_id=int(conversation_id),
                    message=result["response"],
                    api_key=settings.CHATWOOT_API_KEY
                )
                if send_result.get("success"):
                    logger.info(f"Successfully sent response to Chatwoot conversation {conversation_id}")
                else:
                    logger.error(f"Failed to send message to Chatwoot: {send_result.get('error')}")
            
            # Update contact attributes if available
            if settings.CHATWOOT_API_KEY and result.get("chatwoot_sync_data"):
                attributes_to_update = prepare_chatwoot_update(
                    result["chatwoot_sync_data"],
                    inbox_id
                )
                try:
                    update_result = await update_contact_attributes(
                        account_id=settings.CHATWOOT_ACCOUNT_ID,
                        contact_id=int(contact_id),
                        attributes=attributes_to_update,
                        api_key=settings.CHATWOOT_API_KEY
                    )
                    if update_result.get("success"):
                        logger.info(f"Successfully updated Chatwoot attributes: {len(result['chatwoot_sync_data'])} fields")
                    else:
                        logger.error(f"Failed to update Chatwoot attributes: {update_result.get('error')}")
                except Exception as e:
                    logger.error(f"Error updating Chatwoot attributes: {e}")
            
            # Prepare response with updated attributes
            response_data = {
                "success": True,
                "message": result["response"]
            }
            
            # Add updated persistent context if available  
            if result.get("chatwoot_sync_data"):
                response_data["additional_attributes"] = prepare_chatwoot_update(
                    result["chatwoot_sync_data"],
                    inbox_id
                )
            
            return JSONResponse(content=response_data, status_code=200)
        else:
            logger.error(f"Error processing message: {result.get('error')}")
            
            # Send error message to Chatwoot
            if settings.CHATWOOT_API_KEY:
                error_message = result.get("response", "I encountered an error processing your message. Please try again.")
                await send_message(
                    account_id=settings.CHATWOOT_ACCOUNT_ID,
                    conversation_id=int(conversation_id),
                    message=error_message,
                    api_key=settings.CHATWOOT_API_KEY
                )
            
            return JSONResponse(
                content={
                    "success": False,
                    "message": result.get("response", "Error processing message")
                },
                status_code=500
            )
            
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return JSONResponse(
            content={
                "success": False,
                "message": "Internal server error"
            },
            status_code=500
        )


@app.post("/test")
async def test_endpoint(message: Dict[str, Any]):
    """
    Test endpoint for direct message processing
    """
    try:
        # Use default test values
        inbox_id = message.get("inbox_id", 74274)
        contact_id = message.get("contact_id", "test_contact")
        conversation_id = message.get("conversation_id", "test_conv")
        message_content = message.get("content", "")
        
        result = await message_handler.process_chatwoot_message_async(
            inbox_id=inbox_id,
            contact_id=contact_id,
            conversation_id=conversation_id,
            message_content=message_content,
            message_id="test_msg",
            whatsapp_profile={"name": "Test User", "phone": "+65-9999-9999"},
            chatwoot_additional_params={},
            recent_messages=[]
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Test endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    import os
    
    # Enable reload in development
    is_dev = os.getenv("DEV_MODE", "false").lower() == "true"
    uvicorn.run(
        "web_app:app",  # Use string import for reload to work
        host="0.0.0.0", 
        port=8000,
        reload=is_dev,
        reload_dirs=["."] if is_dev else None
    )