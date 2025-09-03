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
from tools.chatwoot_history_formatter import (
    extract_persistent_context,
    prepare_chatwoot_update
)
from context import PersistentContext

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
        
        # Format recent conversation history
        recent_messages = []
        if webhook.messages:
            # Keep messages as dict format for context
            recent_messages = [msg.model_dump() for msg in webhook.messages[-10:]]  # Last 10 messages
        
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
                logger.info(f"Updating Chatwoot attributes: {len(result['chatwoot_sync_data'])} fields")
            
            return JSONResponse(content=response_data, status_code=200)
        else:
            logger.error(f"Error processing message: {result.get('error')}")
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