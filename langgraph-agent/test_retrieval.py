"""
Test vector retrieval independently
"""

import asyncio
import os
from beanis import init_beanis
from beanis.odm.indexes import IndexManager
import redis.asyncio as redis
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings

from models import KnowledgeDocument


async def test_retrieval():
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")

    print("🚀 Testing Vector Retrieval\n")

    redis_client = redis.Redis(host="localhost", port=6379, decode_responses=False)

    await init_beanis(database=redis_client, document_models=[KnowledgeDocument])

    print("✅ Connected to Redis\n")

    # Check how many documents exist
    try:
        all_docs = await KnowledgeDocument.find_many(limit=5)
        print(f"📊 Found {len(all_docs)} documents in Redis")

        if all_docs:
            print(f"\n📄 Sample documents:")
            for i, doc in enumerate(all_docs[:3], 1):
                print(f"  {i}. Title: {doc.title}")
                print(f"     Context: {doc.context[:100]}...")
                print()
    except Exception as e:
        print(f"❌ Error fetching documents: {e}")

    # Test vector search
    print(f"\n🔍 Testing vector search...")

    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small", openai_api_key=api_key
    )

    query = "Who were the Normans?"
    query_embedding = embeddings.embed_query(query)

    print(f"Query: {query}")
    print(f"Embedding dimensions: {len(query_embedding)}")

    try:
        results = await IndexManager.find_by_vector_similarity(
            redis_client=redis_client,
            document_class=KnowledgeDocument,
            field_name="embedding",
            query_vector=query_embedding,
            k=3,
        )

        print(f"\n✅ Found {len(results)} matching documents:")

        for doc_id, score in results:
            doc = await KnowledgeDocument.get(doc_id)
            if doc:
                print(f"\n  📄 Document (score: {score:.4f}):")
                print(f"     Title: {doc.title}")
                print(f"     Context: {doc.context[:150]}...")

    except Exception as e:
        print(f"❌ Error during vector search: {e}")
        import traceback

        traceback.print_exc()

    await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(test_retrieval())
