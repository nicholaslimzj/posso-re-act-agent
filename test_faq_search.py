#!/usr/bin/env python3
"""
Test FAQ search to verify vector vs text search
"""
from loguru import logger
from tools import get_faq_answer

# Test questions
test_questions = [
    "What makes your school special?",  # Semantic match to "What makes Posso different?"
    "Tell me about class sizes",  # Should match small class info
    "Hours of operation",  # Should match school hours
    "Do you have a kindergarten program?",  # Should match age/grade info
]

print("=" * 60)
print("FAQ SEARCH TEST - Check logs to see if using VECTOR or TEXT")
print("=" * 60)

for q in test_questions:
    print(f"\n📌 Question: {q}")
    result = get_faq_answer(q)
    
    if result.get("status") == "success":
        print(f"✅ Found answer with similarities: {result.get('similarity_scores', [])[:1]}")
        print(f"   Related: {result.get('related_topics', [])[:1]}")
    else:
        print(f"❌ No match found")

print("\n" + "=" * 60)
print("Check the logs above to see:")
print("  🔍 'Using VECTOR SEARCH' = Embeddings are working!")
print("  📝 'Using TEXT SEARCH' = Fallback to keyword matching")
print("=" * 60)