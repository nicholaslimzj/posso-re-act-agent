from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger

from config import school_manager
from .models import FullContext, RuntimeContext, PersistentContext, ActiveTaskContext
from .redis_helpers import redis_manager


class ContextLoader:
    """Loads and manages context for ReAct sessions"""
    
    def __init__(self):
        self.school_manager = school_manager
        self.redis_manager = redis_manager
    
    def load_context(
        self,
        inbox_id: int,
        contact_id: str,
        conversation_id: str,
        whatsapp_profile: Optional[Dict[str, Any]] = None,
        chatwoot_additional_params: Optional[Dict[str, Any]] = None,
        recent_messages: Optional[list] = None
    ) -> FullContext:
        """
        Load complete context for a ReAct session
        
        Args:
            inbox_id: Chatwoot inbox ID (now the primary key)
            contact_id: Contact/customer identifier
            conversation_id: Chatwoot conversation ID
            whatsapp_profile: WhatsApp profile data
            chatwoot_additional_params: Persistent data from Chatwoot
            recent_messages: Recent conversation messages
        
        Returns:
            FullContext object ready for ReAct processing
        """
        try:
            # Get school_id from inbox_id using schools.json config
            school_id = self._get_school_id_from_inbox(inbox_id)
            
            # Load persistent context from Redis cache or Chatwoot
            persistent_context = self._load_persistent_context(inbox_id, contact_id, chatwoot_additional_params)
            
            # Load runtime context
            runtime_context = self._load_runtime_context(
                school_id=school_id,
                conversation_id=conversation_id,
                inbox_id=inbox_id,
                whatsapp_profile=whatsapp_profile,
                recent_messages=recent_messages
            )
            
            # Load active context from Redis or create new
            active_context = self._load_active_context(inbox_id, contact_id)
            
            return FullContext(
                persistent=persistent_context,
                runtime=runtime_context,
                active=active_context
            )
            
        except Exception as e:
            logger.error(f"Error loading context: {e}")
            # Return minimal context as fallback
            return self._create_minimal_context(inbox_id, conversation_id)
    
    def _load_persistent_context(
        self, 
        inbox_id: int, 
        contact_id: str, 
        chatwoot_data: Optional[Dict[str, Any]]
    ) -> PersistentContext:
        """Load persistent context from Redis cache or Chatwoot (exact backup)"""
        try:
            # First, try to get from Redis cache (30-day TTL)
            cached_context = self.redis_manager.get_persistent_context(inbox_id, contact_id)
            if cached_context:
                logger.debug(f"Loaded persistent context from Redis cache for {inbox_id}_{contact_id}")
                return cached_context
            
            # Not in cache, load from Chatwoot as exact backup
            if not chatwoot_data:
                logger.debug(f"No Chatwoot data available for {inbox_id}_{contact_id}, creating empty context")
                context = PersistentContext()
            else:
                # Parse Chatwoot data directly as PersistentContext
                try:
                    context = PersistentContext(**chatwoot_data)
                    logger.debug(f"Loaded persistent context from Chatwoot for {inbox_id}_{contact_id}")
                except Exception as parse_error:
                    logger.warning(f"Failed to parse Chatwoot data as PersistentContext: {parse_error}")
                    # Fallback to empty context if parsing fails
                    context = PersistentContext()
            
            # Cache in Redis for 30 days (exact backup)
            self.redis_manager.save_persistent_context(inbox_id, contact_id, context)
            
            return context
            
        except Exception as e:
            logger.error(f"Error loading persistent context: {e}")
            return PersistentContext()
    
    def _load_runtime_context(
        self,
        school_id: str,
        conversation_id: str,
        inbox_id: int,
        whatsapp_profile: Optional[Dict[str, Any]] = None,
        recent_messages: Optional[list] = None
    ) -> RuntimeContext:
        """Load runtime context with school configuration"""
        try:
            # Get school configuration
            school_config = self._build_school_config(school_id, inbox_id)
            
            # Extract WhatsApp profile data
            whatsapp_name = whatsapp_profile.get("name") if whatsapp_profile else None
            whatsapp_phone = whatsapp_profile.get("phone") if whatsapp_profile else None
            
            # Check if returning customer
            is_returning = bool(whatsapp_phone and self._check_returning_customer(whatsapp_phone))
            
            return RuntimeContext(
                conversation_id=conversation_id,
                inbox_id=inbox_id,
                school_id=school_id,
                whatsapp_name=whatsapp_name,
                whatsapp_phone=whatsapp_phone,
                messages=recent_messages or [],
                school_config=school_config,
                processing_started_at=datetime.utcnow().isoformat(),
                has_new_messages=False,
                is_returning_customer=is_returning
            )
            
        except Exception as e:
            logger.error(f"Error loading runtime context: {e}")
            return RuntimeContext(
                conversation_id=conversation_id,
                inbox_id=inbox_id,
                school_id=school_id
            )
    
    def _get_school_id_from_inbox(self, inbox_id: int) -> str:
        """Get school_id from inbox_id using schools.json config"""
        school_config = self.school_manager.get_school_config(str(inbox_id))
        if school_config:
            return school_config.get("school_id", "unknown")
        
        logger.warning(f"No school config found for inbox_id {inbox_id}")
        return "unknown"
    
    def _load_active_context(self, inbox_id: int, contact_id: str) -> ActiveTaskContext:
        """Load active context from Redis or create new"""
        try:
            # Try to get existing active context from Redis
            active_context = self.redis_manager.get_active_context(inbox_id, contact_id)
            
            if active_context:
                logger.info(f"Loaded existing active context for inbox_{inbox_id}_{contact_id}")
                return active_context
            
            # Create new active context
            logger.info(f"Creating new active context for inbox_{inbox_id}_{contact_id}")
            return ActiveTaskContext()
            
        except Exception as e:
            logger.error(f"Error loading active context: {e}")
            return ActiveTaskContext()
    
    def _build_school_config(self, school_id: str, inbox_id: int) -> Dict[str, Any]:
        """Build school configuration dictionary"""
        return {
            "school_name": self.school_manager.get_school_name(school_id),
            "branch_phone": self.school_manager.get_school_phone(school_id),
            "address": self.school_manager.get_school_address(school_id),
            "tour_slots": self.school_manager.get_tour_slots(school_id),
            "working_days": self.school_manager.get_working_days(school_id),
            "pipedrive_pipeline_id": self.school_manager.get_pipedrive_pipeline_id(school_id),
            "chatwoot_inbox_id": inbox_id,
            "other_branches": self.school_manager.get_other_branches()
        }
    
    def _check_returning_customer(self, phone: str) -> bool:
        """Check if customer has previous interactions (mock implementation)"""
        # TODO: Implement actual check against Chatwoot/Pipedrive
        # For now, return False as placeholder
        return False
    
    def _create_minimal_context(self, inbox_id: int, conversation_id: str) -> FullContext:
        """Create minimal context as fallback"""
        school_id = self._get_school_id_from_inbox(inbox_id)
        return FullContext(
            persistent=PersistentContext(),
            runtime=RuntimeContext(
                conversation_id=conversation_id,
                inbox_id=inbox_id,
                school_id=school_id
            ),
            active=ActiveTaskContext()
        )
    
    def save_context(self, inbox_id: int, contact_id: str, context: FullContext) -> bool:
        """Save active context to Redis"""
        try:
            return self.redis_manager.save_active_context(inbox_id, contact_id, context.active)
        except Exception as e:
            logger.error(f"Error saving context: {e}")
            return False
    
    def prepare_chatwoot_sync_data(self, context: FullContext) -> Dict[str, Any]:
        """Prepare persistent context data for Chatwoot sync (exact backup)"""
        try:
            # Convert the entire persistent context to dict, excluding None values
            sync_data = context.persistent.model_dump(exclude_none=True)
            
            # Convert enum values to strings for JSON serialization
            if "tour_status" in sync_data and sync_data["tour_status"]:
                sync_data["tour_status"] = sync_data["tour_status"].value if hasattr(sync_data["tour_status"], 'value') else str(sync_data["tour_status"])
            
            return sync_data
            
        except Exception as e:
            logger.error(f"Error preparing Chatwoot sync data: {e}")
            return {}

# Global instance
context_loader = ContextLoader()