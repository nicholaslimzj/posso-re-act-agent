#!/usr/bin/env python3
"""
Test Upstash Redis + Vector integration
"""

import asyncio
import redis
import httpx
import os
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")
UPSTASH_VECTOR_REST_URL = os.getenv("UPSTASH_VECTOR_REST_URL")
UPSTASH_VECTOR_REST_TOKEN = os.getenv("UPSTASH_VECTOR_REST_TOKEN")

async def test_redis():
    """Test Upstash Redis connection"""
    logger.info("Testing Upstash Redis connection...")
    
    try:
        # Connect to Redis
        r = redis.from_url(REDIS_URL, decode_responses=True)
        
        # Test write
        test_key = f"test_key_{datetime.now().isoformat()}"
        r.set(test_key, "Hello Upstash Redis!")
        
        # Test read
        value = r.get(test_key)
        
        if value == "Hello Upstash Redis!":
            logger.info("✅ Redis connection successful!")
            
            # Clean up
            r.delete(test_key)
            return True
        else:
            logger.error("❌ Redis test failed - value mismatch")
            return False
            
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        return False

async def test_vector_search():
    """Test Upstash Vector search"""
    logger.info("Testing Upstash Vector search...")
    
    try:
        test_queries = [
            "What are your school fees?",
            "Can I book a tour?", 
            "What programs do you offer?"
        ]
        
        async with httpx.AsyncClient() as client:
            for query in test_queries:
                response = await client.post(
                    f"{UPSTASH_VECTOR_REST_URL}/query-data",
                    headers={
                        "Authorization": f"Bearer {UPSTASH_VECTOR_REST_TOKEN}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "data": query,
                        "topK": 2,
                        "includeMetadata": True
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("result") and len(result["result"]) > 0:
                        top_match = result["result"][0]
                        score = top_match.get("score", 0)
                        title = top_match["metadata"]["title"]
                        logger.info(f"✅ Query: '{query}' → Match: '{title}' (score: {score:.3f})")
                    else:
                        logger.warning(f"⚠️ No results for: '{query}'")
                else:
                    logger.error(f"❌ Vector search failed: {response.status_code}")
                    return False
        
        logger.info("✅ Vector search tests completed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Vector search failed: {e}")
        return False

async def test_faq_tool():
    """Test the new FAQ tool"""
    logger.info("Testing FAQ tool integration...")
    
    try:
        # Import the new FAQ tool
        from tools.faq_tool_upstash import get_faq_answer_upstash
        
        test_question = "What are your school fees?"
        result = get_faq_answer_upstash(test_question)  # Now sync function
        
        if result.get("status") == "success":
            logger.info(f"✅ FAQ Tool Test Passed!")
            logger.info(f"Question: {test_question}")
            logger.info(f"Answer: {result['answer'][:100]}...")
            return True
        else:
            logger.error(f"❌ FAQ Tool Test Failed: {result}")
            return False
            
    except Exception as e:
        logger.error(f"❌ FAQ Tool Test Failed: {e}")
        return False

async def main():
    """Run all integration tests"""
    logger.info("🚀 Testing Upstash Redis + Vector Integration...")
    
    # Check environment variables
    if not all([REDIS_URL, UPSTASH_VECTOR_REST_URL, UPSTASH_VECTOR_REST_TOKEN]):
        logger.error("❌ Missing environment variables!")
        logger.info("Required: REDIS_URL, UPSTASH_VECTOR_REST_URL, UPSTASH_VECTOR_REST_TOKEN")
        return
    
    tests = [
        ("Redis Connection", test_redis()),
        ("Vector Search", test_vector_search()),
        ("FAQ Tool Integration", test_faq_tool())
    ]
    
    results = []
    for test_name, test_coro in tests:
        logger.info(f"\n--- {test_name} ---")
        result = await test_coro
        results.append((test_name, result))
    
    # Summary
    logger.info("\n🎯 Test Results Summary:")
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status} {test_name}")
        if not passed:
            all_passed = False
    
    if all_passed:
        logger.info("\n🎉 All tests passed! Upstash integration is ready!")
    else:
        logger.error("\n💥 Some tests failed. Check the logs above.")

if __name__ == "__main__":
    asyncio.run(main())