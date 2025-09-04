"""
Response Crafting Agent for Posso Brand Voice
Acts as Pocco's editor - takes Pocco's draft response and polishes it to sound more natural and warm
"""

from typing import Dict, Any, Optional, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
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
        # Use Llama-4 Maverick via OpenRouter for fast response crafting
        self.llm = ChatOpenAI(
            model="meta-llama/llama-4-maverick",
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
        target_language: str = "en"
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
    
    def _build_brand_prompt(self, school_config: Dict[str, Any], target_language: str) -> str:
        """Build brand-consistent system prompt based on language"""
        
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
        
        # Build conversation context
        conv_context = ""
        if chatwoot_history:
            conv_context = f"\n**Recent conversation context:**\n{chatwoot_history[-300:]}"  # Last 300 chars
        
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