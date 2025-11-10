# LangGraph RAG Agent with Beanis & MCP Tools

Build intelligent AI agents with conversation memory, semantic search, and tool calling using LangGraph + Beanis + Redis.

## What This Example Shows

This example demonstrates TWO approaches to building production-ready RAG agents:

### 1. Basic RAG Agent (`agent.py`)
A straightforward RAG pipeline that always retrieves context:
- **Stores knowledge** in Redis using Beanis with vector embeddings
- **Orchestrates workflows** using LangGraph for complex agent logic
- **Maintains conversation history** across sessions
- **Always retrieves context** for every query (fixed pipeline)

### 2. Tool-Calling Agent (`agent_with_tools.py`) ⭐ RECOMMENDED
An intelligent agent using MCP (Model Context Protocol) tools that decides when to retrieve:
- **Smart retrieval** - Agent decides when to search the knowledge base
- **Memory management** - Store and retrieve custom agent state
- **Conversation-aware** - Optionally loads history when needed
- **Redis-backed memory** - Persistent key-value storage for agent memory
- **MCP server** (`mcp_server.py`) - Reusable tools for any LangGraph agent

## Architecture

### Tool-Calling Agent Architecture (Recommended)

```
User Query
    ↓
┌──────────────────────────────────────────┐
│         LangGraph with Tool Calling      │
│                                          │
│  ┌────────────────────────────────┐     │
│  │  Agent Node (LLM Reasoning)    │     │
│  │  - Analyze query               │     │
│  │  - Decide which tools to use   │     │
│  └──────────┬─────────────────────┘     │
│             ↓                            │
│  ┌────────────────────────────────┐     │
│  │  Tool Node (Execute Tools)     │     │
│  │                                │     │
│  │  Available MCP Tools:          │     │
│  │  • search_knowledge_base()     │     │
│  │  • get_conversation_history()  │     │
│  │  • store_memory(key, value)    │     │
│  │  • retrieve_memory(key)        │     │
│  └──────────┬─────────────────────┘     │
│             ↓                            │
│       (Loop back to Agent if needed)     │
│             ↓                            │
│    Final Response Generation             │
└──────────────────────────────────────────┘
    ↓
Response + Metadata

All tools interact with Redis via Beanis ODM
```

## Prerequisites

- Python 3.10+
- Redis (running on localhost:6379)
- OpenAI API key

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Start Redis

```bash
# Using docker-compose (recommended)
docker-compose up -d

# Or manually with docker
docker run -d -p 6379:6379 --name langgraph-redis --platform linux/amd64 redis/redis-stack:latest
```

**⚠️ Important for ARM Macs (M1/M2/M3)**: You MUST use the `--platform linux/amd64` flag or specify `platform: linux/amd64` in docker-compose. There's a known bug in Redis Stack ARM64 builds where the RediSearch module crashes when processing vector data using SVE2 instructions, causing vector indexes to be silently dropped. Using the x86 image under Rosetta emulation avoids this issue.

### 3. Set OpenAI API Key

```bash
export OPENAI_API_KEY='your-api-key-here'
```

### 4. Ingest Data

Load sample data from Hugging Face SQuAD dataset:

```bash
python ingest_data.py
```

This will:
- Load 100 examples from SQuAD dataset
- Generate embeddings using OpenAI
- Store in Redis with vector indexes

### 5. Run the Agent

#### Option A: Tool-Calling Agent (Recommended)

```bash
python test_tool_agent.py
```

This demonstrates the intelligent agent that:
- **Greets without tools** - Simple queries don't need retrieval
- **Searches when needed** - Factual questions trigger knowledge base search
- **Stores user preferences** - Agent remembers information in Redis
- **Uses conversation history** - Contextual follow-up questions
- **Combines tools** - Complex queries use multiple tools together

#### Option B: Basic RAG Agent

```bash
python main.py
```

The basic agent:
- Always retrieves context for every query
- Fixed pipeline (no tool calling)
- Simpler but less efficient

## How It Works

### Beanis Models

Three Beanis document models manage state:

**KnowledgeDocument**: Stores documents with vector embeddings
```python
class KnowledgeDocument(Document):
    title: str
    context: str
    embedding: Annotated[List[float], VectorField(dimensions=1536)]
```

**ConversationHistory**: Tracks conversation across sessions
```python
class ConversationHistory(Document):
    session_id: str
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime
```

**AgentState**: Stores agent workflow state (optional)
```python
class AgentState(Document):
    session_id: str
    current_step: str
    query: Optional[str]
```

### MCP Tools (Tool-Calling Agent)

The MCP server provides reusable tools that the agent can call:

