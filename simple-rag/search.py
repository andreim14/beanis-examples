"""Search the knowledge base - incredibly simple!"""
import asyncio
import sys
from transformers import AutoModel
import redis.asyncio as redis
from beanis import init_beanis
from beanis.odm.indexes import IndexManager
from models import KnowledgeBase

# Load model
model = AutoModel.from_pretrained('jinaai/jina-embeddings-v4', trust_remote_code=True)


async def search(query: str, k: int = 3):
    """Search for similar documents"""
    # Connect to Redis
    redis_client = redis.Redis(decode_responses=True)
    await init_beanis(database=redis_client, document_models=[KnowledgeBase])

    # Embed the query
    query_embedding = model.encode([query])[0].tolist()

    # Search (that's it!)
    results = await IndexManager.find_by_vector_similarity(
        redis_client=redis_client,
        document_class=KnowledgeBase,
        field_name="embedding",
        query_vector=query_embedding,
        k=k
    )

    # Display results
    print(f"\n🔍 Query: '{query}'\n")
    print(f"Found {len(results)} relevant documents:\n")

    for i, (doc_id, score) in enumerate(results, 1):
        doc = await KnowledgeBase.get(doc_id)
        print(f"{i}. [Similarity: {score:.3f}]")
        print(f"   {doc.text[:200]}...")
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python search.py 'your question here'")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    asyncio.run(search(query))
