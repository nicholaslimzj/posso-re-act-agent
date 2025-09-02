import os
from dotenv import load_dotenv
from typing import Optional

# Load environment variables
load_dotenv()

class Settings:
    # OpenRouter Configuration
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "openai/gpt-4o-mini-2024-07-18")
    
    # Redis Configuration  
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    REDIS_SESSION_TTL: int = 3600  # 1 hour in seconds
    
    # LangChain Tracing
    LANGCHAIN_TRACING_V2: str = os.getenv("LANGCHAIN_TRACING_V2", "false")
    LANGCHAIN_API_KEY: str = os.getenv("LANGCHAIN_API_KEY", "")
    
    # ReAct Agent Configuration
    MAX_REASONING_CYCLES: int = 10
    SESSION_LOCK_TIMEOUT: int = 300  # 5 minutes
    
    # School Configuration
    DEFAULT_SCHOOL_ID: str = "tampines"
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required environment variables"""
        if not cls.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is required")
        return True

# Global settings instance
settings = Settings()