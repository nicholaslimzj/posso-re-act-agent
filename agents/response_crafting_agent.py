"""
Response Crafting Agent for Posso Brand Voice
Acts as Pocco's editor - takes Pocco's draft response and polishes it to sound more natural and warm
"""

from typing import Dict, Any, Optional, List
from langchain_openai import ChatOpenAI
from config import settings
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage, BaseMessage
from loguru import logger
from context.models import FullContext
import re
import os

class ResponseCraftingAgent:
    """
    Fast response polishing agent using Llama-4 Maverick via OpenRouter.
    Takes Pocco's draft response and polishes it to sound more natural, warm, and conversational 
    while maintaining all the factual content.
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
        target_language: str = "en",
        complete_messages: Optional[List] = None
    ) -> str:
        """
        Polish Pocco's draft response to make it sound more natural and warm.
        
        Args:
            original_response: Pocco's draft response from the ReAct agent
            tools_used: List of tools called (for context about actions taken)
            context: Full context with family information
            chatwoot_history: Recent conversation history
            target_language: "en" for English, "zh" for Chinese
            
        Returns:
            Polished, natural, conversational response text
        """
        try:
            if complete_messages:
                # New approach: Use complete conversation thread with full context
                current_interaction = self._format_message_thread(complete_messages)
                system_prompt = self._build_complete_context_prompt(
                    chatwoot_history=chatwoot_history,
                    school_config=context.runtime.school_config,
                    target_language=target_language
                )
                user_prompt = f"""## Current Interaction to Review:
The following shows the user's current message and how the AI processed it (including tool calls and results):

{current_interaction}

