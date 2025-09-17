import os
import json
from dotenv import load_dotenv

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

    # Pipedrive Configuration
    PIPEDRIVE_API_URL: str = os.getenv("PIPEDRIVE_API_URL", "https://api.pipedrive.com/v1")
    PIPEDRIVE_APIV2_URL: str = os.getenv("PIPEDRIVE_APIV2_URL", "https://api.pipedrive.com")

    # Load all school-specific Pipedrive API keys from JSON
    PIPEDRIVE_API_KEYS: dict = json.loads(
        os.getenv("PIPEDRIVE_API_KEYS_JSON")
    )

    # Chatwoot Configuration
    CHATWOOT_API_URL: str = os.getenv("CHATWOOT_API_URL", "https://app.chatwoot.com")
    CHATWOOT_ACCOUNT_ID: int = int(os.getenv("CHATWOOT_ACCOUNT_ID", "1"))
    CHATWOOT_API_KEY: str = os.getenv("CHATWOOT_API_KEY", "")

    # Upstash Configuration
    UPSTASH_VECTOR_REST_URL: str = os.getenv("UPSTASH_VECTOR_REST_URL", "")
    UPSTASH_VECTOR_REST_TOKEN: str = os.getenv("UPSTASH_VECTOR_REST_TOKEN", "")

    
    @classmethod
    def validate(cls) -> bool:
        """Validate required environment variables"""
        if not cls.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is required")
        return True

# Global settings instance
settings = Settings()