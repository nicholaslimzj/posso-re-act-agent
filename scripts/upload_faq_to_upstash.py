#!/usr/bin/env python3
"""
Upload FAQ data to Upstash Vector
Uses Upstash's built-in vectorization to ensure consistency with query-data endpoint.
"""

import asyncio
import httpx
import os
from typing import List, Dict, Any
import json
from loguru import logger

# Load environment variables (try .env file if running locally)
from dotenv import load_dotenv
load_dotenv()  # This will silently fail if .env doesn't exist (which is fine in Docker)

UPSTASH_VECTOR_REST_URL = os.getenv("UPSTASH_VECTOR_REST_URL")
UPSTASH_VECTOR_REST_TOKEN = os.getenv("UPSTASH_VECTOR_REST_TOKEN")

# Debug: Print env vars (without token)
print(f"UPSTASH_VECTOR_REST_URL: {UPSTASH_VECTOR_REST_URL}")
print(f"UPSTASH_VECTOR_REST_TOKEN: {'***' if UPSTASH_VECTOR_REST_TOKEN else 'NOT SET'}")

if not UPSTASH_VECTOR_REST_URL or not UPSTASH_VECTOR_REST_TOKEN:
    raise ValueError("Please set UPSTASH_VECTOR_REST_URL and UPSTASH_VECTOR_REST_TOKEN in .env")

async def clear_database():
    """Clear all vectors from the Upstash Vector database"""
    logger.info("🗑️ Clearing Upstash Vector database...")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.delete(
            f"{UPSTASH_VECTOR_REST_URL}/reset",
            headers={
                "Authorization": f"Bearer {UPSTASH_VECTOR_REST_TOKEN}"
            }
        )
        
        if response.status_code != 200:
            logger.error(f"Clear failed: {response.status_code} - {response.text}")
            raise Exception("Failed to clear database")
        
        logger.info("✅ Database cleared successfully!")

async def upload_faq_data():
    """Upload FAQ content to Upstash Vector using auto-vectorization"""
    
    # Read FAQ content
    faq_path = "data/posso_faq.txt"
    if not os.path.exists(faq_path):
        raise FileNotFoundError(f"FAQ file not found at {faq_path}")
    
    with open(faq_path, 'r', encoding='utf-8') as f:
        faq_content = f.read()
    
    # Split FAQ into sections (assuming double newlines separate sections)
    sections = [section.strip() for section in faq_content.split('\n\n') if section.strip()]
    logger.info(f"Found {len(sections)} FAQ sections")
    
    # Prepare data for upload using upsert-data (auto-vectorization)
    vectors_to_upload = []
    for i, section in enumerate(sections):
        # Extract title (first line) and answer (rest)
        lines = section.split('\n', 1)  # Split only on first newline
        title = lines[0] if lines else f"Section {i+1}"
        answer = lines[1].strip() if len(lines) > 1 else ""

        vectors_to_upload.append({
            "id": f"faq_{i}",
            "data": section,  # Full text for vectorization (question + answer)
            "metadata": {
                "title": title,
                "content": answer,  # Just the answer, without the question
                "section_id": i
            }
        })
    
    # Upload to Upstash Vector using upsert-data
    logger.info(f"Uploading {len(vectors_to_upload)} text sections to Upstash (auto-vectorization)...")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Upload in batches (Upstash may have limits)
        batch_size = 100
        for i in range(0, len(vectors_to_upload), batch_size):
            batch = vectors_to_upload[i:i + batch_size]
            
            response = await client.post(
                f"{UPSTASH_VECTOR_REST_URL}/upsert-data",
                headers={
                    "Authorization": f"Bearer {UPSTASH_VECTOR_REST_TOKEN}",
                    "Content-Type": "application/json"
                },
                json=batch
            )
            
            if response.status_code != 200:
                logger.error(f"Upload failed: {response.status_code} - {response.text}")
                raise Exception(f"Failed to upload batch {i//batch_size + 1}")
            
            logger.info(f"Uploaded batch {i//batch_size + 1}/{(len(vectors_to_upload) + batch_size - 1)//batch_size}")
    
    logger.info("✅ FAQ data successfully uploaded to Upstash Vector!")
    
    # Test the search
    await test_search()

async def test_search():
    """Test the uploaded embeddings by searching"""
    logger.info("Testing search functionality...")
    
    test_queries = [
        "What are your school fees?",
        "What programs do you offer?",
        "How can I book a tour?"
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
                if result.get("result"):
                    top_match = result["result"][0]
                    logger.info(f"Query: '{query}'")
                    logger.info(f"Match: {top_match['metadata']['title']} (score: {top_match.get('score', 'N/A')})")
                    logger.info("")
            else:
                logger.error(f"Search test failed: {response.status_code} - {response.text}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "clear":
        logger.info("Running in CLEAR mode...")
        asyncio.run(clear_database())
    else:
        logger.info("Running in UPLOAD mode...")
        asyncio.run(upload_faq_data())