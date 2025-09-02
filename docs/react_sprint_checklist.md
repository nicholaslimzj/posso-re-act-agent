# ReAct School Chatbot Sprint Plan

## Hour 1: Foundation & FAQ Tool (60 mins)

### Docker Development Environment Setup (15 mins)
- [ ] Create `docker-compose.yml` with Redis and app services
- [ ] Create `Dockerfile` for Python app
- [ ] Create `.env` file for environment variables
- [ ] Basic folder structure: `/tools`, `/agents`, `/context`, `/config`, `/data`
- [ ] Test Docker environment: `docker-compose up`

### Dependencies & Configuration (10 mins)
- [ ] Create `requirements.txt`:
  - `langgraph`, `litellm`, `redis`, `faiss-cpu`, `openai`, `pydantic`
  - `python-dotenv`, `loguru`
- [ ] Create `config/settings.py` for environment management
- [ ] Test Redis connection from container

### Context Models (20 mins)
- [ ] Create `context/models.py` with Pydantic models:
  - `PersistentContext` (Chatwoot fields)
  - `RuntimeContext` (session data)  
  - `ActiveTaskContext` (Redis state)
- [ ] Create `context/redis_helpers.py`: `get_context()`, `save_context()`
- [ ] Test context loading/saving

### FAQ Tool Implementation (15 mins)
- [ ] Extract FAQ text from PDF into `data/posso_faq.txt`
- [ ] Build `tools/faq_tool.py`:
  - Text splitting with RecursiveCharacterTextSplitter
  - FAISS vector store with OpenAI embeddings
  - `get_faq_answer(question: str)` function
- [ ] Test FAQ tool: "What makes Posso different?"

## Hour 2: Basic ReAct Loop (60 mins)

### LangGraph ReAct Agent (35 mins)
- [ ] Create `agents/react_agent.py`:
  - Basic ReAct workflow with LangGraph
  - Connect LiteLLM with GPT-4o-mini
  - Register FAQ tool with proper schema
- [ ] Create `main.py` for testing agent interactions
- [ ] Test simple flow: Question → Thought → FAQ Tool → Response
- [ ] Debug and fix tool calling issues

### Context Integration (25 mins)
- [ ] Load context at session start (create mock Chatwoot data)
- [ ] Save reasoning history to Redis after each cycle
- [ ] Implement basic session lifecycle management
- [ ] Test context persistence across multiple messages
- [ ] Basic session cleanup with TTL

## Hour 3: Advanced ReAct Features (60 mins)

### Message Queuing System (20 mins)
- [ ] Implement Redis session locking mechanism
- [ ] Create `new_messages:{school_id}_{contact_id}` flag system
- [ ] Build message queuing for concurrent requests
- [ ] Test concurrent message handling

### Context Update Tool (20 mins)
- [ ] Build `tools/context_tool.py`:
  - `update_context(field, new_value, reason)` function
  - Update Redis active context
  - Prepare Chatwoot sync data
- [ ] Register tool with ReAct agent
- [ ] Test correction flow: "Actually my name is Jon, not John"

### Unread Messages Tool (20 mins)
- [ ] Build `check_unread_messages()` tool
- [ ] Implement end-of-cycle message processing
- [ ] Test complex flow: booking + curriculum question + name correction
- [ ] Debug multi-step ReAct reasoning

## Docker Compose Configuration

### `docker-compose.yml`
```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - LANGCHAIN_TRACING_V2=${LANGCHAIN_TRACING_V2}
      - LANGCHAIN_API_KEY=${LANGCHAIN_API_KEY}
    volumes:
      - .:/app
      - ./data:/app/data
    depends_on:
      - redis
    command: python main.py

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes

volumes:
  redis_data:
```

### `Dockerfile`
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

### `.env`
```env
OPENAI_API_KEY=your_openai_key_here
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langchain_key_here
REDIS_URL=redis://localhost:6379
```

## Success Criteria by Hour 3

✅ **Docker environment running smoothly**  
✅ **Working ReAct agent with context memory**  
✅ **FAQ answering with real Posso school data**  
✅ **Natural conversation flow with topic switching**  
✅ **Message queuing for concurrent requests**  
✅ **Context corrections mid-conversation**  
✅ **Redis persistence and session management**  

## Ready for Hours 4-6: Real Booking Tools! 🚀

**Next Phase:** Implement `check_availability()`, `book_tour()`, `request_callback()` tools with mock Pipedrive APIs, then add real integrations.