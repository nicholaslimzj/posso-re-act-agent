"""
Shared context formatting utilities for both ReAct and Response Crafting agents.
Ensures both agents see identical context information.
"""

from typing import List, Optional
from .models import FullContext


def format_context_for_prompt(context: FullContext) -> List[str]:
    """
    Format context information consistently for both ReAct and Response Crafter prompts.

    Args:
        context: Full context object with persistent, runtime, and active data

    Returns:
        List of formatted context strings ready to be joined into prompts
    """
    prompt_parts = []

    # Parent Information - exactly as shown in ReAct agent
    prompt_parts.append("**Parent Information:**")
    prompt_parts.append(f"- Preferred Name: {context.persistent.parent_preferred_name or 'Unknown'}")
    prompt_parts.append(f"- Preferred Email: {context.persistent.parent_preferred_email or 'Unknown'}")
    prompt_parts.append(f"- Preferred Phone: {context.persistent.parent_preferred_phone or 'Unknown'}")

    if context.runtime.whatsapp_name:
        prompt_parts.append(f"- WhatsApp Name: {context.runtime.whatsapp_name}")
    if context.runtime.whatsapp_phone:
        prompt_parts.append(f"- WhatsApp Phone: {context.runtime.whatsapp_phone}")

    # Child Information
    prompt_parts.append("\n**Child Information:**")
    prompt_parts.append(f"- Name: {context.persistent.child_name or 'Unknown'}")
    prompt_parts.append(f"- Date of Birth: {context.persistent.child_dob or 'Unknown'}")
    prompt_parts.append(f"- Preferred Enrollment: {context.persistent.preferred_enrollment_date or 'Unknown'}")

    # Pipedrive Deal ID
    if context.persistent.pipedrive_deal_id:
        prompt_parts.append(f"\n**Pipedrive Deal ID**: {context.persistent.pipedrive_deal_id}")

    # Tour Information
    if context.persistent.tour_scheduled_date:
        prompt_parts.append(f"\n**Tour Scheduled**: {context.persistent.tour_scheduled_date} at {context.persistent.tour_scheduled_time}")

    # School Configuration
    if context.runtime.school_config:
        config = context.runtime.school_config
        prompt_parts.append(f"\n**School Branch**: {config.get('school_name', 'Unknown')}")
        if config.get('address'):
            prompt_parts.append(f"**Location**: {config['address']}")

    return prompt_parts


def format_active_task_context(context: FullContext) -> List[str]:
    """
    Format active task context information.

    Args:
        context: Full context object

    Returns:
        List of formatted active task strings (may be empty)
    """
    prompt_parts = []

    if context.active.active_task_type:
        prompt_parts.append(f"**Active Task**: {context.active.active_task_type.value}")
        if context.active.active_task_status:
            prompt_parts.append(f"**Task Status**: {context.active.active_task_status.value}")

        # Add previous tool response context for intelligent continuation
        if context.active.active_task_data and "last_tool_response" in context.active.active_task_data:
            # Check if data is fresh (not older than 30 minutes)
            task_timestamp = context.active.active_task_data.get("timestamp")
            is_fresh = True
            if task_timestamp:
                from datetime import datetime, timedelta
                try:
                    task_time = datetime.fromisoformat(task_timestamp.replace('Z', '+00:00'))
                    now = datetime.utcnow()
                    is_fresh = (now - task_time) < timedelta(minutes=30)
                except (ValueError, TypeError):
                    pass  # If timestamp parsing fails, assume it's fresh

            if is_fresh:
                tool_response = context.active.active_task_data["last_tool_response"]
                prompt_parts.append("\n## Context from Previous Interaction:")
                prompt_parts.append(f"**Last tool used**: {tool_response.get('tool', 'unknown')}")
                prompt_parts.append(f"**Tool response**: {tool_response.get('status', 'unknown')}")
                prompt_parts.append(f"**Progress**: {tool_response.get('progress', 'unknown')}")

                if tool_response.get("prompt_for"):
                    if isinstance(tool_response["prompt_for"], list):
                        fields_needed = ", ".join(tool_response["prompt_for"])
                    else:
                        fields_needed = str(tool_response["prompt_for"])
                    prompt_parts.append(f"**Still need**: {fields_needed}")

                if tool_response.get("stage"):
                    prompt_parts.append(f"**Current stage**: {tool_response['stage']}")

                prompt_parts.append(f"**Next step**: {tool_response.get('next_action', 'Continue with the workflow')}")

                prompt_parts.append("\n**Consider the user's current message:**")
                prompt_parts.append("- Are they providing the requested information? → Continue with the workflow")
                prompt_parts.append("- Are they asking a related question while still interested? → Answer it briefly")
                prompt_parts.append("- Have they moved to a different topic entirely? → Handle the new request")

        elif context.active.active_task_data:
            prompt_parts.append(f"**Task Data**: {context.active.active_task_data}")

    return prompt_parts