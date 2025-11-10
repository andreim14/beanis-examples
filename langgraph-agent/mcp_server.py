"""
MCP Server for Beanis RAG Integration

Provides tools for LangGraph agents to interact with Beanis:
1. Vector similarity search (retrieval tool)
2. Memory management (store/retrieve agent state)
3. Conversation history tracking
"""

import asyncio
import json
import os
from typing import List, Optional, Dict, Any

import redis.asyncio as redis
from beanis import init_beanis
from beanis.odm.indexes import IndexManager
from langchain_openai import OpenAIEmbeddings

from models import KnowledgeDocument, ConversationHistory, AgentState


class BeanisRAGTools:
    """MCP-compatible tools for Beanis RAG operations"""

    def __init__(self, redis_client, openai_api_key: str):
        self.redis_client = redis_client
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small", openai_api_key=openai_api_key
        )

    async def search_knowledge_base(
        self, query: str, k: int = 3, min_score: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Tool: Search knowledge base using vector similarity

        Args:
            query: Search query text
            k: Number of results to return
            min_score: Minimum similarity score (0-1)

        Returns:
            List of documents with content and metadata
        """
        print(f"🔍 [MCP Tool] Searching knowledge base: {query[:50]}...")

        # Generate query embedding
        query_embedding = self.embeddings.embed_query(query)

        # Search using Beanis
        results = await IndexManager.find_by_vector_similarity(
            redis_client=self.redis_client,
            document_class=KnowledgeDocument,
            field_name="embedding",
            query_vector=query_embedding,
            k=k,
        )

        # Fetch and format documents
        documents = []
        for doc_id, score in results:
            if score >= min_score:
                doc = await KnowledgeDocument.get(doc_id)
                if doc:
                    documents.append(
                        {
                            "id": str(doc.id),
                            "title": doc.title,
                            "context": doc.context,
                            "question": doc.question,
                            "score": float(score),
                            "source": doc.source,
                        }
                    )

        print(f"✅ [MCP Tool] Found {len(documents)} relevant documents")
        return documents

    async def get_conversation_history(
        self, session_id: str, limit: int = 5
    ) -> List[Dict[str, str]]:
        """
        Tool: Retrieve conversation history for a session

        Args:
            session_id: Session identifier
            limit: Maximum number of messages to retrieve

        Returns:
            List of conversation messages (oldest to newest)
        """
        print(f"📜 [MCP Tool] Loading history for session: {session_id}")

        # Get all conversation docs and filter by session
        # We get all since session_id indexing might not be set up
        all_docs = await ConversationHistory.all()

        # Filter by session_id manually
        session_docs = [doc for doc in all_docs if doc.session_id == session_id]

        # Sort by timestamp and limit
        history_docs = sorted(session_docs, key=lambda x: x.timestamp, reverse=True)[:limit]

        # Return oldest first
        messages = [
            {
                "role": doc.role,
                "content": doc.content,
                "timestamp": doc.timestamp.isoformat() if hasattr(doc.timestamp, 'isoformat') else str(doc.timestamp),
            }
            for doc in reversed(history_docs)
        ]

        print(f"✅ [MCP Tool] Loaded {len(messages)} messages")
        return messages

    async def save_conversation_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        retrieved_docs: Optional[List[str]] = None,
    ) -> bool:
        """
        Tool: Save a conversation turn (user + assistant messages)

        Args:
            session_id: Session identifier
            user_message: User's message
            assistant_message: Assistant's response
            retrieved_docs: List of document IDs used for this response

        Returns:
            True if successful
        """
        print(f"💾 [MCP Tool] Saving conversation turn for: {session_id}")

        # Save user message
        user_msg = ConversationHistory(
            session_id=session_id, role="user", content=user_message
        )
        await user_msg.insert()

        # Save assistant response
        assistant_msg = ConversationHistory(
            session_id=session_id,
            role="assistant",
            content=assistant_message,
            retrieved_docs=retrieved_docs or [],
        )
        await assistant_msg.insert()

        print(f"✅ [MCP Tool] Conversation saved")
        return True

    async def store_agent_memory(
        self, session_id: str, key: str, value: Any
    ) -> bool:
        """
        Tool: Store arbitrary agent state/memory

        Args:
            session_id: Session identifier
            key: Memory key
            value: Value to store (will be JSON serialized)

        Returns:
            True if successful
        """
        print(f"🧠 [MCP Tool] Storing memory: {session_id}/{key}")

        # Store in Redis directly for fast access
        memory_key = f"agent_memory:{session_id}:{key}"
        await self.redis_client.set(
            memory_key, json.dumps(value), ex=86400  # 24 hour expiry
        )

        print(f"✅ [MCP Tool] Memory stored")
        return True

    async def retrieve_agent_memory(
        self, session_id: str, key: str, default: Any = None
    ) -> Any:
        """
        Tool: Retrieve agent state/memory

        Args:
            session_id: Session identifier
            key: Memory key
            default: Default value if not found

        Returns:
            Stored value or default
        """
        print(f"🧠 [MCP Tool] Retrieving memory: {session_id}/{key}")

        memory_key = f"agent_memory:{session_id}:{key}"
        value = await self.redis_client.get(memory_key)

        if value:
            print(f"✅ [MCP Tool] Memory retrieved")
            return json.loads(value)
        else:
            print(f"ℹ️  [MCP Tool] Memory not found, using default")
            return default

    async def clear_session_memory(self, session_id: str) -> bool:
        """
        Tool: Clear all memory for a session

        Args:
            session_id: Session identifier

        Returns:
            True if successful
        """
        print(f"🗑️  [MCP Tool] Clearing memory for: {session_id}")

        # Clear all memory keys for this session
        pattern = f"agent_memory:{session_id}:*"
        keys = []
        async for key in self.redis_client.scan_iter(match=pattern):
            keys.append(key)

        if keys:
            await self.redis_client.delete(*keys)
            print(f"✅ [MCP Tool] Cleared {len(keys)} memory entries")
        else:
            print(f"ℹ️  [MCP Tool] No memory entries found")

        return True


# Tool definitions for MCP protocol
MCP_TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": "Search the knowledge base using semantic similarity. Use this when you need to find relevant information to answer the user's question.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "k": {
                    "type": "integer",
                    "description": "Number of results to return (default: 3)",
                    "default": 3,
                },
                "min_score": {
                    "type": "number",
                    "description": "Minimum similarity score 0-1 (default: 0.7)",
                    "default": 0.7,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_conversation_history",
        "description": "Retrieve conversation history for context-aware responses",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum messages to retrieve (default: 5)",
                    "default": 5,
                },
            },
            "required": [],
        },
    },
    {
        "name": "save_conversation_turn",
        "description": "Save a conversation turn to memory",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "user_message": {"type": "string"},
                "assistant_message": {"type": "string"},
                "retrieved_docs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Document IDs used",
                },
            },
            "required": ["session_id", "user_message", "assistant_message"],
        },
    },
    {
        "name": "store_agent_memory",
        "description": "Store arbitrary agent state/memory (key-value store)",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Memory key"},
                "value": {"description": "Value to store (any JSON type)"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "retrieve_agent_memory",
        "description": "Retrieve agent state/memory by key",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Memory key"},
                "default": {
                    "description": "Default value if not found",
                },
            },
            "required": ["key"],
        },
    },
    {
        "name": "clear_session_memory",
        "description": "Clear all memory for a session",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
            },
            "required": ["session_id"],
        },
    },
]
