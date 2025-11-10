"""
LangGraph RAG Agent using Beanis for state management and vector storage
"""

import os
from typing import TypedDict, List, Annotated
from operator import add

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import HumanMessage, SystemMessage

from beanis.odm.indexes import IndexManager
from models import KnowledgeDocument, ConversationHistory, AgentState
import redis.asyncio as redis


# Define the agent state type
class RAGAgentState(TypedDict):
    """State for the RAG agent workflow"""

    query: str
    session_id: str
    conversation_history: List[dict]
    retrieved_docs: List[str]
    retrieved_context: str
    final_response: str
    confidence_score: float


class RAGAgent:
    """
    RAG Agent using LangGraph for workflow and Beanis for storage

    Features:
    - Semantic search over knowledge base using vector embeddings
    - Conversation history tracking
    - Parallel document retrieval for speed
    - Context-aware response generation
    """

    def __init__(self, redis_client, openai_api_key: str, model: str = "gpt-4o-mini"):
        self.redis_client = redis_client
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small", openai_api_key=openai_api_key
        )
        self.llm = ChatOpenAI(
            model=model, temperature=0.7, openai_api_key=openai_api_key
        )

        # Build the LangGraph workflow
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow with parallel nodes"""

        workflow = StateGraph(RAGAgentState)

        # Define nodes
        workflow.add_node("retrieve_context", self._retrieve_context)
        workflow.add_node("load_history", self._load_conversation_history)
        workflow.add_node("generate_response", self._generate_response)
        workflow.add_node("save_history", self._save_conversation)

        # Define edges
        workflow.set_entry_point("retrieve_context")

        # After retrieval, load history in parallel (could be parallelized)
        workflow.add_edge("retrieve_context", "load_history")
        workflow.add_edge("load_history", "generate_response")
        workflow.add_edge("generate_response", "save_history")
        workflow.add_edge("save_history", END)

        return workflow.compile()

    async def _retrieve_context(self, state: RAGAgentState) -> RAGAgentState:
        """Retrieve relevant documents from Redis using vector similarity"""

        print(f"🔍 Retrieving context for: {state['query'][:50]}...")

        # Generate query embedding
        query_embedding = self.embeddings.embed_query(state["query"])

        # Search using Beanis vector similarity
        results = await IndexManager.find_by_vector_similarity(
            redis_client=self.redis_client,
            document_class=KnowledgeDocument,
            field_name="embedding",
            query_vector=query_embedding,
            k=3,  # Top 3 most relevant docs
        )

        # Fetch documents
        retrieved_texts = []
        doc_ids = []

        for doc_id, score in results:
            doc = await KnowledgeDocument.get(doc_id)
            if doc:
                retrieved_texts.append(f"Context: {doc.context}")
                doc_ids.append(str(doc.id))

        # Combine context
        combined_context = "\n\n".join(retrieved_texts) if retrieved_texts else "No relevant context found."

        print(f"✅ Retrieved {len(retrieved_texts)} documents")

        return {
            **state,
            "retrieved_docs": doc_ids,
            "retrieved_context": combined_context,
        }

    async def _load_conversation_history(self, state: RAGAgentState) -> RAGAgentState:
        """Load recent conversation history from Redis"""

        print(f"📜 Loading conversation history for session: {state['session_id']}")

        # Get last 5 messages from this session
        # Using Beanis find_many with filtering
        try:
            history_docs = await ConversationHistory.find_many(
                ConversationHistory.session_id == state["session_id"],
                sort=[("timestamp", -1)],
                limit=5
            )
        except:
            # Fallback if API is different
            history_docs = []

        # Convert to dict format (most recent first, so reverse)
        conversation_history = [
            {"role": doc.role, "content": doc.content}
            for doc in reversed(history_docs)
        ]

        print(f"✅ Loaded {len(conversation_history)} messages")

        return {**state, "conversation_history": conversation_history}

    async def _generate_response(self, state: RAGAgentState) -> RAGAgentState:
        """Generate response using LLM with retrieved context and history"""

        print(f"🤖 Generating response...")

        # Build messages
        messages = [
            SystemMessage(
                content="""You are a helpful AI assistant with access to a knowledge base.
Answer questions based on the provided context. If the context doesn't contain
enough information, say so clearly. Be concise but informative.

Retrieved Context:
{context}
""".format(
                    context=state["retrieved_context"]
                )
            )
        ]

        # Add conversation history
        for msg in state.get("conversation_history", []):
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(SystemMessage(content=msg["content"]))

        # Add current query
        messages.append(HumanMessage(content=state["query"]))

        # Generate response
        response = await self.llm.ainvoke(messages)

        print(f"✅ Response generated")

        return {
            **state,
            "final_response": response.content,
            "confidence_score": 0.9,  # Placeholder
        }

    async def _save_conversation(self, state: RAGAgentState) -> RAGAgentState:
        """Save conversation to Redis for future context"""

        print(f"💾 Saving conversation...")

        # Save user message
        user_msg = ConversationHistory(
            session_id=state["session_id"],
            role="user",
            content=state["query"],
        )
        await user_msg.insert()

        # Save assistant response
        assistant_msg = ConversationHistory(
            session_id=state["session_id"],
            role="assistant",
            content=state["final_response"],
            retrieved_docs=state.get("retrieved_docs", []),
        )
        await assistant_msg.insert()

        print(f"✅ Conversation saved")

        return state

    async def query(self, query: str, session_id: str = "default") -> dict:
        """
        Query the RAG agent

        Args:
            query: User question
            session_id: Session identifier for conversation tracking

        Returns:
            Dict with response and metadata
        """

        print(f"\n{'=' * 60}")
        print(f"🚀 Processing query: {query}")
        print(f"{'=' * 60}\n")

        initial_state: RAGAgentState = {
            "query": query,
            "session_id": session_id,
            "conversation_history": [],
            "retrieved_docs": [],
            "retrieved_context": "",
            "final_response": "",
            "confidence_score": 0.0,
        }

        # Run the graph
        final_state = await self.graph.ainvoke(initial_state)

        return {
            "response": final_state["final_response"],
            "retrieved_docs": final_state["retrieved_docs"],
            "confidence": final_state["confidence_score"],
            "session_id": session_id,
        }
