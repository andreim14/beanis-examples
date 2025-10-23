"""
CLI script to import restaurants from OpenStreetMap into PostgreSQL

Usage:
    python scripts/import_city.py Roma
    python scripts/import_city.py Milano --country Italy --warm-cache
"""
import sys
import asyncio
import logging
import argparse
from sqlalchemy import func
from geoalchemy2.functions import ST_SetSRID, ST_MakePoint

# Add parent directory to path for imports
sys.path.insert(0, '.')

from database import SessionLocal, init_postgres_db, init_redis_cache
from services import OSMImporter, RestaurantService
from models import RestaurantDB

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def import_city(city: str, country: str = "Italy", warm_cache: bool = False):
    """
    Import restaurants from OpenStreetMap into PostgreSQL

    Args:
        city: City name (e.g., "Roma", "Milano")
        country: Country name
        warm_cache: Whether to warm Redis cache after import
    """

    logger.info(f"===== Importing Restaurants for {city}, {country} =====")

    # Initialize database
    init_postgres_db()
    db = SessionLocal()

    try:
        # Fetch from OSM
        importer = OSMImporter()
        osm_data = importer.fetch_restaurants(city, country)

        if not osm_data:
            logger.error("❌ No restaurants fetched from OSM")
            return

        logger.info(f"📦 Fetched {len(osm_data)} restaurants from OSM")

        # Import into PostgreSQL
        imported = 0
        skipped = 0

        for data in osm_data:
            # Check if already exists
            exists = db.query(RestaurantDB).filter_by(
                osm_id=data["osm_id"]
            ).first()

            if exists:
                skipped += 1
                continue

            # Create restaurant
            restaurant = RestaurantDB(
                osm_id=data["osm_id"],
                name=data["name"],
                location=func.ST_SetSRID(
                    func.ST_MakePoint(data["longitude"], data["latitude"]),
                    4326
                ),
                address=data["address"],
                city=data["city"],
                country=data["country"],
                cuisine=data["cuisine"],
                phone=data["phone"],
                website=data["website"],
                outdoor_seating=data["outdoor_seating"],
                accepts_delivery=data["delivery"],
                takeaway=data["takeaway"],
                wheelchair_accessible=data["wheelchair"],
                opening_hours={"raw": data["opening_hours"]} if data["opening_hours"] else {},
                is_active=True
            )

            db.add(restaurant)
            imported += 1

            # Commit in batches
            if imported % 100 == 0:
                db.commit()
                logger.info(f"  💾 Committed {imported} restaurants...")

        # Final commit
        db.commit()

        logger.info(f"""
===== Import Summary =====
✅ Imported: {imported} new restaurants
⏭️  Skipped: {skipped} duplicates
💾 Total in DB: {db.query(RestaurantDB).filter_by(city=city).count()} restaurants
        """)

        # Warm cache if requested
        if warm_cache and imported > 0:
            logger.info("\n🔥 Warming Redis cache...")
            await init_redis_cache()

            service = RestaurantService(db)
            cached = await service.warm_cache(city)

            logger.info(f"✅ Cached {cached} restaurants in Redis")

    finally:
        db.close()


def main():
    """Parse arguments and run import"""
    parser = argparse.ArgumentParser(
        description="Import restaurants from OpenStreetMap"
    )
    parser.add_argument(
        "city",
        help="City name (e.g., Roma, Milano)"
    )
    parser.add_argument(
        "--country",
        default="Italy",
        help="Country name (default: Italy)"
    )
    parser.add_argument(
        "--warm-cache",
        action="store_true",
        help="Warm Redis cache after import"
    )

    args = parser.parse_args()

    # Run import
    asyncio.run(import_city(
        city=args.city,
        country=args.country,
        warm_cache=args.warm_cache
    ))


if __name__ == "__main__":
    main()
