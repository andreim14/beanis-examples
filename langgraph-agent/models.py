"""
Beanis models for LangGraph RAG agent
Stores documents with embeddings and conversation history in Redis
"""

from beanis import Document, VectorField
from datetime import datetime
from typing import List, Optional
from typing_extensions import Annotated
from pydantic import Field


class KnowledgeDocument(Document):
    """Document with vector embeddings for RAG retrieval"""

    title: str = Field(description="Document title")
    context: str = Field(description="Document content/context")
    question: Optional[str] = Field(default=None, description="Associated question if any")

    # Vector embedding for semantic search (1536 dimensions for OpenAI text-embedding-3-small)
    embedding: Annotated[List[float], VectorField(dimensions=1536)]

    # Metadata
    source: str = Field(default="squad", description="Data source")
    created_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "knowledge_docs"


class ConversationHistory(Document):
    """Stores conversation history for context-aware responses"""

    session_id: Annotated[str, Field(description="Unique session identifier", index=True)]
    role: str = Field(description="Role: user or assistant")
    content: str = Field(description="Message content")
    timestamp: datetime = Field(default_factory=datetime.now)

    # Optional metadata
    retrieved_docs: Optional[List[str]] = Field(default=None, description="Document IDs used for this response")

    class Settings:
        name = "conversations"


class AgentState(Document):
    """Stores agent state between runs"""

    session_id: str = Field(description="Unique session identifier")
    current_step: str = Field(default="start", description="Current step in the graph")
    query: Optional[str] = Field(default=None, description="Current user query")
    retrieved_context: Optional[str] = Field(default=None, description="Retrieved context")
    final_response: Optional[str] = Field(default=None, description="Final generated response")

    # Metadata
    last_updated: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "agent_states"
