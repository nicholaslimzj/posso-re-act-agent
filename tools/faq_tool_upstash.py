"""
FAQ Search Tool using Upstash Vector
Replaces the local sentence-transformers approach with serverless vector search
"""

import httpx
import asyncio
from typing import Dict, Any, Optional
from loguru import logger
from config import settings

async def get_faq_answer_upstash_async(question: str) -> Dict[str, Any]:
    """
    Search FAQ using Upstash Vector with built-in embedding
    
    Args:
        question: User's question
        
    Returns:
        Dict with answer or error
    """
    try:
        if not settings.UPSTASH_VECTOR_REST_URL or not settings.UPSTASH_VECTOR_REST_TOKEN:
            return {
                "status": "error",
                "error": "Upstash Vector not configured. Please set UPSTASH_VECTOR_REST_URL and UPSTASH_VECTOR_REST_TOKEN"
            }
        
        # Query Upstash Vector with raw text (embedding handled server-side)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.UPSTASH_VECTOR_REST_URL}/query-data",
                headers={
                    "Authorization": f"Bearer {settings.UPSTASH_VECTOR_REST_TOKEN}",
                    "Content-Type": "application/json"
                },
                json={
                    "data": question,
                    "topK": 3,
                    "includeMetadata": True
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Upstash Vector query failed: {response.status_code} - {response.text}")
                return {
                    "status": "error", 
                    "error": f"Vector search failed: {response.status_code}"
                }
            
            result = response.json()
            
            if not result.get("result") or len(result["result"]) == 0:
                return {
                    "status": "not_found",
                    "message": "I couldn't find specific information about that in our FAQ. Let me help you get in touch with someone who can provide more details."
                }
            
            # Get all matches and analyze them
            matches = result["result"]
            
            # Log all matches for debugging
            logger.info(f"FAQ search - Query: '{question}' | Found {len(matches)} matches")
            for i, match in enumerate(matches):
                score = match.get("score", 0)
                title = match["metadata"].get("title", "Unknown")[:50]
                logger.info(f"  Match {i+1}: {title} (score: {score:.3f})")
            
            # Use the best match if score is decent, otherwise try combining top matches
            best_match = matches[0]
            best_score = best_match.get("score", 0)
            
            if best_score > 0.8:  # High confidence - use single best match
                answer = best_match["metadata"]["content"]
                logger.info(f"Using single best match (score: {best_score:.3f})")
            elif len(matches) > 1 and matches[1].get("score", 0) > 0.6:
                # Multiple decent matches - combine top 2
                answer1 = best_match["metadata"]["content"]
                answer2 = matches[1]["metadata"]["content"]
                answer = f"{answer1}\n\n---\n\nAdditional information:\n{answer2}"
                logger.info(f"Combining top 2 matches (scores: {best_score:.3f}, {matches[1].get('score', 0):.3f})")
            else:
                # Use single best match even if score is lower
                answer = best_match["metadata"]["content"]
                logger.info(f"Using best available match (score: {best_score:.3f})")
            
            return {
                "status": "success",
                "answer": answer,
                "confidence": best_score,
                "source": "FAQ",
                "matches_count": len(matches)
            }
            
    except httpx.TimeoutException:
        logger.error("Upstash Vector query timed out")
        return {
            "status": "error",
            "error": "FAQ search timed out. Please try again."
        }
    except Exception as e:
        logger.error(f"Error in FAQ search: {e}")
        return {
            "status": "error",
            "error": f"FAQ search error: {str(e)}"
        }

def get_faq_answer_upstash(question: str) -> Dict[str, Any]:
    """
    Synchronous wrapper for the async Upstash FAQ search
    LangChain tools need sync functions, so we run the async function in an event loop
    """
    logger.info(f"🔍 FAQ SYNC WRAPPER called with question: {question}")
    try:
        # Simplified approach: always use asyncio.run in a new event loop
        # This handles all edge cases cleanly
        return asyncio.run(get_faq_answer_upstash_async(question))
    except Exception as e:
        logger.error(f"Error in sync FAQ wrapper: {e}")
        return {
            "status": "error", 
            "error": f"FAQ search wrapper error: {str(e)}"
        }