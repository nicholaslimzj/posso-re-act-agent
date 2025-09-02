import json
import redis
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from loguru import logger

from config import settings
from .models import ActiveTaskContext, FullContext, PersistentContext, RuntimeContext

class RedisContextManager:
    def __init__(self):
        self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        
    def _get_base_key(self, inbox_id: int, contact_id: str) -> str:
        """Generate base Redis key from Chatwoot inbox_id and contact_id"""
        return f"{inbox_id}_{contact_id}"
    
    def _get_active_context_key(self, inbox_id: int, contact_id: str) -> str:
        """Generate Redis key for active ReAct session context"""
        return f"{self._get_base_key(inbox_id, contact_id)}:active_context"
    
    def _get_persistent_context_key(self, inbox_id: int, contact_id: str) -> str:
        """Generate Redis key for persistent customer context"""
        return f"{self._get_base_key(inbox_id, contact_id)}:persistent_context"
    
    def _get_new_messages_key(self, inbox_id: int, contact_id: str) -> str:
        """Generate Redis key for new messages flag"""
        return f"{self._get_base_key(inbox_id, contact_id)}:new_messages"
    
    def _get_session_lock_key(self, inbox_id: int, contact_id: str) -> str:
        """Generate Redis key for session lock"""
        return f"{self._get_base_key(inbox_id, contact_id)}:session_lock"
    
    def get_active_context(self, inbox_id: int, contact_id: str) -> Optional[ActiveTaskContext]:
        """Retrieve active ReAct session context from Redis"""
        try:
            redis_key = self._get_active_context_key(inbox_id, contact_id)
            context_data = self.redis_client.get(redis_key)
            
            if context_data:
                data = json.loads(context_data)
                return ActiveTaskContext(**data)
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving active context: {e}")
            return None
    
    def save_active_context(self, inbox_id: int, contact_id: str, context: ActiveTaskContext) -> bool:
        """Save active ReAct session context to Redis with 1-hour TTL"""
        try:
            redis_key = self._get_active_context_key(inbox_id, contact_id)
            
            # Set expiration time if not already set
            if not context.session_expires_at:
                expires_at = datetime.utcnow() + timedelta(seconds=settings.REDIS_SESSION_TTL)
                context.session_expires_at = expires_at.isoformat()
            
            context_data = context.model_dump_json()
            self.redis_client.setex(
                redis_key, 
                settings.REDIS_SESSION_TTL,  # 1 hour
                context_data
            )
            
            logger.debug(f"Saved active context for {inbox_id}_{contact_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving active context: {e}")
            return False
    
    def get_persistent_context(self, inbox_id: int, contact_id: str) -> Optional[PersistentContext]:
        """Retrieve persistent customer context from Redis"""
        try:
            redis_key = self._get_persistent_context_key(inbox_id, contact_id)
            context_data = self.redis_client.get(redis_key)
            
            if context_data:
                data = json.loads(context_data)
                return PersistentContext(**data)
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving persistent context: {e}")
            return None
    
    def save_persistent_context(self, inbox_id: int, contact_id: str, context: PersistentContext) -> bool:
        """Save persistent customer context to Redis with 30-day TTL"""
        try:
            redis_key = self._get_persistent_context_key(inbox_id, contact_id)
            context_data = context.model_dump_json()
            
            # 30 days TTL for persistent context
            ttl_30_days = 30 * 24 * 60 * 60
            self.redis_client.setex(redis_key, ttl_30_days, context_data)
            
            logger.debug(f"Saved persistent context for {inbox_id}_{contact_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving persistent context: {e}")
            return False
    
    def delete_all_context(self, inbox_id: int, contact_id: str) -> bool:
        """Delete all context data for a contact"""
        try:
            base_pattern = f"{self._get_base_key(inbox_id, contact_id)}:*"
            keys = self.redis_client.keys(base_pattern)
            
            if keys:
                result = self.redis_client.delete(*keys)
                logger.debug(f"Deleted {result} context keys for {inbox_id}_{contact_id}")
                return result > 0
            return True
            
        except Exception as e:
            logger.error(f"Error deleting all context: {e}")
            return False
    
    
    def acquire_session_lock(self, inbox_id: int, contact_id: str, lock_id: str, timeout_seconds: int = 300) -> bool:
        """Acquire session lock using Redis atomic operations"""
        try:
            lock_key = self._get_session_lock_key(inbox_id, contact_id)
            
            # Use Redis SETNX (set if not exists) for atomic lock acquisition
            result = self.redis_client.set(
                lock_key, 
                lock_id, 
                nx=True,  # Only set if key doesn't exist
                ex=timeout_seconds  # Expire in 5 minutes by default
            )
            
            if result:
                logger.debug(f"Acquired session lock for {inbox_id}_{contact_id} by {lock_id}")
                return True
            else:
                logger.debug(f"Failed to acquire session lock for {inbox_id}_{contact_id}, already locked")
                return False
            
        except Exception as e:
            logger.error(f"Error acquiring session lock: {e}")
            return False
    
    def check_session_lock(self, inbox_id: int, contact_id: str) -> Optional[str]:
        """Check if session is locked and return lock owner"""
        try:
            lock_key = self._get_session_lock_key(inbox_id, contact_id)
            lock_owner = self.redis_client.get(lock_key)
            return lock_owner
        except Exception as e:
            logger.error(f"Error checking session lock: {e}")
            return None
    
    def release_session_lock(self, inbox_id: int, contact_id: str, lock_id: str) -> bool:
        """Release session lock if owned by lock_id"""
        try:
            lock_key = self._get_session_lock_key(inbox_id, contact_id)
            
            # Lua script for atomic lock release (only if owned by lock_id)
            lua_script = """
                if redis.call('GET', KEYS[1]) == ARGV[1] then
                    return redis.call('DEL', KEYS[1])
                else
                    return 0
                end
            """
            
            result = self.redis_client.eval(lua_script, 1, lock_key, lock_id)
            
            if result:
                logger.debug(f"Released session lock for {inbox_id}_{contact_id} by {lock_id}")
                return True
            else:
                logger.debug(f"Failed to release session lock for {inbox_id}_{contact_id}, not owned by {lock_id}")
                return False
            
        except Exception as e:
            logger.error(f"Error releasing session lock: {e}")
            return False
    
    def queue_message(self, inbox_id: int, contact_id: str, message: Dict[str, Any]) -> bool:
        """Queue a message during active ReAct session"""
        try:
            # Set flag that new messages arrived
            new_msgs_key = self._get_new_messages_key(inbox_id, contact_id)
            self.redis_client.setex(new_msgs_key, 300, "1")  # 5 minute TTL
            
            # Add to context queue
            context = self.get_active_context(inbox_id, contact_id)
            if context:
                from .models import QueuedMessage
                queued_msg = QueuedMessage(
                    message_id=message.get("id", "unknown"),
                    content=message.get("content", ""),
                    timestamp=datetime.utcnow().isoformat()
                )
                context.queued_messages.append(queued_msg)
                return self.save_active_context(inbox_id, contact_id, context)
            
            return False
            
        except Exception as e:
            logger.error(f"Error queuing message: {e}")
            return False
    
    def check_new_messages(self, inbox_id: int, contact_id: str) -> bool:
        """Check if new messages arrived during processing"""
        try:
            new_msgs_key = self._get_new_messages_key(inbox_id, contact_id)
            return self.redis_client.exists(new_msgs_key) > 0
        except Exception as e:
            logger.error(f"Error checking new messages: {e}")
            return False
    
    def clear_new_messages_flag(self, inbox_id: int, contact_id: str) -> bool:
        """Clear new messages flag"""
        try:
            new_msgs_key = self._get_new_messages_key(inbox_id, contact_id)
            self.redis_client.delete(new_msgs_key)
            return True
        except Exception as e:
            logger.error(f"Error clearing new messages flag: {e}")
            return False

# Global instance
redis_manager = RedisContextManager()