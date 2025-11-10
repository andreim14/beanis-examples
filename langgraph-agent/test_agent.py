"""
Quick test script for the RAG agent (non-interactive)
"""

import asyncio
import os
import sys
from beanis import init_beanis
import redis.asyncio as redis
from dotenv import load_dotenv

from agent import RAGAgent
from models import KnowledgeDocument, ConversationHistory, AgentState


async def test_agent():
    """Test the RAG agent with a few queries"""

    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ Error: OPENAI_API_KEY not set")
        sys.exit(1)

    print("🚀 Testing RAG Agent\n")

    # Connect to Redis
    redis_client = redis.Redis(
        host="localhost", port=6379, decode_responses=False
    )

    # Initialize Beanis
    await init_beanis(
        database=redis_client,
        document_models=[KnowledgeDocument, ConversationHistory, AgentState],
    )

    print("✅ Connected to Redis\n")

    # Create agent
    agent = RAGAgent(redis_client=redis_client, openai_api_key=api_key)

    print("✅ Agent initialized\n")

    # Test query
    query = "What is the Normans' legacy?"
    session_id = "test-session"

    print(f"Testing query: {query}\n")

    result = await agent.query(query, session_id=session_id)

    print(f"\n{'=' * 60}")
    print(f"📝 Response:\n{result['response']}")
    print(f"\n📚 Retrieved {len(result['retrieved_docs'])} documents")
    print(f"🎯 Confidence: {result['confidence']:.2f}")
    print(f"{'=' * 60}\n")

    print("✅ Test completed successfully!")

    await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(test_agent())
