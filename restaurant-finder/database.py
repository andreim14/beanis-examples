"""Database connection management for PostgreSQL and Redis"""
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
import redis.asyncio as redis
from beanis import init_beanis

from config import settings
from models import Base, RestaurantCache

logger = logging.getLogger(__name__)

# PostgreSQL setup
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=NullPool,  # Disable connection pooling for CLI scripts
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_postgres_db():
    """
    Initialize PostgreSQL database and create tables

    Creates all tables defined in models.db if they don't exist
    Enables PostGIS extension
    """
    from sqlalchemy import text

    logger.info("Initializing PostgreSQL database...")

    # Enable PostGIS extension
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.commit()
        logger.info("✅ PostGIS extension enabled")

    # Create tables
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Database tables created")


def get_db() -> Session:
    """
    Get PostgreSQL database session

    Usage in FastAPI:
        @app.get("/...")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Redis setup
_redis_client = None


async def get_redis_client():
    """
    Get Redis client singleton

    Returns cached client or creates new one
    """
    global _redis_client

    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True
        )
        logger.info(f"✅ Connected to Redis at {settings.REDIS_URL}")

    return _redis_client


async def init_redis_cache():
    """
    Initialize Beanis with Redis

    Call this on application startup
    """
    logger.info("Initializing Redis cache with Beanis...")

    client = await get_redis_client()

    await init_beanis(
        database=client,
        document_models=[RestaurantCache]
    )

    logger.info("✅ Beanis initialized with Redis")


async def close_redis():
    """Close Redis connection"""
    global _redis_client

    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("✅ Redis connection closed")
