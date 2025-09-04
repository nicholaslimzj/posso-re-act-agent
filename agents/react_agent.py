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
from agents.response_crafting_agent import ResponseCraftingAgent


class ReActState(TypedDict):
    """State for a single ReAct invocation"""
    messages: Annotated[List[BaseMessage], add]  # Messages are accumulated via addition
    final_response: Optional[str]  # The response to return
    crafted_response: Optional[str]  # The polished response from ResponseCraftingAgent
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
    
    # Response crafting context
    context: Optional[FullContext]  # Full context for response crafting
    chatwoot_history: Optional[str]  # Conversation history
    original_message: Optional[str]  # Original user message for language detection


class ReActAgent:
    """Cleaner ReAct agent with proper separation of concerns"""
    
    def __init__(self):
        self.llm = self._setup_llm()
        self.base_tools = self._setup_base_tools()
        self.tools = self.base_tools  # Will be updated with context-aware tools
        self.response_crafter = ResponseCraftingAgent()
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
    
    def _create_context_aware_tools(self, context) -> List[BaseTool]:
        """Create tools that have access to the full context"""
        from tools.context_tools import update_contact_info
        from tools.check_tour_slots_tool import check_tour_slots
        from tools.book_tour_tool import book_or_reschedule_tour
        from tools.callback_tool import request_callback
        from tools.manage_tour_tool import manage_existing_tour
        
        @tool
        def update_contact_info_tool(
            update_type: str,
            fields: dict
        ) -> dict:
            """
            Update parent or child contact information.
            Args:
                update_type: Type of update - "parent", "child", or "new_child"
                  - "parent": Update parent's preferred contact details
                  - "child": Update current child's information (same child)
                  - "new_child": Switch to tracking a DIFFERENT child (WARNING: resets Pipedrive deal!)
                fields: Dictionary of fields to update
                  Parent fields: parent_preferred_name, parent_preferred_email, parent_preferred_phone
                  Child fields: child_name, child_dob, preferred_enrollment_date
            Returns:
                {"status": "updated", "update_type": ..., "updated_fields": {...}}
            """
            # Now uses pure function pattern - modifies context in-place
            return update_contact_info(
                context,
                update_type=update_type,
                fields=fields
            )
        
        @tool
        def check_tour_availability_tool(
            preferences: dict = None
        ) -> dict:
            """
            Check available tour slots based on preferences.
            Args:
                preferences: Optional dict with:
                  - date: Specific date (YYYY-MM-DD)
                  - day_of_week: Day name (Monday, Tuesday, etc.)
                  - time_preference: "morning" | "afternoon" | specific time (HH:MM)
                  - next_week: bool - if True, check next week instead of this week
            Returns:
                Dictionary with available slots organized by date
            """
            return check_tour_slots(context.runtime, preferences)
        
        @tool
        def book_tour_tool(
            tour_date: str,
            tour_time: str,
            action: str = "book"
        ) -> dict:
            """
            Book or reschedule a tour - intelligently handles data collection.
            This tool will guide you through collecting required information.
            Args:
                tour_date: Date in YYYY-MM-DD format
                tour_time: Time in HH:MM format (Singapore time) - e.g., "10:00", "13:00", "15:00"
                action: "book" for new booking (default) or "reschedule" for existing tour
            Returns:
                Either booking confirmation OR guidance on what information to collect next
            """
            # The tool now handles all the workflow logic internally
            result = book_or_reschedule_tour(
                context,
                action=action,
                tour_date=tour_date,
                tour_time=tour_time
            )
            
            # If the tool says we need info, help the LLM understand what to do
            if result.get("status") == "need_info":
                # Add LLM-friendly instructions
                if result.get("next_action") == "ask_user":
                    result["llm_instruction"] = f"Ask the user: {result.get('question', result.get('context_hint'))}"
                elif result.get("next_action") == "confirm_data":
                    result["llm_instruction"] = f"Confirm with user: {result.get('question')}"
                elif result.get("next_action") == "create_deal":
                    result["llm_instruction"] = "Call the create_pipedrive_deal tool first"
            
            return result
        
        @tool
        def request_callback_tool(
            callback_preference: str = "anytime",
            reason: str = None
        ) -> dict:
            """
            Request a callback from the school - intelligently handles data collection.
            This tool will guide you through collecting required information.
            Args:
                callback_preference: "morning", "afternoon", or "anytime" (default)
                reason: Optional reason for the callback
            Returns:
                Either callback confirmation OR guidance on what information to collect next
            """
            result = request_callback(
                context,
                callback_preference=callback_preference,
                reason=reason
            )
            
            # Add LLM instructions based on result
            if result.get("status") == "need_info":
                if result.get("next_action") == "ask_user":
                    result["llm_instruction"] = f"Ask the user for: {result.get('question')}"
            
            return result
        
        @tool
        def manage_tour_tool(
            action: str,
            new_date: str = None,
            new_time: str = None,
            reason: str = None
        ) -> dict:
            """
            Manage an existing tour booking - reschedule or cancel.
            Args:
                action: "reschedule" or "cancel"
                new_date: For reschedule - new date in YYYY-MM-DD format
                new_time: For reschedule - new time in HH:MM format (e.g., "10:00", "13:00")
                reason: For cancel - optional reason for cancellation
            Returns:
                Confirmation of the action taken
            """
            return manage_existing_tour(
                context,
                action=action,
                new_date=new_date,
                new_time=new_time,
                reason=reason
            )
        
        return [update_contact_info_tool, check_tour_availability_tool, book_tour_tool, request_callback_tool, manage_tour_tool]
    
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
            """Decide whether to continue with tools or craft response"""
            if state["should_continue"] and state["cycle_count"] < settings.MAX_REASONING_CYCLES:
                return "tools"
            return "response_crafting"
        
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
        
        def response_crafting_node(state: ReActState) -> Dict[str, Any]:
            """Craft the final response using ResponseCraftingAgent"""
            try:
                final_response = state.get("final_response", "")
                tools_used = state.get("tools_used", [])
                
                # Get context and history from state metadata (if available)
                # These would need to be passed through the graph invoke call
                context = state.get("context")
                chatwoot_history = state.get("chatwoot_history") 
                message = state.get("original_message", "")
                
                if context and final_response:
                    # Detect language from original message
                    target_language = self.response_crafter.detect_language(message)
                    
                    # Craft response
                    crafted_response = self.response_crafter.craft_response(
                        original_response=final_response,
                        tools_used=tools_used,
                        context=context,
                        chatwoot_history=chatwoot_history,
                        target_language=target_language
                    )
                    
                    logger.info(f"Response crafted successfully in {target_language}")
                    return {"crafted_response": crafted_response}
                else:
                    # Fallback to original response
                    logger.warning("Missing context for response crafting, using original response")
                    return {"crafted_response": final_response}
                    
            except Exception as e:
                logger.error(f"Error in response crafting: {e}")
                # Fallback to original response
                return {"crafted_response": state.get("final_response", "")}
        
        # Build the graph
        workflow = StateGraph(ReActState)
        
        # Add nodes
        workflow.add_node("reasoning", reasoning_node)
        workflow.add_node("tools", ToolNode(self.tools))
        workflow.add_node("track_tools", track_tools_node)
        workflow.add_node("response_crafting", response_crafting_node)
        
        # Define edges
        workflow.set_entry_point("reasoning")
        workflow.add_conditional_edges("reasoning", should_continue_func)
        workflow.add_edge("tools", "track_tools")
        workflow.add_edge("track_tools", "reasoning")
        workflow.add_edge("response_crafting", END)
        
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
            # Processing message with optional conversation history
            if chatwoot_history:
                logger.info(f"Processing with conversation history ({len(chatwoot_history)} chars)")
            
            # Update tools with context-aware versions if we have context
            if context:
                context_tools = self._create_context_aware_tools(context)
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
                "crafted_response": None,
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
                "contact_id": contact_id,
                # Response crafting context
                "context": context,
                "chatwoot_history": chatwoot_history,
                "original_message": message
            }
            
            # Run the ReAct graph
            final_state = self.graph.invoke(initial_state)
            
            # Extract results - prefer crafted response over final response
            response = final_state.get("crafted_response") or final_state.get("final_response", "I couldn't generate a response.")
            
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
        import pytz
        from datetime import datetime
        
        # Get current date in Singapore time
        singapore_tz = pytz.timezone('Asia/Singapore')
        current_date = datetime.now(singapore_tz)
        date_str = current_date.strftime("%A, %B %d, %Y")
        
        prompt_parts = [
            "You are Pocco, the Posso Assistant — a warm, professional representative of Posso International Academy.",
            "You help parents book school tours, answer questions about the school, and assist with enrollment.",
            f"Today's date is {date_str} (Singapore time).",
            "",
            "## Your Personality (Pocco):",
            "- Be warm, calm, and reassuring, like a trusted preschool educator",
            "- Speak clearly and confidently, without sounding too formal or scripted", 
            "- Stay patient and helpful, especially when parents are unsure or take time to decide",
            "- Use natural, conversational language that feels human",
            "- Focus on being helpful and supportive throughout the interaction",
            "",
            "## Available Tools:",
            "1. **get_faq_answer_tool**: Use this FIRST for any questions about:",
            "   - School programs, curriculum, or educational approach",
            "   - Fees, tuition, or costs",
            "   - Tour availability or scheduling",
            "   - Location, facilities, or general information",
            "   - Always check FAQ before providing general information",
            "",
            "2. **check_tour_availability**: Check available tour slots:",
            "   - Use when parent asks about tour availability or dates",
            "   - Can filter by day of week, morning/afternoon, specific dates",
            "   - Returns next 14 days of available slots",
            "   - Always call this before suggesting tour dates",
            "",
            "3. **book_tour**: Book or reschedule a tour:",
            "   - Use after parent confirms a specific date and time",
            "   - This tool intelligently guides you through data collection",
            "   - It will tell you what information is missing or needs confirmation",
            "   - Follow the tool's guidance on what to ask the user next",
            "   - The tool tracks progress (e.g., '2/4 required fields collected')",
            "   - Tour times are typically 10:00, 13:00, or 15:00",
            "",
            "4. **request_callback**: Request a callback from the school:",
            "   - Use when parent explicitly asks for a callback or to speak with someone",
            "   - This tool intelligently guides you through data collection (similar to booking)",
            "   - It will collect parent info, child info, then create callback request",
            "   - Specify callback_preference: 'morning', 'afternoon', or 'anytime'",
            "   - Creates a note in Pipedrive for the team to follow up",
            "",
            "5. **manage_tour**: Reschedule or cancel an existing tour:",
            "   - Use when parent wants to change or cancel their booked tour",
            "   - action='reschedule': Requires new_date and new_time",
            "   - action='cancel': Optional reason for cancellation",
            "   - Will update Pipedrive and add notes about the change",
            "",
            "6. **update_contact_info**: Update parent or child information:",
            "   - update_type='parent': Update parent's preferred contact details",
            "     * Preferred name, email, or phone (separate from WhatsApp)",
            "   - update_type='child': Update SAME child's information",
            "     * Fix typos, update DOB, add missing info",
            "   - update_type='new_child': Switch to DIFFERENT child",
            "     * WARNING: Resets Pipedrive deal! Use only when explicitly switching children",
            "     * Parent says 'instead of [previous child]' or mentions different child",
            "",
            "## Important Guidelines:",
            "- Always check FAQ first for factual questions",
            "- Check availability before suggesting tour dates",
            "- Update ANY 'Unknown' fields when user provides that information",
            "- Update context when user provides corrections or new information",
            "- Be careful to distinguish between updating same child vs switching children",
            "- If parent mentions multiple children, ask which one to focus on",
            "- When you see 'Unknown' for any field and the user mentions it, update immediately",
            "",
            "## Child Information Collection:",
            "- NEVER ask for or store child's age directly - it changes over time",
            "- Always collect child's Date of Birth (DOB) instead - this is permanent data",
            "- Also collect preferred enrollment date (when they want to start)",
            "- The system calculates the appropriate program level from DOB + enrollment date"
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
        
        # Add persistent context - ALWAYS show key fields
        prompt_parts.append("\n**Parent Information:**")
        prompt_parts.append(f"- Preferred Name: {context.persistent.parent_preferred_name or 'Unknown'}")
        prompt_parts.append(f"- Preferred Email: {context.persistent.parent_preferred_email or 'Unknown'}")
        prompt_parts.append(f"- Preferred Phone: {context.persistent.parent_preferred_phone or 'Unknown'}")
        
        if context.runtime.whatsapp_name:
            prompt_parts.append(f"- WhatsApp Name: {context.runtime.whatsapp_name}")
        if context.runtime.whatsapp_phone:
            prompt_parts.append(f"- WhatsApp Phone: {context.runtime.whatsapp_phone}")
        
        prompt_parts.append("\n**Child Information:**")
        prompt_parts.append(f"- Name: {context.persistent.child_name or 'Unknown'}")
        prompt_parts.append(f"- Date of Birth: {context.persistent.child_dob or 'Unknown'}")
        prompt_parts.append(f"- Preferred Enrollment: {context.persistent.preferred_enrollment_date or 'Unknown'}")
        
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
            # Adding conversation history to system prompt
            prompt_parts.append("\n## Previous Conversation:")
            prompt_parts.append(chatwoot_history)
            prompt_parts.append("---End of conversation history---")
            prompt_parts.append("\nNow respond to the user's current message.")
        else:
            # No conversation history available
            pass
        
        return "\n".join(prompt_parts)