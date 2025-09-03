"""
ReAct Agent V2 - Cleaner separation of concerns
"""
from typing import Dict, Any, List, Optional, TypedDict
from datetime import datetime
from uuid import uuid4

from langgraph.graph import StateGraph, END
from langchain_core.messages import RemoveMessage
from typing import Annotated
from operator import add
from langgraph.prebuilt import ToolNode
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import BaseTool, tool
from langchain_openai import ChatOpenAI
from loguru import logger

from config import settings
from context import FullContext, redis_manager


class ReActState(TypedDict):
    """State for a single ReAct invocation"""
    messages: Annotated[List[BaseMessage], add]  # Messages are accumulated via addition
    final_response: Optional[str]  # The response to return
    tools_used: List[str]  # Track which tools were called
    reasoning_summary: str  # Human-readable summary
    cycle_count: int
    should_continue: bool
    
    # Task tracking fields
    current_task: str  # What the agent is currently working on
    task_phase: str  # Current phase of the task (collecting_info, processing, etc.)
    expecting_input: Optional[str]  # Specific input the agent is waiting for
    
    # Concurrency control fields
    injection_count: int  # Track injection count locally (resets each session)
    inbox_id: Optional[int]  # Chatwoot inbox ID for Redis access
    contact_id: Optional[str]  # Contact ID for Redis access


