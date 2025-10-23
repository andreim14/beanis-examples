"""Ingest documents into the knowledge base - dead simple!"""
import asyncio
from pathlib import Path
from transformers import AutoModel
import redis.asyncio as redis
from beanis import init_beanis
from models import KnowledgeBase

# Load Jina embeddings v4 (open-source, multimodal)
print("Loading Jina v4 model...")
model = AutoModel.from_pretrained('jinaai/jina-embeddings-v4', trust_remote_code=True)


async def ingest_text(text: str):
    """Ingest a single text document"""
    # Generate embedding
    embedding = model.encode([text])[0].tolist()

    # Store in Redis
    doc = KnowledgeBase(text=text, embedding=embedding)
    await doc.insert()

    print(f"✓ Indexed: {text[:60]}...")


async def main():
    # Connect to Redis
    redis_client = redis.Redis(decode_responses=True)
    await init_beanis(database=redis_client, document_models=[KnowledgeBase])

    # Load sample data
    sample_file = Path(__file__).parent / "data" / "sample.txt"
    content = sample_file.read_text()

    # Split into paragraphs (simple chunking)
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]

    print(f"\n📚 Ingesting {len(paragraphs)} paragraphs...\n")

    # Ingest each paragraph
    for paragraph in paragraphs:
        await ingest_text(paragraph)

    print(f"\n✅ Successfully indexed {len(paragraphs)} documents!")
    print("💡 Try: python search.py 'what is semantic search?'")


if __name__ == "__main__":
    asyncio.run(main())
