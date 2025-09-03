#!/usr/bin/env python3
"""
ReAct School Chatbot - Main Entry Point
"""

import os
from loguru import logger
from config import settings


def main():
    """Main entry point - determines run mode"""
    run_mode = os.getenv("RUN_MODE", "test").lower()
    
    logger.info(f"🚀 Starting Posso ReAct School Chatbot in {run_mode.upper()} mode")
    
    try:
        # Validate settings
        settings.validate()
        logger.info("✅ Settings validated")
        
        if run_mode == "web":
            # Run as web server
            logger.info("Starting FastAPI web server...")
            import uvicorn
            
            # Enable reload in development
            is_dev = os.getenv("DEV_MODE", "false").lower() == "true"
            
            # Note: workers > 1 disables reload, so only use multi-worker in non-dev mode
            workers = 1 if is_dev else int(os.getenv("WORKERS", "4"))
            
            uvicorn.run(
                "web_app:app",  # Use string import for reload to work
                host="0.0.0.0", 
                port=8000,
                reload=is_dev,
                reload_dirs=["/app"] if is_dev else None,
                workers=workers if not is_dev else None  # Multiple workers only in production
            )
            
        else:
            # Run tests
            logger.info("Running in test mode...")
            from tests.test_agent import (
                test_faq_functionality,
                test_redis_connection,
                test_message_handler
            )
            
            # Run tests
            test_faq_functionality()
            test_redis_connection() 
            test_message_handler()
            
            logger.info("🎉 All tests passed! ReAct School Chatbot is ready.")
        
    except KeyboardInterrupt:
        logger.info("Application interrupted")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise


if __name__ == "__main__":
    main()