```python
# 1. Search Knowledge Base
search_knowledge_base(query: str, k: int = 3)
# Vector similarity search in Redis - only called when needed

# 2. Get Conversation History
get_conversation_history(limit: int = 5)
# Load past messages for context - agent decides when to use

# 3. Store Agent Memory
store_memory(key: str, value: Any)
# Persist custom state in Redis (user prefs, facts, etc.)

# 4. Retrieve Agent Memory
retrieve_memory(key: str, default: Any = None)
# Recall previously stored information
```

**Key Advantage**: The LLM decides which tools to use based on the query. Simple greetings don't trigger expensive vector searches!

### LangGraph Workflows

#### Basic Agent Workflow (agent.py)
Fixed pipeline that always runs:
1. **retrieve_context**: Vector search in Redis
2. **load_history**: Load recent conversation
3. **generate_response**: Use LLM with context + history
4. **save_history**: Store conversation

#### Tool-Calling Agent Workflow (agent_with_tools.py)
Dynamic workflow with conditional tool usage:
1. **agent_node**: LLM analyzes query and decides which tools to call
2. **tool_node**: Execute selected tools (search, memory, history)
3. **Loop**: Agent re-evaluates with tool results
4. **Final response**: Generated when no more tools needed

### Vector Search with Beanis

Semantic search using Beanis:

```python
results = await IndexManager.find_by_vector_similarity(
    redis_client=redis_client,
    document_class=KnowledgeDocument,
    field_name="embedding",
    query_vector=query_embedding,
    k=3  # Top 3 results
)
```

Beanis automatically:
- Creates Redis vector indexes
- Handles serialization
- Manages index updates

## Example Usage

```python
from agent import RAGAgent

# Initialize
agent = RAGAgent(redis_client=redis_client, openai_api_key=api_key)

# Query
result = await agent.query(
    query="What is machine learning?",
    session_id="user-123"
)

print(result["response"])
# Prints AI-generated response with retrieved context
```

## Extending the Agent

### Add New Nodes

Add custom processing steps to the LangGraph workflow:

```python
def _build_graph(self):
    workflow = StateGraph(RAGAgentState)

    # Add custom node
    workflow.add_node("fact_check", self._fact_check)

    # Add to workflow
    workflow.add_edge("generate_response", "fact_check")
    workflow.add_edge("fact_check", "save_history")
```

### Parallel Execution

Run multiple retrievers in parallel:

```python
workflow.add_node("retrieve_semantic", self._retrieve_semantic)
workflow.add_node("retrieve_keyword", self._retrieve_keyword)

# Both run in parallel
workflow.set_entry_point("retrieve_semantic")
workflow.set_entry_point("retrieve_keyword")

# Combine results
workflow.add_node("combine_results", self._combine)
workflow.add_edge("retrieve_semantic", "combine_results")
workflow.add_edge("retrieve_keyword", "combine_results")
```

### Custom Embeddings

Use different embedding models:

```python
from sentence_transformers import SentenceTransformer

class CustomRAGAgent(RAGAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.embeddings = SentenceTransformer('all-MiniLM-L6-v2')
```

## Performance

Benchmarked on M1 Mac with 100 documents:

- **Ingestion**: ~5 seconds for 100 docs with embeddings
- **Query time**: ~500-800ms total (including vector search + LLM)
- **Vector search**: ~10-20ms in Redis
- **Memory usage**: ~4KB per document

## Why This Stack?

**Beanis + Redis**:
- ✅ Fast vector search (10-20ms)
- ✅ Built-in conversation persistence
- ✅ Clean ODM interface
- ✅ No separate vector database needed

**LangGraph**:
- ✅ Clear workflow visualization
- ✅ Easy to extend and modify
- ✅ Parallel execution support
- ✅ State management built-in

**OpenAI**:
- ✅ High-quality embeddings
- ✅ Powerful language models
- ✅ Simple API

## Troubleshooting

**Redis connection error**:
```bash
# Make sure Redis is running
redis-cli ping
# Should return: PONG
```

**Vector index disappears after inserting documents (ARM Macs)**:
This is caused by a Redis Stack ARM64 bug. Solution:
```bash
# Stop current container
docker stop langgraph-redis && docker rm langgraph-redis

# Start with x86 emulation
docker run -d -p 6379:6379 --name langgraph-redis --platform linux/amd64 redis/redis-stack:latest
```

Or update docker-compose.yml:
```yaml
services:
  redis:
    image: redis/redis-stack:latest
    platform: linux/amd64  # Add this line
    ports:
      - "6379:6379"
```

**OpenAI API errors**:
```bash
# Verify API key is set
echo $OPENAI_API_KEY

# Check rate limits in OpenAI dashboard
```

**Slow vector search**:
- Reduce `k` parameter in similarity search
- Use smaller dataset for testing
- Ensure Redis has enough memory

## Learn More

- [Beanis Documentation](https://andreim14.github.io/beanis/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Redis Vector Similarity](https://redis.io/docs/latest/develop/interact/search-and-query/query/vector-search/)

## License

MIT