class ReActAgent:
    """Cleaner ReAct agent with proper separation of concerns"""
    
    def __init__(self):
        self.llm = self._setup_llm()
        self.base_tools = self._setup_base_tools()
        self.tools = self.base_tools  # Will be updated with context-aware tools
        self.graph = self._build_graph()
    
    def _setup_llm(self) -> ChatOpenAI:
        """Setup ChatOpenAI with OpenRouter"""
        return ChatOpenAI(
            model=settings.MODEL_NAME,
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            temperature=0.1,
            max_tokens=1000
        )
    
    def _setup_base_tools(self) -> List[BaseTool]:
        """Setup base tools that don't need context"""
        from tools import get_faq_answer
        
        @tool
        def get_faq_answer_tool(question: str) -> dict:
            """
            Retrieve FAQ answer for school/tour related questions.
            Args:
                question: The user's question about the school
            Returns:
                {"answer": "...", "related_topics": [...]} or {"status": "no_match"}
            """
            return get_faq_answer(question)
        
        return [get_faq_answer_tool]
    
    def _create_context_aware_tools(self, inbox_id: int, contact_id: str) -> List[BaseTool]:
        """Create tools that have access to inbox_id and contact_id"""
        from tools.context_tools import (
            update_parent_details as _update_parent,
            update_child_details as _update_child,
            track_new_child as _track_new
        )
        
        @tool
        def update_parent_details(
            parent_preferred_name: Optional[str] = None,
            parent_preferred_email: Optional[str] = None,
            parent_preferred_phone: Optional[str] = None
        ) -> dict:
            """
            Update parent's preferred contact details when they provide corrections.
            Args:
                parent_preferred_name: Parent's preferred name
                parent_preferred_email: Parent's preferred email  
                parent_preferred_phone: Parent's preferred phone
            Returns:
                {"status": "updated", "updated_fields": {...}}
            """
            return _update_parent(
                inbox_id, contact_id,
                parent_preferred_name=parent_preferred_name,
                parent_preferred_email=parent_preferred_email,
                parent_preferred_phone=parent_preferred_phone
            )
        
        @tool
        def update_child_details(
            child_name: Optional[str] = None,
            child_dob: Optional[str] = None,
            child_age: Optional[int] = None,
            preferred_enrollment_date: Optional[str] = None
        ) -> dict:
            """
            Update current child's details (same child, just corrections/additions).
            Args:
                child_name: Child's name
                child_dob: Date of birth (YYYY-MM-DD format)
                child_age: Age in years (auto-calculated if DOB provided)
                preferred_enrollment_date: Preferred enrollment date (YYYY-MM-DD)
            Returns:
                {"status": "updated", "updated_fields": {...}}
            """
            return _update_child(
                inbox_id, contact_id,
                child_name=child_name,
                child_dob=child_dob,
                child_age=child_age,
                preferred_enrollment_date=preferred_enrollment_date
            )
        
        @tool
        def track_new_child(
            child_name: str,
            child_dob: Optional[str] = None,
            child_age: Optional[int] = None,
            preferred_enrollment_date: Optional[str] = None
        ) -> dict:
            """
            Switch to tracking a DIFFERENT child. WARNING: Resets all unspecified fields and creates new Pipedrive deal.
            Use ONLY when parent explicitly mentions a different child.
            Args:
                child_name: New child's name (required)
                child_dob: New child's date of birth (YYYY-MM-DD)
                child_age: New child's age in years
                preferred_enrollment_date: Preferred enrollment date (YYYY-MM-DD)
            Returns:
                {"status": "switched", "previous_child": {...}, "new_child": {...}, "deal_reset": True}
            """
            return _track_new(
                inbox_id, contact_id,
                child_name=child_name,
                child_dob=child_dob,
                child_age=child_age,
                preferred_enrollment_date=preferred_enrollment_date
            )
        
        return [update_parent_details, update_child_details, track_new_child]
    
    def _build_graph(self) -> StateGraph:
        """Build the ReAct reasoning graph"""
        
        def reasoning_node(state: ReActState) -> Dict[str, Any]:
            """Generate reasoning and decide on action"""
            try:
                messages = state["messages"]
                cycle_count = state["cycle_count"]
                injection_count = state.get("injection_count", 0)
                inbox_id = state.get("inbox_id")
                contact_id = state.get("contact_id")
                
                # List to collect new messages to inject
                messages_to_inject = []
                
                # Check for new messages and inject them (max 2 times to prevent loops)
                if inbox_id and contact_id and injection_count < 2:
                    if redis_manager.check_new_messages(inbox_id, contact_id):
                        # Get active context for queued messages
                        active_context = redis_manager.get_active_context(inbox_id, contact_id)
                        if active_context and active_context.queued_messages:
                                # Build injection message with task context
                                current_task = state.get("current_task", "Processing your request")
                                task_phase = state.get("task_phase", "analyzing")
                                
                                injection_msg = f"[New messages received while: {current_task}]\n"
                                injection_msg += f"Current phase: {task_phase}\n"
                                injection_msg += "Messages:"
                                
                                for queued_msg in active_context.queued_messages:
                                    injection_msg += f"\n• {queued_msg.content}"
                                
                                # Add to messages to inject
                                messages_to_inject.append(SystemMessage(content=injection_msg))
                                
                                # Log before clearing
                                num_injected = len(active_context.queued_messages)
                                
                                # Clear the processed messages from queue
                                active_context.queued_messages = []
                                redis_manager.save_active_context(inbox_id, contact_id, active_context)
                                
                                # Clear the new messages flag
                                redis_manager.clear_new_messages_flag(inbox_id, contact_id)
                                
                                # Increment injection count locally
                                injection_count += 1
                                
                                logger.info(f"Injected {num_injected} queued messages (injection #{injection_count})")
                
                # Combine original messages with any injected messages
                all_messages = messages + messages_to_inject
                
                # Get LLM response with tools
                llm_with_tools = self.llm.bind_tools(self.tools)
                response = llm_with_tools.invoke(all_messages)
                
                # Check if we should continue (has tool calls)
                has_tool_calls = bool(getattr(response, 'tool_calls', None))
                
                # Extract final response if no tool calls
                final_response = None if has_tool_calls else response.content
                
                # Update reasoning summary
                if has_tool_calls:
                    reasoning_summary = f"Cycle {cycle_count}: Calling tools..."
                else:
                    reasoning_summary = f"Cycle {cycle_count}: Generated final response"
                
                # Return injected messages AND the LLM response
                new_messages = messages_to_inject + [response]
                
                return {
                    "messages": new_messages,  # Return all new messages to append
                    "final_response": final_response,
                    "reasoning_summary": reasoning_summary,
                    "should_continue": has_tool_calls,
                    "cycle_count": cycle_count + 1,
                    "injection_count": injection_count  # Pass along the updated count
                }
                
            except Exception as e:
                logger.error(f"Error in reasoning node at cycle {state['cycle_count']}: {e}")
                return {
                    "messages": [AIMessage(content="I encountered an error.")],
                    "final_response": "I encountered an error processing your request.",
                    "should_continue": False,
                    "cycle_count": state["cycle_count"] + 1
                }
        
        def should_continue_func(state: ReActState) -> str:
            """Decide whether to continue with tools or end"""
            if state["should_continue"] and state["cycle_count"] < settings.MAX_REASONING_CYCLES:
                return "tools"
            return END
        
        def track_tools_node(state: ReActState) -> Dict[str, Any]:
            """Track which tools were used"""
            messages = state["messages"]
            tools_used = state.get("tools_used", [])
            
            
            # Check for tool calls in recent messages
            for msg in messages[-3:]:  # Check last 3 messages
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_name = tc.get('name', 'unknown')
                        if tool_name not in tools_used:
                            tools_used.append(tool_name)
            
            return {"tools_used": tools_used}
        
        # Build the graph
        workflow = StateGraph(ReActState)
        
        # Add nodes
        workflow.add_node("reasoning", reasoning_node)
        workflow.add_node("tools", ToolNode(self.tools))
        workflow.add_node("track_tools", track_tools_node)
        
        # Define edges
        workflow.set_entry_point("reasoning")
        workflow.add_conditional_edges("reasoning", should_continue_func)
        workflow.add_edge("tools", "track_tools")
        workflow.add_edge("track_tools", "reasoning")
        
        return workflow.compile()
    
    def process_message(
        self,
        message: str,
        context: FullContext,
        inbox_id: Optional[int] = None,
        contact_id: Optional[str] = None,
        chatwoot_history: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a user message through the ReAct agent
        
        Args:
            message: User's current message
            context: Full context (mainly for persistent data)
            inbox_id: Chatwoot inbox ID for Redis access
            contact_id: Contact ID for Redis access
            chatwoot_history: Formatted conversation history from Chatwoot
            
        Returns:
            Dict with response and metadata
        """
        try:
            # Update tools with context-aware versions if we have inbox_id and contact_id
            if inbox_id and contact_id:
                context_tools = self._create_context_aware_tools(inbox_id, contact_id)
                self.tools = self.base_tools + context_tools
                # Rebuild graph with updated tools
                self.graph = self._build_graph()
            else:
                self.tools = self.base_tools
            
            # Build context-aware system prompt
            system_prompt = self._build_system_prompt(context, chatwoot_history)
            
            # Initialize state with fresh message thread
            initial_state: ReActState = {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=message)
                ],
                "final_response": None,
                "tools_used": [],
                "reasoning_summary": "Starting reasoning...",
                "cycle_count": 1,
                "should_continue": True,
                # Task tracking
                "current_task": "Processing user request",
                "task_phase": "analyzing",
                "expecting_input": None,
                # Concurrency control
                "injection_count": 0,
                "inbox_id": inbox_id,
                "contact_id": contact_id
            }
            
            # Run the ReAct graph
            final_state = self.graph.invoke(initial_state)
            
            # Extract results
            response = final_state.get("final_response", "I couldn't generate a response.")
            
            # Build reasoning summary for Redis (simplified)
            reasoning_summary = {
                "cycles": final_state["cycle_count"] - 1,
                "tools_used": final_state["tools_used"],
                "summary": final_state["reasoning_summary"]
            }
            
            return {
                "response": response,
                "reasoning_summary": reasoning_summary,
                "tools_used": final_state["tools_used"],
                "cycles_count": final_state["cycle_count"] - 1,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return {
                "response": "I'm sorry, I encountered an error processing your message.",
                "reasoning_summary": {"error": str(e)},
                "tools_used": [],
                "cycles_count": 0,
                "success": False
            }
    
    def _build_system_prompt(self, context: FullContext, chatwoot_history: Optional[str]) -> str:
        """Build system prompt with context"""
        prompt_parts = [
            "You are a helpful assistant for Posso International Academy.",
            "You help parents book school tours, answer questions about the school, and assist with enrollment.",
            "",
            "## Available Tools:",
            "1. **get_faq_answer_tool**: Use this FIRST for any questions about:",
            "   - School programs, curriculum, or educational approach",
            "   - Fees, tuition, or costs",
            "   - Tour availability or scheduling",
            "   - Location, facilities, or general information",
            "   - Always check FAQ before providing general information",
            "",
            "2. **update_parent_details**: Use when parent provides their contact preferences:",
            "   - Preferred name (different from WhatsApp name)",
            "   - Preferred email for communications",
            "   - Preferred phone for callbacks",
            "   - Do NOT automatically use WhatsApp profile as preferred details",
            "",
            "3. **update_child_details**: Use when correcting/adding info for SAME child:",
            "   - Fixing typos in child's name",
            "   - Updating date of birth",
            "   - Adding missing information",
            "   - Changing preferred enrollment date",
            "",
            "4. **track_new_child**: Use ONLY when parent switches to DIFFERENT child:",
            "   - Parent says 'instead of [previous child]'",
            "   - Parent mentions a different child by name",
            "   - WARNING: This resets all data and creates new Pipedrive deal",
            "   - Always confirm before using this tool",
            "",
            "## Important Guidelines:",
            "- Always check FAQ first for factual questions",
            "- Update context when user provides corrections",
            "- Be careful to distinguish between updating same child vs switching children",
            "- If parent mentions multiple children, ask which one to focus on"
        ]
        
        # Add current context information
        prompt_parts.append("\n## Current Context:")
        
        # Add active task context if in progress
        if context.active.active_task_type:
            prompt_parts.append(f"**Active Task**: {context.active.active_task_type.value}")
            if context.active.active_task_status:
                prompt_parts.append(f"**Task Status**: {context.active.active_task_status.value}")
            if context.active.active_task_data:
                prompt_parts.append(f"**Collected Data**: {context.active.active_task_data}")
        
        # Add persistent context
        prompt_parts.append("\n**Parent Information:**")
        if context.persistent.parent_preferred_name:
            prompt_parts.append(f"- Preferred Name: {context.persistent.parent_preferred_name}")
        if context.persistent.parent_preferred_email:
            prompt_parts.append(f"- Preferred Email: {context.persistent.parent_preferred_email}")
        if context.persistent.parent_preferred_phone:
            prompt_parts.append(f"- Preferred Phone: {context.persistent.parent_preferred_phone}")
        
        if context.runtime.whatsapp_name:
            prompt_parts.append(f"- WhatsApp Name: {context.runtime.whatsapp_name}")
        if context.runtime.whatsapp_phone:
            prompt_parts.append(f"- WhatsApp Phone: {context.runtime.whatsapp_phone}")
        
        prompt_parts.append("\n**Child Information:**")
        if context.persistent.child_name:
            prompt_parts.append(f"- Name: {context.persistent.child_name}")
        if context.persistent.child_dob:
            prompt_parts.append(f"- Date of Birth: {context.persistent.child_dob}")
        if context.persistent.child_age:
            prompt_parts.append(f"- Age: {context.persistent.child_age} years")
        if context.persistent.preferred_enrollment_date:
            prompt_parts.append(f"- Preferred Enrollment: {context.persistent.preferred_enrollment_date}")
        
        if context.persistent.pipedrive_deal_id:
            prompt_parts.append(f"\n**Pipedrive Deal ID**: {context.persistent.pipedrive_deal_id}")
        
        # Add tour information if scheduled
        if context.persistent.tour_scheduled_date:
            prompt_parts.append(f"\n**Tour Scheduled**: {context.persistent.tour_scheduled_date} at {context.persistent.tour_scheduled_time}")
        
        # Add school configuration
        if context.runtime.school_config:
            config = context.runtime.school_config
            prompt_parts.append(f"\n**School Branch**: {config.get('school_name', 'Unknown')}")
            if config.get('address'):
                prompt_parts.append(f"**Location**: {config['address']}")
        
        # Add conversation history if available
        if chatwoot_history:
            prompt_parts.append(f"\n## Previous Conversation:\n{chatwoot_history}")
        
        return "\n".join(prompt_parts)