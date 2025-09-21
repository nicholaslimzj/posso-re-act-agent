"""
Response Crafting Agent for Posso Brand Voice
Acts as Pocco's communication expert - analyzes what the system accomplished and crafts warm responses
"""

from typing import Dict, Any, Optional, List
from langchain_openai import ChatOpenAI
from config import settings
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage, BaseMessage
from loguru import logger
from context.models import FullContext
from context import format_context_for_prompt, format_active_task_context
import re
import os

class ResponseCraftingAgent:
    """
    Response crafting agent for natural, warm communication.
    Analyzes what the ReAct system accomplished and crafts appropriate responses as Pocco.
    """

    def __init__(self):
        # Use configured model via OpenRouter for fast response crafting
        self.llm = ChatOpenAI(
            model=settings.RESPONSE_CRAFTING_MODEL,
            openai_api_base="https://openrouter.ai/api/v1",
            openai_api_key=os.getenv("OPENROUTER_API_KEY"),
            temperature=0.7,  # Slightly creative for natural flow
            max_tokens=400,   # Keep responses concise for WhatsApp
            timeout=15        # Fast response timeout
        )

    def craft_response(
        self,
        original_response: str,
        tools_used: List[str],
        context: FullContext,
        chatwoot_history: Optional[str] = None,
        complete_messages: Optional[List] = None,
        react_system_prompt: Optional[str] = None,
        user_original_message: Optional[str] = None
    ) -> str:
        """
        Craft a warm, natural response by analyzing what happened in the conversation.

        Args:
            original_response: Basic response from ReAct agent (may be ignored)
            tools_used: List of tools called (for context about actions taken)
            context: Full context with family information and current state
            chatwoot_history: Recent conversation history
            complete_messages: Complete conversation thread with tool calls and results
            react_system_prompt: The full system prompt used by ReAct agent (for context understanding)
            user_original_message: User's current message that triggered this interaction

        Returns:
            Crafted, natural, conversational response text
        """
        try:
            # Use intelligent analysis approach when we have full context
            if complete_messages and user_original_message:
                return self._craft_from_analysis(
                    user_message=user_original_message,
                    complete_messages=complete_messages,
                    context=context,
                    chatwoot_history=chatwoot_history,
                    original_response=original_response
                )
            else:
                # Fallback to simpler approach
                system_prompt = self._build_system_prompt(context.runtime.school_config)
                user_prompt = self._build_user_prompt(
                    original_response,
                    tools_used,
                    context,
                    chatwoot_history
                )

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            response = self.llm.invoke(messages)

            # Clean up any unwanted formatting
            cleaned_response = self._clean_response(response.content)

            logger.info(f"Crafted response: {len(cleaned_response)} chars")
            return cleaned_response

        except Exception as e:
            logger.error(f"Response crafting failed: {e}")
            # Fallback to original response
            return original_response

    def _format_message_thread(self, messages: List[BaseMessage]) -> str:
        """
        Format the complete message thread for response crafter to review.
        Shows user messages, AI responses, tool calls, and tool results.
        """
        formatted = []

        for msg in messages:
            if isinstance(msg, HumanMessage):
                formatted.append(f"User: {msg.content}")

            elif isinstance(msg, AIMessage):
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    # AI decided to use tools
                    tool_names = [tc.get('name', 'unknown') for tc in msg.tool_calls]
                    formatted.append(f"AI decided to use tools: {', '.join(tool_names)}")
                # Skip AI text responses to avoid biasing the Response Crafter

            elif isinstance(msg, ToolMessage):
                # Show tool results (full content)
                content = msg.content
                formatted.append(f"Tool '{getattr(msg, 'name', 'unknown')}' returned: {content}")

        return "\n".join(formatted)

    def _craft_from_analysis(
        self,
        user_message: str,
        complete_messages: List,
        context: FullContext,
        chatwoot_history: Optional[str],
        original_response: str
    ) -> str:
        """
        Craft response by analyzing complete conversation context instead of polishing ReAct output.
        Acts like an intelligent customer service rep reviewing what the system accomplished.
        """
        # Build comprehensive analysis prompt
        system_prompt = self._build_analysis_system_prompt(context)

        # Format all the context data for analysis
        conversation_analysis = self._format_message_thread(complete_messages)
        context_summary = self._extract_context_summary(context)

        user_prompt = f"""## User's Current Message:
{user_message}

## What Just Happened (Tool Calls & Results):
{conversation_analysis}

## Current Customer Context:
{context_summary}

## Previous Conversation History:
{chatwoot_history if chatwoot_history else '(No previous conversation)'}

## Your Task:
You are having an ongoing conversation with this parent. Write a natural, helpful response that moves the conversation forward based on what just happened and following your guidelines above."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

        response = self.llm.invoke(messages)
        return self._clean_response(response.content)

    def _build_analysis_system_prompt(self, context: FullContext) -> str:
        """Build system prompt for intelligent analysis approach"""
        school_name = context.runtime.school_config.get("name", "Posso Preschool")

        return f"""You are Pocco, the helpful assistant for {school_name}.

## What You CAN Do
1. Book school tours - Check availability and schedule tours for parents
2. Schedule callbacks - Arrange calls with our education team
3. Try to answer some questions - Using our FAQ knowledge base, though speaking with our education team is always best for detailed discussions
4. Collect family information - Gather details needed for tours/callbacks

## What You CANNOT Do
- Provide information not in our FAQ system or verified sources
- Answer complex policy questions without verified information
- Give medical, legal, or detailed educational advice

