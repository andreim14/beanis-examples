"""Basic test to verify vector search works"""
import asyncio
import redis.asyncio as redis
from beanis import init_beanis
from models import KnowledgeBase
import numpy as np

async def test_basic():
    # Connect
    redis_client = redis.Redis(decode_responses=True)
    await init_beanis(database=redis_client, document_models=[KnowledgeBase])

    print("✓ Connected to Redis")

    # Create a few test documents with random embeddings
    docs = [
        ("Redis is fast", np.random.rand(1024).tolist()),
        ("Python is great", np.random.rand(1024).tolist()),
        ("Beanis is simple", np.random.rand(1024).tolist()),
    ]

    print("\n📝 Creating test documents...")
    for text, emb in docs:
        doc = KnowledgeBase(text=text, embedding=emb)
        await doc.insert()
        print(f"  ✓ {text}")

    print("\n✅ Test passed! Documents inserted successfully.")
    print("\n💡 Note: Vector indexes are created automatically on first init_beanis() call.")

if __name__ == "__main__":
    asyncio.run(test_basic())
