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
from context import FullContext


class ReActState(TypedDict):
    """State for a single ReAct invocation"""
    messages: Annotated[List[BaseMessage], add]  # Messages are accumulated via addition
    final_response: Optional[str]  # The response to return
    tools_used: List[str]  # Track which tools were called
    reasoning_summary: str  # Human-readable summary
    cycle_count: int
    should_continue: bool


class ReActAgent:
    """Cleaner ReAct agent with proper separation of concerns"""
    
    def __init__(self):
        self.llm = self._setup_llm()
        self.tools = self._setup_tools()
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
    
    def _setup_tools(self) -> List[BaseTool]:
        """Setup available tools for the agent"""
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
    
    def _build_graph(self) -> StateGraph:
        """Build the ReAct reasoning graph"""
        
        def reasoning_node(state: ReActState) -> Dict[str, Any]:
            """Generate reasoning and decide on action"""
            try:
                messages = state["messages"]
                cycle_count = state["cycle_count"]
                
                
                # Get LLM response with tools
                llm_with_tools = self.llm.bind_tools(self.tools)
                response = llm_with_tools.invoke(messages)
                
                # Check if we should continue (has tool calls)
                has_tool_calls = bool(getattr(response, 'tool_calls', None))
                
                # Extract final response if no tool calls
                final_response = None if has_tool_calls else response.content
                
                # Update reasoning summary
                if has_tool_calls:
                    reasoning_summary = f"Cycle {cycle_count}: Calling tools..."
                else:
                    reasoning_summary = f"Cycle {cycle_count}: Generated final response"
                
                return {
                    "messages": [response],  # Only return the new message to append
                    "final_response": final_response,
                    "reasoning_summary": reasoning_summary,
                    "should_continue": has_tool_calls,
                    "cycle_count": cycle_count + 1
                }
                
            except Exception as e:
                logger.error(f"Error in reasoning node at cycle {state['cycle_count']}: {e}")
                return {
                    "messages": state["messages"] + [AIMessage(content="I encountered an error.")],
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
        chatwoot_history: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a user message through the ReAct agent
        
        Args:
            message: User's current message
            context: Full context (mainly for persistent data)
            chatwoot_history: Formatted conversation history from Chatwoot
            
        Returns:
            Dict with response and metadata
        """
        try:
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
                "should_continue": True
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
            "You help parents book school tours, answer questions, and provide information."
        ]
        
        # Add active task context if in progress
        if context.active.active_task_type:
            prompt_parts.append(f"\n## Current Task in Progress:")
            prompt_parts.append(f"Task: {context.active.active_task_type.value}")
            if context.active.active_task_status:
                prompt_parts.append(f"Status: {context.active.active_task_status.value}")
            if context.active.active_task_data:
                prompt_parts.append(f"Collected information: {context.active.active_task_data}")
        
        # Add persistent context if available
        if context.persistent.parent_preferred_name:
            prompt_parts.append(f"\nParent's name: {context.persistent.parent_preferred_name}")
        
        if context.persistent.child_name:
            prompt_parts.append(f"Child's name: {context.persistent.child_name}")
        
        if context.persistent.tour_scheduled_date:
            prompt_parts.append(f"Tour scheduled: {context.persistent.tour_scheduled_date} at {context.persistent.tour_scheduled_time}")
        
        # Add conversation history if available
        if chatwoot_history:
            prompt_parts.append(f"\n## Previous Conversation:\n{chatwoot_history}")
        
        return "\n".join(prompt_parts)