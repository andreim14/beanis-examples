"""
CLI script to warm Redis cache from PostgreSQL

Usage:
    python scripts/warm_cache.py Roma
    python scripts/warm_cache.py --all
"""
import sys
import asyncio
import logging
import argparse

# Add parent directory to path
sys.path.insert(0, '.')

from database import SessionLocal, init_redis_cache
from services import RestaurantService
from models import RestaurantDB

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def warm_cache_for_city(city: str):
    """Warm Redis cache for a specific city"""

    logger.info(f"🔥 Warming cache for {city}...")

    await init_redis_cache()
    db = SessionLocal()

    try:
        service = RestaurantService(db)
        cached = await service.warm_cache(city)

        logger.info(f"✅ Cached {cached} restaurants for {city}")

    finally:
        db.close()


async def warm_cache_all():
    """Warm Redis cache for all cities in database"""

    logger.info("🔥 Warming cache for ALL cities...")

    await init_redis_cache()
    db = SessionLocal()

    try:
        # Get all unique cities
        cities = db.query(RestaurantDB.city).distinct().all()
        cities = [c[0] for c in cities if c[0]]

        logger.info(f"Found {len(cities)} cities: {', '.join(cities)}")

        total_cached = 0
        for city in cities:
            service = RestaurantService(db)
            cached = await service.warm_cache(city)
            total_cached += cached

        logger.info(f"\n✅ Total cached: {total_cached} restaurants across {len(cities)} cities")

    finally:
        db.close()


def main():
    """Parse arguments and warm cache"""
    parser = argparse.ArgumentParser(
        description="Warm Redis cache from PostgreSQL"
    )
    parser.add_argument(
        "city",
        nargs="?",
        help="City name (or use --all)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Warm cache for all cities"
    )

    args = parser.parse_args()

    if args.all:
        asyncio.run(warm_cache_all())
    elif args.city:
        asyncio.run(warm_cache_for_city(args.city))
    else:
        parser.error("Provide city name or --all flag")


if __name__ == "__main__":
    main()
