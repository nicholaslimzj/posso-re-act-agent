import os
from dotenv import load_dotenv
from typing import Optional, Dict, Any
import threading

# Load environment variables
load_dotenv()

class Settings:
    # OpenRouter Configuration
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")
    RESPONSE_CRAFTING_MODEL: str = os.getenv("RESPONSE_CRAFTING_MODEL", "meta-llama/llama-4-maverick")

    # Redis Configuration
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    REDIS_SESSION_TTL: int = 3600  # 1 hour in seconds

    # LangChain Tracing
    LANGCHAIN_TRACING_V2: str = os.getenv("LANGCHAIN_TRACING_V2", "false")
    LANGCHAIN_API_KEY: str = os.getenv("LANGCHAIN_API_KEY", "")

    # ReAct Agent Configuration
    MAX_REASONING_CYCLES: int = 10
    SESSION_LOCK_TIMEOUT: int = 120  # 2 minutes

    # School Configuration
    DEFAULT_SCHOOL_ID: str = "tampines"

    # Pipedrive Configuration
    PIPEDRIVE_API_URL: str = os.getenv("PIPEDRIVE_API_URL", "https://api.pipedrive.com/v1")
    PIPEDRIVE_APIV2_URL: str = os.getenv("PIPEDRIVE_APIV2_URL", "https://api.pipedrive.com")
    PIPEDRIVE_API_KEY: str = os.getenv("PIPEDRIVE_API_KEY", "")  # Fallback/default API key

    # Chatwoot Configuration
    CHATWOOT_API_URL: str = os.getenv("CHATWOOT_API_URL", "https://app.chatwoot.com")
    CHATWOOT_ACCOUNT_ID: int = int(os.getenv("CHATWOOT_ACCOUNT_ID", "1"))
    CHATWOOT_API_KEY: str = os.getenv("CHATWOOT_API_KEY", "")

    # Upstash Configuration
    UPSTASH_VECTOR_REST_URL: str = os.getenv("UPSTASH_VECTOR_REST_URL", "")
    UPSTASH_VECTOR_REST_TOKEN: str = os.getenv("UPSTASH_VECTOR_REST_TOKEN", "")

    # Thread-local storage for current school context
    _local = threading.local()

    @classmethod
    def set_current_school_config(cls, school_config: Dict[str, Any]) -> None:
        """Set the current school configuration for this request/thread"""
        cls._local.school_config = school_config

    @classmethod
    def get_current_school_config(cls) -> Optional[Dict[str, Any]]:
        """Get the current school configuration for this request/thread"""
        return getattr(cls._local, 'school_config', None)

    @property
    def current_pipedrive_api_key(self) -> str:
        """
        Get the Pipedrive API key for the current school context.
        Falls back to the default PIPEDRIVE_API_KEY if no school context is set.
        """
        school_config = self.get_current_school_config()
        if not school_config:
            return self.PIPEDRIVE_API_KEY

        # Import here to avoid circular imports
        from integrations.pipedrive import get_pipedrive_api_key
        return get_pipedrive_api_key(school_config)
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required environment variables"""
        if not cls.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is required")
        return True

# Global settings instance
settings = Settings()