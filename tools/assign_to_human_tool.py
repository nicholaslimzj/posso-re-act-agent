"""
Assign to Human Tool - Assigns conversation to human agent in Chatwoot
"""

from typing import Dict, Any
from loguru import logger
from config import settings
from context.models import FullContext
from integrations.chatwoot import assign_conversation_to_agent




async def assign_to_human_tool(
    context: FullContext,
    reason: str = "User requested human assistance"
) -> Dict[str, Any]:
    """
    Assign the current conversation to a human agent in Chatwoot.
    This function is used for manual escalations where the bot determines it needs human help.
    Silent handovers are handled systematically elsewhere.

    Args:
        context: Full context with conversation and school information
        reason: Reason for the assignment (for logging/notes)

    Returns:
        Dict with status and details about the assignment
    """
    try:
        # Get school configuration for agent assignment
        school_config = context.runtime.school_config
        if not school_config:
            return {
                "status": "error",
                "message": "School configuration not found",
                "action_taken": "none"
            }

        # Get Chatwoot configuration
        chatwoot_config = school_config.get("chatwoot", {})
        inbox_id = chatwoot_config.get("inbox_id")
        agent_id = chatwoot_config.get("agent_id_for_handover")

        if not inbox_id or not agent_id:
            return {
                "status": "error",
                "message": "Chatwoot configuration missing (inbox_id or agent_id_for_handover)",
                "action_taken": "none"
            }

        # Get conversation ID from runtime context
        conversation_id = context.runtime.conversation_id
        if not conversation_id:
            return {
                "status": "error",
                "message": "No conversation ID found",
                "action_taken": "none"
            }

        # Assign conversation to human agent via Chatwoot integration
        result = await assign_conversation_to_agent(
            account_id=settings.CHATWOOT_ACCOUNT_ID,
            conversation_id=int(conversation_id),
            agent_id=agent_id,
            api_key=settings.CHATWOOT_API_KEY,
            reason=reason
        )

        if result.get("success"):
            logger.info(f"Successfully assigned conversation {conversation_id} to agent {agent_id}. Reason: {reason}")

            # Manual escalation - notify user
            return {
                "status": "success",
                "action_taken": "escalation",
                "agent_id": agent_id,
                "reason": reason,
                "response_hint": "Inform the user that you're connecting them with the education team who will be able to help them. DO NOT offer any further assistance from yourself as the conversation is being transferred to a human agent and you will no longer be responding. Do not repeat information that was already shared in this conversation."
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to assign conversation to human agent: {result.get('error', 'Unknown error')}",
                "action_taken": "none"
            }

    except Exception as e:
        logger.error(f"Error in assign_to_human_tool: {e}")
        return {
            "status": "error",
            "message": "System error occurred while trying to assign to human agent",
            "action_taken": "none",
            "error": str(e)
        }
