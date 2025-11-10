"""
Ingest data from Hugging Face dataset into Redis using Beanis
"""

import asyncio
import os
from datasets import load_dataset
from langchain_openai import OpenAIEmbeddings
from beanis import init_beanis
import redis.asyncio as redis

from models import KnowledgeDocument


async def ingest_squad_data(openai_api_key: str, max_docs: int = 100):
    """
    Load a subset of SQuAD data and ingest into Redis

    Args:
        openai_api_key: OpenAI API key for embeddings
        max_docs: Maximum number of documents to ingest
    """

    print("🚀 Starting data ingestion...")

    # Connect to Redis
    redis_client = redis.Redis(
        host="localhost", port=6379, decode_responses=True
    )

    # Initialize Beanis
    await init_beanis(
        database=redis_client, document_models=[KnowledgeDocument]
    )

    print("✅ Connected to Redis and initialized Beanis")

    # Initialize embeddings
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small", openai_api_key=openai_api_key
    )

    print("✅ Initialized OpenAI embeddings")

    # Load dataset
    print(f"📥 Loading SQuAD dataset (first {max_docs} examples)...")
    dataset = load_dataset("rajpurkar/squad", split="train")

    # Take a small subset
    subset = dataset.select(range(min(max_docs, len(dataset))))

    print(f"📊 Processing {len(subset)} documents...")

    # Ingest documents
    ingested_count = 0
    for i, example in enumerate(subset):
        try:
            # Extract fields
            title = example["title"]
            context = example["context"]
            question = example["question"]

            # Generate embedding
            embedding = embeddings.embed_query(context)

            # Create document
            doc = KnowledgeDocument(
                title=title,
                context=context,
                question=question,
                embedding=embedding,
                source="squad",
            )

            # Insert into Redis
            await doc.insert()

            ingested_count += 1

            if (i + 1) % 10 == 0:
                print(f"  ✓ Processed {i + 1}/{len(subset)} documents...")

        except Exception as e:
            print(f"  ✗ Error processing document {i}: {e}")
            continue

    print(f"\n✅ Successfully ingested {ingested_count} documents!")

    # Show sample
    try:
        sample_docs = await KnowledgeDocument.find_many().limit(3)
        print(f"\n📄 Sample documents:")
        for doc in sample_docs:
            print(f"  - {doc.title}: {doc.context[:100]}...")
    except Exception as e:
        print(f"\n📄 Sample documents: (skipping due to API difference)")

    await redis_client.aclose()


if __name__ == "__main__":
    # Load environment variables from .env file
    from dotenv import load_dotenv

    load_dotenv()

    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        print("Create a .env file with: OPENAI_API_KEY=your-key-here")
        exit(1)

    # Run ingestion
    asyncio.run(ingest_squad_data(api_key, max_docs=100))
