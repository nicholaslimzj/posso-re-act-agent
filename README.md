# 🤖 ReAct School Chatbot

A conversational AI chatbot for school tours and enrollment built with LangGraph ReAct pattern, designed to handle natural conversations, context switching, and concurrent requests.

## 🚀 Features

✅ **ReAct Reasoning** - Think → Act → Observe cycle with LangGraph  
✅ **FAQ Knowledge Base** - FAISS vector search on school information  
✅ **Context Memory** - Persistent customer data across conversations  
✅ **Concurrent Requests** - Redis-based session locking and message queuing  
✅ **School Configuration** - Multi-school support via inbox_id mapping  
✅ **OpenRouter Integration** - Uses gpt-4o-mini via LiteLLM  
✅ **Chatwoot Ready** - Designed for webhook integration  

## 🏗️ Architecture

```
User Message → Chatwoot → Message Handler → ReAct Agent → Tools → Response
                              ↓
                         Redis Memory (Context + Locks)
                              ↓  
                         LangSmith (Tracing)
```

### Core Components

- **ReAct Agent** (`agents/react_agent.py`) - LangGraph reasoning workflow
- **Message Handler** (`message_handler.py`) - Orchestrates processing with concurrency
- **Context System** (`context/`) - Persistent, runtime, and active context management
- **Tools** (`tools/`) - FAQ search, context updates, message checking
- **Redis Manager** (`context/redis_helpers.py`) - Handles all Redis operations

## 📁 Project Structure

```
posso-re-act-agent/
├── agents/          # ReAct agent implementation
├── context/         # Context models and Redis management
├── tools/           # Agent tools (FAQ, context updates)
├── config/          # Settings and school configuration
├── data/            # FAQ content and knowledge base
├── docs/            # Documentation
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── main.py         # Entry point and testing
```

## 🔑 Redis Key Structure

All keys use `{inbox_id}_{contact_id}` prefix for Chatwoot alignment:

```
74274_12345:active_context      # Current ReAct session (1h TTL)
74274_12345:persistent_context  # Customer data (30d TTL)  
74274_12345:session_lock        # Concurrency control (5m TTL)
74274_12345:new_messages        # Message queue flag (5m TTL)
```

## 🔧 Configuration

### Environment Variables (.env)
```env
OPENROUTER_API_KEY=your_openrouter_key_here
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langchain_key_here
REDIS_URL=redis://localhost:6379
```

### School Configuration (config/schools.json)
Maps inbox_id to school settings:
```json
{
  "schools": {
    "74274": {
      "school_id": "74274",
      "name": "Posso Preschool Tampines",
      "pipedrive": { ... },
      "chatwoot": { ... },
      "tour_slots": ["10:00", "13:00", "15:00"]
    }
  }
}
```

## 🚀 Quick Start

1. **Setup Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

2. **Start Services**
   ```bash
   docker-compose up -d
   ```

3. **Test the System**
   ```bash
   docker-compose exec app python main.py
   ```

## 🧠 ReAct Flow Example

```
User: "What are your school hours?"

THOUGHT: User is asking about school operating hours. I should use the FAQ tool.

ACTION: get_faq_answer_tool("school hours")

OBSERVATION: Found answer about 8:00 AM to 3:00 PM regular hours, with extended care available.

RESPONSE: "Our regular school hours are 8:00 AM to 3:00 PM, Monday through Friday..."
```

## 🔄 Concurrency Handling

1. **Message arrives** → Check if session is locked
2. **If locked** → Queue message in Redis, return "processing" response
3. **If unlocked** → Acquire lock, process with ReAct, check queue, release lock

## 🛠️ Tools Available to Agent

- **`get_faq_answer_tool`** - Search knowledge base for school information
- **`update_context_aware`** - Update customer context (name corrections, etc.)
- **`check_unread_messages_aware`** - Check for messages that arrived during processing

## 📊 Context Types

### Persistent Context (30-day Redis cache)
- Parent/child information
- Tour bookings and callbacks  
- Pipedrive integration data

### Runtime Context (Session only)
- WhatsApp profile
- School configuration
- Recent conversation history

### Active Context (1-hour TTL)
- Current ReAct task state
- Reasoning history
- Queued messages

## 🎯 Webhook Integration

Ready for Chatwoot webhook with this payload:
```python
message_handler.process_chatwoot_message(
    inbox_id=74274,
    contact_id="contact_123",
    conversation_id="conv_456", 
    message_content="Hi, I want to book a tour",
    whatsapp_profile={"name": "John", "phone": "+65-9123-4567"},
    chatwoot_additional_params={...}  # Existing customer data
)
```

## 📈 Monitoring

- **LangSmith** - ReAct reasoning traces
- **Redis** - Session state and performance
- **Logs** - Structured logging with loguru

## 🔮 Next Phase: Booking Tools

The foundation is ready for:
- `check_availability()` - Tour slot checking
- `book_tour()` - Complete booking flow  
- `request_callback()` - Callback scheduling
- Pipedrive API integration

## 🧪 Testing

Run comprehensive tests:
```bash
python main.py
```

Tests cover:
- FAQ vector search
- Redis connectivity
- ReAct reasoning cycles
- Context management
- Concurrency handling