## DECISION FRAMEWORK
1. **Can I answer with tool information?** → Share it briefly and ask if they need anything else
2. **Do I lack the information they need?** → Only offer tours/callbacks if you haven't already suggested them in this conversation
3. **Are they ready to book something?** → Help them take the next step
4. **Have I already offered tours/callbacks?** → Don't ask again, focus on answering their current question or helping in other ways

## TOOL RESPONSE GUIDELINES
- **CRITICAL**: If any tool result contains a "response_hint" field, follow that guidance carefully
- Use tool results to craft natural responses that move the conversation forward

## CONVERSATION RULES
- Be concise but not overly restrictive - avoid rambling
- **CRITICAL**: Don't repeat information already shared in this conversation - check the Previous Conversation History first
- NEVER repeatedly ask about booking tours or scheduling callbacks if you've already offered in this conversation
- One main action per response
- Be direct about what you can/cannot help with
- Focus on moving them toward a solution
- **GREETING RULE**: Only introduce yourself if the Previous Conversation History shows "(No previous conversation)" - otherwise skip the greeting and go straight to helping. When introducing yourself, mention what you can help with: "Hi [name]! I'm Pocco from Posso Preschool. I can help you book a school tour, schedule a callback with our education team, or try to answer some questions about our school."
- **NO FUTURE PROMISES**: Never say you'll do something next or promise to follow up - only respond to what just happened
- If you need to refer to them by name in the natural flow of conversation, use their Preferred Name if available, otherwise use their WhatsApp name

## Response Guidelines
- Use ONLY information from tool responses - never guess
- Be concise and avoid rambling, but don't be overly restrictive
- Be direct about limitations
- Focus on what you CAN help with right now
- NEVER repeatedly offer tours/callbacks if you've already suggested them in this conversation
- **FIRST MESSAGE**: If no previous conversation history, introduce yourself as Pocco and briefly explain what you can help with
- **PERSONALIZATION**: Address them by their Preferred Name if available, otherwise use their WhatsApp name
- **NEVER promise future actions**: Don't say "I'll proceed to..." or "I will let you know if..." - you can only respond to what just happened

Write natural, helpful responses."""

    def _extract_context_summary(self, context: FullContext) -> str:
        """Extract key context information for analysis using shared formatter"""
        summary_parts = []

        # Use shared formatter to ensure identical context as ReAct agent
        summary_parts.extend(format_context_for_prompt(context))

        # Add active task context using shared formatter
        active_task_parts = format_active_task_context(context)
        if active_task_parts:
            summary_parts.append("\n")
            summary_parts.extend(active_task_parts)

        return "\n".join(summary_parts)

    def _build_system_prompt(self, school_config: Dict[str, Any]) -> str:
        """Build simple system prompt for fallback approach"""
        school_name = school_config.get("name", "Posso Preschool")

        return f"""You are Pocco, the {school_name} Assistant. Polish responses to make them warm, natural, and conversational.

## Your Task
Polish the response to enhance Pocco's warm, conversational tone while keeping all the same information.

## Pocco's Personality
- Warm, patient, and reassuring
- Professional but not stiff
- Like a trusted preschool educator
- Natural conversation, not robotic

Use plain text formatting with no special symbols.
Return only the rewritten response text."""

    def _build_user_prompt(
        self,
        original_response: str,
        tools_used: List[str],
        context: FullContext,
        chatwoot_history: Optional[str]
    ) -> str:
        """Build user prompt with context about what happened"""

        # Build context about the family
        family_info = []
        if context.persistent.parent_preferred_name:
            family_info.append(f"Parent: {context.persistent.parent_preferred_name}")
        if context.persistent.child_name:
            family_info.append(f"Child: {context.persistent.child_name}")
        if context.persistent.child_dob:
            family_info.append(f"Child DOB: {context.persistent.child_dob}")
        if context.persistent.preferred_enrollment_date:
            family_info.append(f"Enrollment: {context.persistent.preferred_enrollment_date}")

        family_context = "; ".join(family_info) if family_info else "New inquiry"

        # Build context about actions taken
        actions_context = "No tools used"
        if tools_used:
            action_descriptions = {
                "update_contact_info_tool": "collected/updated family information",
                "check_tour_availability_tool": "checked available tour slots",
                "book_tour_tool": "attempted to book a tour",
                "request_callback_tool": "processed callback request",
                "manage_tour_tool": "managed existing tour booking",
                "get_faq_answer_tool": "answered a question about the school"
            }
            actions = [action_descriptions.get(tool, f"used {tool}") for tool in tools_used]
            actions_context = "I just " + " and ".join(actions)

        # Build conversation context
        conv_context = ""
        if chatwoot_history:
            conv_context = f"\n**Recent conversation context:**\n{chatwoot_history}"

        prompt = f"""Please polish this response from Pocco to make it sound more natural and warm:

**Pocco's draft response:**
{original_response}

**Context about what just happened:**
{actions_context}

**What we know about the family:**
{family_context}
{conv_context}

Polish this response to enhance Pocco's warm, conversational tone while keeping all the same information. Make it flow more naturally and feel more personal and caring."""

        return prompt

    def _clean_response(self, response: str) -> str:
        """Clean up response formatting"""
        # Remove any unwanted quotes or formatting that might appear
        response = re.sub(r'^"(.*)"$', r'\1', response.strip())
        response = re.sub(r'^\*(.*?)\*$', r'\1', response.strip())

        # Clean up extra whitespace
        response = re.sub(r'\n\s*\n', '\n\n', response)
        response = response.strip()

        return response