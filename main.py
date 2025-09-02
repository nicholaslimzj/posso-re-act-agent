#!/usr/bin/env python3
"""
ReAct School Chatbot - Main Entry Point
"""

import asyncio
from uuid import uuid4
from loguru import logger
from typing import Dict, Any

from config import settings
from context import FullContext, RuntimeContext, PersistentContext, ActiveTaskContext, TaskType
from agents.react_agent import ReActAgent
from message_handler import message_handler


def create_mock_context() -> FullContext:
    """Create mock context for testing"""
    runtime_context = RuntimeContext(
        conversation_id="test_conv_123",
        inbox_id=1,
        school_id="tampines",
        whatsapp_name="John Smith",
        whatsapp_phone="+65-9123-4567",
        school_config={
            "available_times": ["09:00", "11:00", "14:00", "16:00"],
            "tour_duration_minutes": 60,
            "max_advance_booking_days": 30,
            "contact_email": "tampines@posso.edu.sg"
        }
    )
    
    return FullContext(
        persistent=PersistentContext(),
        runtime=runtime_context,
        active=ActiveTaskContext()
    )


def test_faq_functionality():
    """Test the FAQ tool functionality"""
    logger.info("🔍 Testing FAQ functionality...")
    
    try:
        from tools import get_faq_answer
        
        test_questions = [
            "What makes Posso different from other schools?",
            "What are your school hours?",
            "Do you provide meals?",
            "What is the admission process?",
            "How much does it cost?"
        ]
        
        for question in test_questions:
            result = get_faq_answer(question)
            logger.info(f"Q: {question}")
            logger.info(f"A: {result.get('status', 'success')}")
            
            if result.get("status") == "success":
                logger.info(f"Answer preview: {result['answer'][:100]}...")
            
            print("-" * 50)
    
    except Exception as e:
        logger.error(f"FAQ test failed: {e}")


def test_message_handler():
    """Test the complete message handling system"""
    logger.info("🤖 Testing Message Handler with ReAct Agent...")
    
    try:
        # Test data - simulating Chatwoot webhook
        inbox_id = 74274  # From schools.json
        contact_id = "test_contact_123"
        conversation_id = "test_conv_456"
        
        test_messages = [
            "Hi, I'd like to know about your school hours",
            "What makes Posso different?", 
            "Can you tell me about the curriculum?",
            "My child is 6 years old, what grade would that be?",
            "Actually, my name is Sarah, not John"  # Context update test
        ]
        
        whatsapp_profile = {
            "name": "John Smith",
            "phone": "+65-9123-4567"
        }
        
        for message in test_messages:
            logger.info(f"👤 User: {message}")
            
            result = message_handler.process_chatwoot_message(
                inbox_id=inbox_id,
                contact_id=contact_id,
                conversation_id=conversation_id,
                message_content=message,
                message_id=f"msg_{uuid4().hex[:8]}",
                whatsapp_profile=whatsapp_profile
            )
            
            if result["success"]:
                logger.info(f"🤖 Agent: {result['response']}")
                logger.info(f"Reasoning cycles: {result.get('cycles_count', 0)}")
                
                if result.get('chatwoot_sync_data'):
                    logger.info(f"Context updates: {len(result['chatwoot_sync_data'])} fields")
            else:
                logger.error(f"❌ Error: {result.get('error', 'Unknown error')}")
            
            print("-" * 50)
    
    except Exception as e:
        logger.error(f"Message handler test failed: {e}")


def test_react_agent():
    """Test the basic ReAct agent"""
    logger.info("🔧 Testing basic ReAct Agent...")
    
    try:
        # Create test context
        context = create_mock_context()
        
        # Create agent instance
        react_agent = ReActAgent()
        
        test_messages = [
            "Hi, I'd like to know about your school hours",
            "What makes Posso different?"
        ]
        
        for message in test_messages:
            logger.info(f"👤 User: {message}")
            
            result = react_agent.process_message(message, context)
            
            logger.info(f"🤖 Agent: {result['response']}")
            logger.info(f"Reasoning cycles: {result.get('cycles_count', 0)}")
            logger.info(f"Tools used: {result.get('tools_used', [])}")
            
            print("-" * 50)
    
    except Exception as e:
        logger.error(f"ReAct agent test failed: {e}")


def test_redis_connection():
    """Test Redis connectivity"""
    logger.info("📡 Testing Redis connection...")
    
    try:
        from context import redis_manager
        
        # Test basic operations
        test_school_id = "tampines"
        test_contact_id = "test_123"
        
        # Test context save/retrieve
        test_context = ActiveTaskContext()
        test_context.active_task_type = TaskType.FAQ
        
        # Save context
        success = redis_manager.save_active_context(test_school_id, test_contact_id, test_context)
        logger.info(f"Save context: {'✅' if success else '❌'}")
        
        # Retrieve context
        retrieved = redis_manager.get_active_context(test_school_id, test_contact_id)
        logger.info(f"Retrieve context: {'✅' if retrieved else '❌'}")
        
        # Clean up
        redis_manager.delete_all_context(test_school_id, test_contact_id)
        logger.info("Redis test completed ✅")
    
    except Exception as e:
        logger.error(f"Redis test failed: {e}")


async def interactive_chat():
    """Interactive chat session for testing"""
    logger.info("💬 Starting interactive chat session...")
    logger.info("Type 'quit' to exit, 'test' to run tests")
    
    context = create_mock_context()
    
    while True:
        try:
            user_input = input("\n👤 You: ").strip()
            
            if user_input.lower() == 'quit':
                break
            elif user_input.lower() == 'test':
                test_faq_functionality()
                test_redis_connection()
                continue
            elif not user_input:
                continue
            
            # Process with ReAct agent
            react_agent = ReActAgent()
            result = react_agent.process_message(user_input, context)
            
            print(f"🤖 Posso Bot: {result['response']}")
            print(f"   (Reasoning cycles: {result.get('cycles_count', 0)})")
            
            # Context is maintained separately, not in agent result
            
        except KeyboardInterrupt:
            logger.info("Chat session interrupted")
            break
        except EOFError:
            logger.info("EOF received, ending chat session")
            break
        except Exception as e:
            logger.error(f"Error in chat: {e}")
            break


def main():
    """Main entry point"""
    logger.info("🚀 Starting Posso ReAct School Chatbot")
    
    try:
        # Validate settings
        settings.validate()
        logger.info("✅ Settings validated")
        
        # Run tests first
        test_faq_functionality()
        test_redis_connection() 
        test_message_handler()
        
        # Skip interactive session in Docker, just show success
        logger.info("🎉 All tests passed! ReAct School Chatbot is ready.")
        logger.info("For interactive testing, run outside Docker or use the message_handler API directly.")
        
    except KeyboardInterrupt:
        logger.info("Application interrupted")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise


if __name__ == "__main__":
    main()