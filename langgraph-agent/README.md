# LangGraph RAG Agent with Beanis

Build intelligent AI agents with conversation memory and semantic search using LangGraph + Beanis + Redis.

## What This Example Shows

This example demonstrates how to build a production-ready RAG (Retrieval-Augmented Generation) agent that:

- **Stores knowledge** in Redis using Beanis with vector embeddings
- **Orchestrates workflows** using LangGraph for complex agent logic
- **Maintains conversation history** across sessions for context-aware responses
- **Retrieves relevant context** using semantic search
- **Generates responses** using OpenAI GPT models with retrieved context

## Architecture

```
User Query
    ↓
┌─────────────────────────────────────┐
│         LangGraph Workflow          │
│                                     │
│  ┌─────────────────────────────┐   │
│  │  1. Retrieve Context        │   │
│  │     (Vector Search in Redis)│   │
│  └────────────┬────────────────┘   │
│               ↓                     │
│  ┌─────────────────────────────┐   │
│  │  2. Load History            │   │
│  │     (From Redis)            │   │
│  └────────────┬────────────────┘   │
│               ↓                     │
│  ┌─────────────────────────────┐   │
│  │  3. Generate Response       │   │
│  │     (OpenAI + Context)      │   │
│  └────────────┬────────────────┘   │
│               ↓                     │
│  ┌─────────────────────────────┐   │
│  │  4. Save to History         │   │
│  │     (Redis via Beanis)      │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
    ↓
Response + Metadata
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
# Using Docker
docker run -d -p 6379:6379 redis:latest

# Or using redis-stack for additional features
docker run -d -p 6379:6379 redis/redis-stack:latest
```

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

```bash
python main.py
```

The agent will:
- Run example queries to demonstrate functionality
- Enter interactive mode for you to ask questions

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

### LangGraph Workflow

The agent uses LangGraph to orchestrate the RAG workflow:

1. **retrieve_context**: Vector search in Redis to find relevant documents
2. **load_history**: Load recent conversation from Redis
3. **generate_response**: Use LLM with context + history
4. **save_history**: Store conversation for future context

Each step is a node in the graph, allowing for:
- **Parallel execution** where appropriate
- **State management** between steps
- **Error handling** at each node
- **Easy modification** of workflow logic

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
