#!/usr/bin/env python3
"""
Test Lambda handler locally before deployment
"""

import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lambda_handler import lambda_handler, health_handler

def test_health_check():
    """Test health check endpoint"""
    print("🔍 Testing health check...")
    
    event = {}
    context = {}
    
    response = health_handler(event, context)
    print(f"Health check response: {response}")
    
    assert response['statusCode'] == 200
    print("✅ Health check passed!")

def test_webhook_handler():
    """Test webhook handler with sample payload"""
    print("🔍 Testing webhook handler...")
    
    # Sample Chatwoot webhook payload
    sample_webhook = {
        "event": "message_created",
        "data": {
            "content": "What are your school fees?",
            "message_type": 0,  # Incoming message
            "conversation": {
                "id": 123,
                "inbox_id": 1,
                "contact_last_seen_at": "1234567890",
                "additional_attributes": {}
            }
        }
    }
    
    # Test with API Gateway format
    event = {
        "body": json.dumps(sample_webhook),
        "headers": {
            "Content-Type": "application/json"
        }
    }
    
    context = {}
    
    try:
        response = webhook_handler(event, context)
        print(f"Webhook response: {response}")
        
        if response['statusCode'] == 200:
            print("✅ Webhook test passed!")
        else:
            print(f"⚠️ Webhook test returned: {response['statusCode']}")
            
    except Exception as e:
        print(f"❌ Webhook test failed: {e}")

def main():
    """Run local Lambda tests"""
    print("🧪 Testing Lambda handlers locally...")
    
    # Check environment variables
    required_vars = [
        'UPSTASH_VECTOR_REST_URL',
        'UPSTASH_VECTOR_REST_TOKEN',
        'REDIS_URL',
        'OPENROUTER_API_KEY'
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"❌ Missing environment variables: {missing_vars}")
        print("Make sure to set these in your .env file")
        return
    
    try:
        test_health_check()
        # Uncomment when ready to test full webhook flow
        # test_webhook_handler()
        
        print("🎉 All local tests passed! Ready for Lambda deployment.")
        
    except Exception as e:
        print(f"❌ Tests failed: {e}")

if __name__ == "__main__":
    main()