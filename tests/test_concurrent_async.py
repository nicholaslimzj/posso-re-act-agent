#!/usr/bin/env python3
"""
Test concurrent message handling with async requests
"""

import asyncio
import aiohttp
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"

async def send_message_async(session, content: str, delay: float = 0):
    """Send a test message asynchronously after optional delay"""
    if delay > 0:
        await asyncio.sleep(delay)
    
    payload = {
        "inbox_id": 74274,
        "contact_id": "test_contact_123",
        "conversation_id": "test_conv_456",
        "content": content
    }
    
    try:
        async with session.post(f"{BASE_URL}/test", json=payload) as response:
            result = await response.json()
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            
            # Check if message was queued
            if result.get("queued"):
                print(f"[{timestamp}] QUEUED: '{content}' -> {result.get('response')}")
            else:
                print(f"[{timestamp}] PROCESSED: '{content}' -> {result.get('response', '')[:100]}...")
            
            return result
    except Exception as e:
        print(f"Error sending '{content}': {e}")
        return None

async def test_rapid_two_messages():
    """Test: User sends child name and DOB in rapid succession"""
    print("\n=== Test 1: Two Rapid Messages (Name + DOB) ===")
    
    async with aiohttp.ClientSession() as session:
        # Send both messages concurrently
        tasks = [
            send_message_async(session, "My child is Emma"),
            send_message_async(session, "Born 15 March 2018", 0.05)  # Tiny delay to ensure order
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Check results
        print("\nResults:")
        print(f"Message 1 queued: {results[0].get('queued', False)}")
        print(f"Message 2 queued: {results[1].get('queued', False)}")
        
        # One should process, one should queue
        assert not results[0].get('queued'), "First message should process"
        assert results[1].get('queued'), "Second message should be queued"
        
        print("✅ Test passed: Second message was queued while first processed")

async def test_multiple_rapid():
    """Test: User sends 4 messages rapidly"""
    print("\n=== Test 2: Four Rapid Messages ===")
    
    async with aiohttp.ClientSession() as session:
        messages = [
            "I need to book a tour",
            "For my daughter Sophie",
            "She's 4 years old", 
            "Born in 2020"
        ]
        
        # Send all messages with tiny delays to maintain order
        tasks = []
        for i, msg in enumerate(messages):
            tasks.append(send_message_async(session, msg, i * 0.02))
        
        results = await asyncio.gather(*tasks)
        
        # Count queued messages
        queued_count = sum(1 for r in results if r.get('queued'))
        print(f"\n{queued_count} out of {len(messages)} messages were queued")
        
        # First should process, rest should queue
        assert not results[0].get('queued'), "First message should process"
        assert queued_count == 3, "Three messages should be queued"
        
        print("✅ Test passed: Multiple messages queued correctly")

async def test_true_concurrent():
    """Test: Truly concurrent messages (no delay)"""
    print("\n=== Test 3: Truly Concurrent Messages ===")
    
    async with aiohttp.ClientSession() as session:
        # Fire all at once, no delays
        tasks = [
            send_message_async(session, "Message A"),
            send_message_async(session, "Message B"),
            send_message_async(session, "Message C")
        ]
        
        results = await asyncio.gather(*tasks)
        
        # At least one should process, others should queue
        processed = sum(1 for r in results if not r.get('queued'))
        queued = sum(1 for r in results if r.get('queued'))
        
        print(f"\nProcessed: {processed}, Queued: {queued}")
        assert processed >= 1, "At least one message should process"
        assert queued >= 1, "At least one message should be queued"
        
        print("✅ Test passed: Concurrent messages handled correctly")

async def main():
    print("🧪 Testing Concurrent Message Handling (Async)")
    print("=" * 50)
    
    # Check server health
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{BASE_URL}/health") as response:
                if response.status == 200:
                    print("✅ Server is healthy")
                else:
                    print("❌ Server health check failed")
                    return
        except Exception as e:
            print(f"❌ Cannot connect to server: {e}")
            return
    
    # Run tests
    await test_rapid_two_messages()
    await asyncio.sleep(2)  # Let first test complete
    
    await test_multiple_rapid()
    await asyncio.sleep(2)  # Let second test complete
    
    await test_true_concurrent()
    
    print("\n" + "=" * 50)
    print("✅ All async tests completed")

if __name__ == "__main__":
    asyncio.run(main())