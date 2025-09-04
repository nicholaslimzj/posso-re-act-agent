#!/usr/bin/env python3
"""
Test concurrent message handling
"""

import requests
import json
import time
import threading
from datetime import datetime

BASE_URL = "http://localhost:8000"

def send_message(content: str, delay: float = 0):
    """Send a test message after optional delay"""
    if delay > 0:
        time.sleep(delay)
    
    payload = {
        "inbox_id": 74274,
        "contact_id": "test_contact_123",
        "conversation_id": "test_conv_456",
        "content": content
    }
    
    try:
        response = requests.post(f"{BASE_URL}/test", json=payload)
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] Sent: '{content}' -> Response: {response.json()}")
        return response.json()
    except Exception as e:
        print(f"Error sending '{content}': {e}")
        return None

def test_rapid_messages():
    """Test scenario: User sends child name and DOB in rapid succession"""
    print("\n=== Test 1: Rapid Child Info Messages ===")
    
    # First message - triggers ReAct processing
    thread1 = threading.Thread(target=send_message, args=("My child is Emma",))
    
    # Second message - should be queued while first is processing
    thread2 = threading.Thread(target=send_message, args=("Born 15 March 2018", 0.2))
    
    thread1.start()
    thread2.start()
    
    thread1.join()
    thread2.join()
    
    print("\nWaiting 3 seconds for processing to complete...")
    time.sleep(3)

def test_multiple_rapid_messages():
    """Test scenario: User sends 3+ messages rapidly"""
    print("\n=== Test 2: Multiple Rapid Messages ===")
    
    messages = [
        "I need to book a tour",
        "For my daughter Sophie",
        "She's 4 years old",
        "Born in 2020"
    ]
    
    threads = []
    for i, msg in enumerate(messages):
        thread = threading.Thread(target=send_message, args=(msg, i * 0.1))
        threads.append(thread)
        thread.start()
    
    for thread in threads:
        thread.join()
    
    print("\nWaiting 5 seconds for processing to complete...")
    time.sleep(5)

def test_context_switch():
    """Test scenario: User changes topic mid-processing"""
    print("\n=== Test 3: Context Switch During Processing ===")
    
    # First message about tour
    thread1 = threading.Thread(target=send_message, args=("I want to book a tour for next week",))
    
    # Second message changes topic
    thread2 = threading.Thread(target=send_message, args=("What are your school fees?", 0.5))
    
    thread1.start()
    thread2.start()
    
    thread1.join()
    thread2.join()
    
    print("\nWaiting 3 seconds for processing to complete...")
    time.sleep(3)

def test_sequential_with_queued():
    """Test scenario: Normal flow with queued message"""
    print("\n=== Test 4: Sequential with Queued Message ===")
    
    # Ask a question that expects follow-up
    result = send_message("I want to book a tour")
    time.sleep(1)
    
    # If bot asks for info, provide it in two messages
    if result and "child" in result.get("response", "").lower():
        print("\nBot asked for child info, sending in two messages...")
        thread1 = threading.Thread(target=send_message, args=("My child is Max",))
        thread2 = threading.Thread(target=send_message, args=("He's 5 years old", 0.1))
        
        thread1.start()
        thread2.start()
        
        thread1.join()
        thread2.join()

if __name__ == "__main__":
    print("🧪 Testing Concurrent Message Handling")
    print("=" * 50)
    
    # Check if server is running
    try:
        health = requests.get(f"{BASE_URL}/health")
        if health.status_code == 200:
            print("✅ Server is healthy")
        else:
            print("❌ Server health check failed")
            exit(1)
    except:
        print("❌ Cannot connect to server at", BASE_URL)
        exit(1)
    
    # Run tests
    test_rapid_messages()
    test_multiple_rapid_messages()
    test_context_switch()
    test_sequential_with_queued()
    
    print("\n" + "=" * 50)
    print("✅ All tests completed")