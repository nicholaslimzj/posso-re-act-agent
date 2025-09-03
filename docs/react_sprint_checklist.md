# ReAct School Chatbot Sprint Plan

## Hour 1: Foundation & FAQ Tool (60 mins)

### Docker Development Environment Setup (15 mins)
- [x] Create `docker-compose.yml` with Redis and app services
- [x] Create `Dockerfile` for Python app
- [x] Create `.env` file for environment variables
- [x] Basic folder structure: `/tools`, `/agents`, `/context`, `/config`, `/data`
- [x] Test Docker environment: `docker-compose up`

### Dependencies & Configuration (10 mins)
- [x] Create `requirements.txt`:
  - [x] `langgraph`, ~~`litellm`~~ (using `langchain-openai`), `redis`, ~~`faiss-cpu`~~ (using `sentence-transformers`), `openai`, `pydantic`
  - [x] `python-dotenv`, `loguru`
- [x] Create `config/settings.py` for environment management
- [x] Test Redis connection from container

### Context Models (20 mins)
- [x] Create `context/models.py` with Pydantic models:
  - [x] `PersistentContext` (Chatwoot fields)
  - [x] `RuntimeContext` (session data)  
  - [x] `ActiveTaskContext` (Redis state)
- [x] Create `context/redis_helpers.py`: `get_context()`, `save_context()`
- [x] Test context loading/saving

### FAQ Tool Implementation (15 mins)
- [x] Extract FAQ text from PDF into `data/posso_faq.txt`
- [x] Build `tools/faq_tool.py`:
  - [x] Text splitting with RecursiveCharacterTextSplitter
  - [x] ~~FAISS vector store with OpenAI embeddings~~ (using sentence-transformers for local embeddings)
  - [x] `get_faq_answer(question: str)` function
- [x] Test FAQ tool: "What makes Posso different?"

## Hour 2: Basic ReAct Loop (60 mins)

### LangGraph ReAct Agent (35 mins)
- [x] Create `agents/react_agent.py`:
  - [x] Basic ReAct workflow with LangGraph
  - [x] Connect ~~LiteLLM~~ LangChain with GPT-4o-mini via OpenRouter
  - [x] Register FAQ tool with proper schema
- [x] Create `main.py` for testing agent interactions
- [x] Test simple flow: Question → Thought → FAQ Tool → Response
- [x] Debug and fix tool calling issues (V2 architecture with message accumulation)

### Context Integration (25 mins)
- [x] Load context at session start (create mock Chatwoot data)
- [x] Save reasoning history to Redis after each cycle (simplified - not full history)
- [x] Implement basic session lifecycle management
- [x] Test context persistence across multiple messages
- [x] Basic session cleanup with TTL

## Hour 3: Advanced ReAct Features (60 mins)

### Message Queuing System (20 mins)
- [x] Implement Redis session locking mechanism
- [x] Create `new_messages:{school_id}_{contact_id}` flag system (using queue)
- [x] Build message queuing for concurrent requests
- [x] Test concurrent message handling

### Context Update Tool (20 mins)
- [x] Build `tools/context_tool.py`:
  - [x] `update_parent_details()` - Update parent's preferred contact info
  - [x] `update_child_details()` - Update same child's information
  - [x] `track_new_child()` - Switch to different child (resets Pipedrive deal!)
  - [x] Update Redis active context
  - [x] Prepare Chatwoot sync data
- [x] **Register tools with ReAct agent** ✅ DONE - Context-aware tools created
- [x] **Enhanced system prompt** to guide tool usage
- [ ] **Test correction flow: "Actually my name is Jon, not John"** (Ready to test)

### Unread Messages Tool (20 mins)
- [x] Build `check_unread_messages()` tool
- [x] Implement end-of-cycle message processing
- [ ] **Test complex flow: booking + curriculum question + name correction** ⚠️ NOT DONE (no booking tools yet)
- [x] Debug multi-step ReAct reasoning

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
✅ **Context corrections mid-conversation** (3 specialized tools implemented)  
✅ **Redis persistence and session management**  

## What We Actually Built (Beyond Plan)

### Improvements Over Original Plan:
- [x] **V2 ReAct Architecture** - Cleaner stateless design with message accumulation
- [x] **Local Embeddings** - Using sentence-transformers instead of OpenAI (free!)
- [x] **Better Context Separation** - Clear distinction between Graph state, Active, Runtime, and Persistent contexts
- [x] **OpenRouter Integration** - Instead of direct OpenAI
- [x] **Production Error Handling** - Graceful fallbacks throughout

### Additional Features Implemented:
- [x] **Three specialized context update tools** instead of one generic tool
- [x] **Message injection system** for handling concurrent messages in ReAct loop
- [x] **Web server with FastAPI** for Chatwoot webhook integration
- [x] **Enhanced system prompt** with tool usage guidelines
- [x] **Proper concurrency handling** with Redis locks and message queuing

### Still TODO:
- [x] **Implement booking tools** (`check_availability`, `book_tour`, `request_callback`) ✅ DONE
- [x] **Format Chatwoot conversation history** properly for agent ✅ DONE with timestamps
- [ ] **Test end-to-end correction flow** with real messages
- [x] **Add Pipedrive integration** for deal creation/updates ✅ DONE with custom fields

### Architecture Refactoring TODO:
- [ ] **Refactor school config access** - Pass school_config through parameters instead of modules directly accessing school_manager
  - Currently modules like `pipedrive.py` directly import and use school_manager
  - Should be passed as parameter from runtime context for consistency
  - Prevents potential config mismatches and improves testability

### Context Cleanup TODO:
- [ ] **Remove unused context fields** - Clean up context models to only include what's actually used
  - Remove fields that were planned but never implemented
  - Consolidate duplicate or overlapping fields
  
- [ ] **Refactor child_age field** - Remove child_age from PersistentContext
  - Age should be calculated dynamically from child_dob when needed
  - Storing age creates data staleness issues
  
- [ ] **Rename enrollment date field** - Change `preferred_enrollment_date` to `child_preferred_enrollment_date`
  - Makes it clear this is child-specific information
  - Consistent with other child fields naming pattern
  - This is the actual value we ask parents for (not calculated age)

## Ready for Hours 4-6: Real Booking Tools! 🚀

**Next Phase:** 
1. First register the context update tool
2. Implement `check_availability()`, `book_tour()`, `request_callback()` tools 
3. Add Chatwoot conversation history formatting
4. Real Pipedrive integration