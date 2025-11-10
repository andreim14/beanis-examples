"""
Test the tool-calling RAG agent with MCP integration

Demonstrates:
1. Agent decides when to search vs use memory
2. Conversation history across sessions
3. Memory storage for user preferences
"""

import asyncio
import os
from dotenv import load_dotenv
import redis.asyncio as redis

from beanis import init_beanis
from models import KnowledgeDocument, ConversationHistory, AgentState
from mcp_server import BeanisRAGTools
from agent_with_tools import ToolCallingRAGAgent


async def main():
    load_dotenv()

    # Connect to Redis
    redis_client = redis.Redis(
        host="localhost", port=6379, decode_responses=False
    )

    # Initialize Beanis
    await init_beanis(
        database=redis_client,
        document_models=[KnowledgeDocument, ConversationHistory, AgentState],
    )

    print("✅ Connected to Redis and initialized Beanis")

    # Initialize MCP tools and agent
    mcp_tools = BeanisRAGTools(
        redis_client=redis_client, openai_api_key=os.getenv("OPENAI_API_KEY")
    )

    agent = ToolCallingRAGAgent(
        mcp_tools=mcp_tools, openai_api_key=os.getenv("OPENAI_API_KEY")
    )

    # Test scenarios
    session_id = "demo_session"

    print("\n" + "=" * 80)
    print("SCENARIO 1: Simple greeting (should NOT use tools)")
    print("=" * 80)
    result = await agent.query("Hello! How are you?", session_id=session_id)
    print(f"\nResponse: {result['response']}\n")

    print("\n" + "=" * 80)
    print("SCENARIO 2: Question requiring knowledge base search")
    print("=" * 80)
    result = await agent.query(
        "What is the capital of France according to your knowledge base?",
        session_id=session_id,
    )
    print(f"\nResponse: {result['response']}\n")

    print("\n" + "=" * 80)
    print("SCENARIO 3: Store user preference in memory")
    print("=" * 80)
    result = await agent.query(
        "My name is Stefan and I prefer short answers.", session_id=session_id
    )
    print(f"\nResponse: {result['response']}\n")

    print("\n" + "=" * 80)
    print("SCENARIO 4: Follow-up question (should use conversation history)")
    print("=" * 80)
    result = await agent.query("What did I just tell you?", session_id=session_id)
    print(f"\nResponse: {result['response']}\n")

    print("\n" + "=" * 80)
    print("SCENARIO 5: Complex question requiring both search and context")
    print("=" * 80)
    result = await agent.query(
        "Based on what you know about me, find information about the University of Notre Dame and summarize it briefly.",
        session_id=session_id,
    )
    print(f"\nResponse: {result['response']}\n")

    # Verify memory persistence
    print("\n" + "=" * 80)
    print("VERIFYING MEMORY PERSISTENCE")
    print("=" * 80)
    stored_name = await mcp_tools.retrieve_agent_memory(session_id, "user_name")
    print(f"Stored user name: {stored_name}")

    # Test new session with history
    print("\n" + "=" * 80)
    print("SCENARIO 6: New session but checking if history can be retrieved")
    print("=" * 80)
    new_session_id = "new_session"
    result = await agent.query(
        "Do you know anything about Stefan?", session_id=new_session_id
    )
    print(f"\nResponse: {result['response']}\n")

    await redis_client.aclose()
    print("✅ Test complete!")


if __name__ == "__main__":
    asyncio.run(main())
