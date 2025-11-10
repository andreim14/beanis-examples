"""
Main script to run the RAG agent with LangGraph and Beanis
"""

import asyncio
import os
import sys
from beanis import init_beanis
import redis.asyncio as redis

from agent import RAGAgent
from models import KnowledgeDocument, ConversationHistory, AgentState


async def main():
    """Run the RAG agent"""

    # Load environment variables
    from dotenv import load_dotenv

    load_dotenv()

    # Get API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        print("Create a .env file with: OPENAI_API_KEY=your-key-here")
        sys.exit(1)

    print("🚀 Starting RAG Agent with LangGraph + Beanis\n")

    # Connect to Redis
    redis_client = redis.Redis(
        host="localhost", port=6379, decode_responses=False
    )

    # Initialize Beanis
    await init_beanis(
        database=redis_client,
        document_models=[KnowledgeDocument, ConversationHistory, AgentState],
    )

    print("✅ Connected to Redis and initialized Beanis\n")

    # Create agent
    agent = RAGAgent(redis_client=redis_client, openai_api_key=api_key)

    print("✅ RAG Agent initialized\n")

    # Example queries
    queries = [
        "What is the Normans' legacy in modern English language?",
        "Tell me about the architectural contributions of the Normans",
        "What was the Norman conquest?",
    ]

    session_id = "demo-session-001"

    for i, query in enumerate(queries, 1):
        print(f"\n{'#' * 80}")
        print(f"Query {i}/{len(queries)}")
        print(f"{'#' * 80}\n")

        result = await agent.query(query, session_id=session_id)

        print(f"\n📝 Response:\n{result['response']}\n")
        print(f"📚 Retrieved {len(result['retrieved_docs'])} documents")
        print(f"🎯 Confidence: {result['confidence']:.2f}")

        # Small delay between queries
        if i < len(queries):
            await asyncio.sleep(1)

    # Interactive mode
    print(f"\n{'=' * 80}")
    print("💬 Interactive Mode - Type 'quit' to exit")
    print(f"{'=' * 80}\n")

    while True:
        try:
            user_input = input("\nYour question: ").strip()

            if user_input.lower() in ["quit", "exit", "q"]:
                print("\n👋 Goodbye!")
                break

            if not user_input:
                continue

            result = await agent.query(user_input, session_id=session_id)

            print(f"\n🤖 Assistant:\n{result['response']}\n")
            print(f"📚 Retrieved {len(result['retrieved_docs'])} documents")

        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            continue

    await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