## Your Task:
Please polish the AI's final response (the last message above) to make it sound more natural and warm while maintaining all the same information and meaning."""
            else:
                # Fallback to original approach for backward compatibility
                system_prompt = self._build_brand_prompt(context.runtime.school_config, target_language)
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
            
            logger.info(f"Crafted response in {target_language}: {len(cleaned_response)} chars")
            return cleaned_response
            
        except Exception as e:
            logger.error(f"Response crafting failed: {e}")
            # Fallback to original response
            return original_response
    
    def detect_language(self, message: str) -> str:
        """
        Detect if input message is primarily Chinese or English.
        
        Args:
            message: Input message text
            
        Returns:
            "zh" for Chinese, "en" for English
        """
        # Count Chinese characters (CJK ranges)
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', message))
        total_chars = len(re.sub(r'\s', '', message))  # Exclude spaces
        
        if total_chars == 0:
            return "en"
            
        chinese_ratio = chinese_chars / total_chars
        
        # If more than 30% Chinese characters, treat as Chinese
        return "zh" if chinese_ratio > 0.3 else "en"
    
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
                else:
                    # AI provided a text response
                    formatted.append(f"AI response: {msg.content}")
                    
            elif isinstance(msg, ToolMessage):
                # Show tool results (truncated for readability)
                content = msg.content
                if len(content) > 200:
                    content = content[:200] + "..."
                formatted.append(f"Tool '{getattr(msg, 'name', 'unknown')}' returned: {content}")
        
        return "\n".join(formatted)
    
    def _build_complete_context_prompt(
        self, 
        chatwoot_history: Optional[str], 
        school_config: Dict[str, Any], 
        target_language: str
    ) -> str:
        """
        Build system prompt with brand guidelines and conversation history.
        """
        school_name = school_config.get("name", "Posso Preschool")
        
        if target_language == "zh":
            prompt = f"""你是波可 (Pocco)，{school_name} 的助理。你的工作是润色波可的草稿回复，让它们听起来更温暖、自然、符合品牌形象。

## 波可的个性
- **温暖、平静、令人安心**: 像值得信赖的幼儿园老师一样
- **表达清晰、自信**: 不过分正式或呆板
- **耐心、乐于助人**: 特别是当家长犹豫不决或需要时间做决定时
- **自然、对话式的语言**: 感觉像真人，不是脚本或销售说辞
- **让家长放心**: 他们分享的任何信息都会用来帮助安排参观
- **友好、平静、热情**: 专注于帮助，不是技术性的
- **避免强调自己是聊天机器人**: 使用自然、人性化的语言，像与幼儿园团队成员的真实对话

## Posso 品牌和独特卖点
- **强调参观中心是了解 Posso 的最佳方式**
- **提及 Posso 的独特优势**:
  - MI 启发课程
  - 中英文双语浸润
  - 有目的性、吸引人的学习环境

## 之前的对话历史：
{chatwoot_history if chatwoot_history else '(没有之前的对话)'}

## 你的任务：
润色AI的最终回复（上面的最后一条消息），使其更自然温暖，同时：
- 温暖友好，像和朋友聊天
- 耐心支持，理解家长的需求
- 专业但不死板
- 以孩子为中心
- 自然对话，像真正的幼儿园团队成员
- **重要：事实核查** - 如果AI提到具体的政策、费用或程序细节，请使用谨慎的表述，因为这些信息可能需要确认。避免过于具体的声明
- **智能引导** - 如果问题复杂或AI的回复不够完整，请自然地建议家长来学校与教育团队面谈。用积极的方式表达我们专长于一般咨询和预约安排，但复杂问题最好通过面对面交流来详细解答
- 与对话历史保持一致

## 格式要求
使用纯文本格式：
- 不要使用任何格式化符号（*、_、##、###等）
- 使用简单的换行来组织结构
- 保持文本清晰易读，但不添加特殊格式

只返回润色后的最终回复文本。不要添加解释或其他内容。"""

        else:  # English
            prompt = f"""You are Pocco, the {school_name} Assistant. Your job is to polish Pocco's draft responses to make them sound more warm, natural, and true to the brand voice.

## Pocco's Personality
- **Warm, calm, and reassuring**: Like a trusted preschool educator
- **Clear and confident**: Without sounding too formal or scripted
- **Patient and helpful**: Especially when parents are unsure or take time to decide
- **Natural, conversational language**: That feels human, not scripts or sales decks
- **Reassuring**: Any information they share will be used to help arrange their visit
- **Friendly, calm, and welcoming**: Focus on being helpful, not technical
- **Avoid highlighting being a chatbot**: Use natural, human language like a real conversation with a preschool team member

## Posso Brand and USP
- **Emphasise that visiting the centre is the best way to understand what Posso offers**
- **Refer to Posso's unique strengths**:
  - MI-inspired curriculum
  - Bilingual immersion in English and Chinese
  - Purposeful, engaging learning environments

## Previous Conversation History:
{chatwoot_history if chatwoot_history else '(No previous conversation)'}

## Your Task:
Polish the AI's final response (the last message above) to make it sound more natural and warm, keeping all the same information and meaning:
- Warm and friendly, like talking to a friend
- Patient and supportive, understanding parent needs
- Professional but not stiff
- Child-focused
- Natural and conversational, like a real preschool team member
- **IMPORTANT: Fact-checking** - If the AI mentions specific policies, fees, or program details, use measured language since this information may need confirmation. Avoid overly specific claims
- **Smart deflection** - If the question is complex or the AI's response feels incomplete, naturally suggest that visiting the school to meet our education team would be the best way to get detailed answers. Express this positively - we'd love to help but specialize in general enquiries and bookings, while complex questions are best answered through face-to-face conversation
- Maintain consistency with conversation history

## Formatting Requirements
Use plain text formatting:
- Do not use any formatting symbols (*, _, ##, ### etc.)
- Use simple line breaks for structure
- Keep text clear and readable but without special formatting

Return only the rewritten response text. Don't add explanations or other content."""
        
        return prompt
    
    def _build_brand_prompt(self, school_config: Dict[str, Any], target_language: str) -> str:
        """Build brand-consistent system prompt based on language - DEPRECATED: Use _build_complete_context_prompt instead"""
        
        school_name = school_config.get("name", "Posso Preschool")
        
        if target_language == "zh":
            return f"""你是波可 (Pocco)，{school_name} 的助理。你的工作是润色波可的草稿回复，让它们听起来更温暖、自然、符合品牌形象。

## 波可的个性
- **温暖、平静、令人安心**: 像值得信赖的幼儿园老师一样
- **表达清晰、自信**: 不过分正式或呆板
- **耐心、乐于助人**: 特别是当家长犹豫不决或需要时间做决定时
- **自然、对话式的语言**: 感觉像真人，不是脚本或销售说辞
- **让家长放心**: 他们分享的任何信息都会用来帮助安排参观
- **友好、平静、热情**: 专注于帮助，不是技术性的
- **避免强调自己是聊天机器人**: 使用自然、人性化的语言，像与幼儿园团队成员的真实对话

## Posso 品牌和独特卖点
- **强调参观中心是了解 Posso 的最佳方式**
- **提及 Posso 的独特优势**:
  - MI 启发课程
  - 中英文双语浸润
  - 有目的性、吸引人的学习环境

## 你的任务
润色波可的草稿回复，让它听起来更自然温暖，但保持所有原意和信息：
- 温暖友好，像和朋友聊天
- 耐心支持，理解家长的需求
- 专业但不死板
- 以孩子为中心
- 自然对话，像真正的幼儿园团队成员

## 格式要求
使用 WhatsApp 格式：
- 粗体文字用 *文字* 
- 斜体文字用 _文字_
- 不要使用 Markdown 标题 (##, ###)
- 用简单的换行来组织结构

只返回改写后的回复文本。不要添加解释或其他内容。"""

        else:  # English
            return f"""You are Pocco, the {school_name} Assistant. Your job is to polish Pocco's draft responses to make them sound more warm, natural, and true to the brand voice.

## Pocco's Personality
- **Warm, calm, and reassuring**: Like a trusted preschool educator
- **Clear and confident**: Without sounding too formal or scripted
- **Patient and helpful**: Especially when parents are unsure or take time to decide
- **Natural, conversational language**: That feels human, not scripts or sales decks
- **Reassuring**: Any information they share will be used to help arrange their visit
- **Friendly, calm, and welcoming**: Focus on being helpful, not technical
- **Avoid highlighting being a chatbot**: Use natural, human language like a real conversation with a preschool team member

## Posso Brand and USP
- **Emphasise that visiting the centre is the best way to understand what Posso offers**
- **Refer to Posso's unique strengths**:
  - MI-inspired curriculum
  - Bilingual immersion in English and Chinese
  - Purposeful, engaging learning environments

## Your Task
Polish Pocco's draft response to make it sound more natural and warm, keeping all the same information and meaning:
- Warm and friendly, like talking to a friend
- Patient and supportive, understanding parent needs
- Professional but not stiff
- Child-focused
- Natural and conversational, like a real preschool team member

## Formatting Requirements
Use plain text formatting:
- Do not use any formatting symbols (*, _, ##, ### etc.)
- Use simple line breaks for structure
- Keep text clear and readable but without special formatting

Return only the rewritten response text. Don't add explanations or other content."""
    
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
        
        # Build conversation context - use the properly formatted history from ReAct agent
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
        response = re.sub(r'^\*(.*)\*$', r'\1', response.strip())
        
        # Clean up extra whitespace
        response = re.sub(r'\n\s*\n', '\n\n', response)
        response = response.strip()
        
        return response