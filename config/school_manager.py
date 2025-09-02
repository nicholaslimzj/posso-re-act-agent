import json
from typing import Dict, Any, Optional, List
from loguru import logger
from pathlib import Path

class SchoolManager:
    """Manages school-specific configuration and settings"""
    
    def __init__(self, config_file: str = "config/schools.json"):
        self.config_file = Path(config_file)
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load school configuration from JSON file"""
        try:
            if not self.config_file.exists():
                logger.error(f"School config file not found: {self.config_file}")
                return {"schools": {}}
            
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            
            logger.info(f"Loaded config for {len(config.get('schools', {}))} schools")
            return config
            
        except Exception as e:
            logger.error(f"Failed to load school config: {e}")
            return {"schools": {}}
    
    def get_school_config(self, school_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific school"""
        return self._config.get("schools", {}).get(school_id)
    
    def get_pipedrive_config(self, school_id: str) -> Optional[Dict[str, Any]]:
        """Get Pipedrive configuration for a school"""
        school_config = self.get_school_config(school_id)
        return school_config.get("pipedrive") if school_config else None
    
    def get_chatwoot_config(self, school_id: str) -> Optional[Dict[str, Any]]:
        """Get Chatwoot configuration for a school"""
        school_config = self.get_school_config(school_id)
        return school_config.get("chatwoot") if school_config else None
    
    def get_tour_slots(self, school_id: str) -> List[str]:
        """Get available tour time slots for a school"""
        school_config = self.get_school_config(school_id)
        return school_config.get("tour_slots", ["10:00", "14:00"]) if school_config else ["10:00", "14:00"]
    
    def get_working_days(self, school_id: str) -> List[int]:
        """Get working days for a school (1=Monday, 7=Sunday)"""
        school_config = self.get_school_config(school_id)
        return school_config.get("working_days", [1, 2, 3, 4, 5]) if school_config else [1, 2, 3, 4, 5]
    
    def get_school_name(self, school_id: str) -> str:
        """Get display name for a school"""
        school_config = self.get_school_config(school_id)
        return school_config.get("name", f"Posso {school_id.title()}") if school_config else f"Posso {school_id.title()}"
    
    def get_school_phone(self, school_id: str) -> Optional[str]:
        """Get phone number for a school"""
        school_config = self.get_school_config(school_id)
        return school_config.get("branch_phone") if school_config else None
    
    def get_school_address(self, school_id: str) -> Optional[str]:
        """Get address for a school"""
        school_config = self.get_school_config(school_id)
        return school_config.get("address") if school_config else None
    
    def get_all_school_ids(self) -> List[str]:
        """Get list of all configured school IDs"""
        return list(self._config.get("schools", {}).keys())
    
    def get_other_branches(self) -> Dict[str, Dict[str, str]]:
        """Get information about other branches (not main schools)"""
        return self._config.get("other_branches", {})
    
    def get_bot_agent_id(self) -> Optional[int]:
        """Get the bot agent ID for Chatwoot"""
        return self._config.get("bot", {}).get("agent_id")
    
    def is_valid_school(self, school_id: str) -> bool:
        """Check if school_id is valid and configured"""
        return school_id in self._config.get("schools", {})
    
    def get_pipedrive_custom_field(self, school_id: str, field_name: str) -> Optional[str]:
        """Get Pipedrive custom field ID for a specific field"""
        pipedrive_config = self.get_pipedrive_config(school_id)
        if not pipedrive_config:
            return None
        
        custom_fields = pipedrive_config.get("custom_fields", {})
        return custom_fields.get(field_name)
    
    def get_pipedrive_stage_id(self, school_id: str, stage_name: str) -> Optional[int]:
        """Get Pipedrive stage ID for a specific stage"""
        pipedrive_config = self.get_pipedrive_config(school_id)
        if not pipedrive_config:
            return None
        
        stages = pipedrive_config.get("stages", {})
        return stages.get(stage_name)
    
    def get_pipedrive_pipeline_id(self, school_id: str) -> Optional[int]:
        """Get Pipedrive pipeline ID for a school"""
        pipedrive_config = self.get_pipedrive_config(school_id)
        return pipedrive_config.get("pipeline_id") if pipedrive_config else None
    
    def get_activity_type(self, school_id: str, activity_name: str) -> Optional[str]:
        """Get Pipedrive activity type for a specific activity"""
        pipedrive_config = self.get_pipedrive_config(school_id)
        if not pipedrive_config:
            return None
        
        activity_types = pipedrive_config.get("activity_types", {})
        return activity_types.get(activity_name)
    
    def reload_config(self) -> bool:
        """Reload configuration from file"""
        try:
            self._config = self._load_config()
            return True
        except Exception as e:
            logger.error(f"Failed to reload school config: {e}")
            return False

# Global instance
school_manager = SchoolManager()