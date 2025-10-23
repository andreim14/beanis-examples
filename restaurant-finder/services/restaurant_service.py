"""Restaurant service with intelligent cache-first queries"""
import logging
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from geoalchemy2.functions import ST_SetSRID, ST_MakePoint, ST_DWithin
from sqlalchemy import cast, func
from geoalchemy2.types import Geometry

from models import RestaurantDB, RestaurantCache
from database import get_redis_client
from beanis.odm.indexes import IndexManager
from beanis import GeoPoint

logger = logging.getLogger(__name__)


class RestaurantService:
    """
    Manages restaurant queries with cache-first strategy

    Flow:
    1. Try Redis cache (5-10ms)
    2. On cache miss → Query PostgreSQL (50-100ms)
    3. Cache the result for next time
    4. Return results
    """

    def __init__(self, db_session: Session):
        self.db = db_session

    async def find_nearby(
        self,
        lat: float,
        lon: float,
        radius_km: float = 2.0,
        cuisine: Optional[str] = None,
        min_rating: float = 0.0,
        max_price: int = 4,
        use_cache: bool = True
    ) -> List[tuple[RestaurantCache, float]]:
        """
        Find restaurants near a location with intelligent caching

        Args:
            lat: Latitude
            lon: Longitude
            radius_km: Search radius in kilometers
            cuisine: Filter by cuisine (optional)
            min_rating: Minimum rating (0-5)
            max_price: Maximum price range (1-4)
            use_cache: Whether to use cache (default: True)

        Returns:
            List of (RestaurantCache, distance_km) tuples
        """

        user_location = GeoPoint(latitude=lat, longitude=lon)

        # === TRY CACHE FIRST ===
        if use_cache:
            cache_start = datetime.now()

            # Build query parameters for Redis
            query_params = {
                "location": user_location,
                "radius": int(radius_km * 1000),  # Convert km to meters
                "is_active": True,
                "rating__gte": min_rating,
                "price_range__lte": max_price,
            }

            if cuisine:
                query_params["cuisine"] = cuisine.lower()

            # Query Redis via Beanis geo-spatial index
            redis_client = await get_redis_client()
            
            results_with_distance = await IndexManager.find_by_geo_radius_with_distance(
                redis_client=redis_client,
                document_class=RestaurantCache,
                field_name="location",
                longitude=lon,
                latitude=lat,
                radius=radius_km,
                unit="km"
            )
            
            # Get full documents and apply filters
            results = []
            for doc_id, distance in results_with_distance:
                try:
                    doc = await RestaurantCache.get(doc_id)
                    if not doc:
                        continue

                    # Apply filters
                    if cuisine and doc.cuisine != cuisine.lower():
                        continue
                    if doc.rating < min_rating:
                        continue
                    if doc.price_range > max_price:
                        continue
                    if not doc.is_active:
                        continue

                    # Store as (document, distance) tuple
                    results.append((doc, distance))
                except Exception as e:
                    # Skip invalid cached documents
                    logger.warning(f"Skipping invalid cached document {doc_id}: {e}")
                    continue

            cache_time_ms = (datetime.now() - cache_start).total_seconds() * 1000

            if results:
                logger.info(
                    f"⚡ Redis cache HIT: {len(results)} results in {cache_time_ms:.1f}ms"
                )
                return results
            else:
                logger.info(
                    f"💨 Redis cache MISS (took {cache_time_ms:.1f}ms, falling back to PostgreSQL)"
                )

        # === CACHE MISS - QUERY POSTGRESQL ===
        db_start = datetime.now()

        point = ST_SetSRID(ST_MakePoint(lon, lat), 4326)

        # Build PostgreSQL query with PostGIS
        query = self.db.query(RestaurantDB).filter(
            ST_DWithin(
                RestaurantDB.location,
                point,
                radius_km * 1000  # meters
            ),
            RestaurantDB.is_active == True,
            RestaurantDB.rating >= min_rating,
            RestaurantDB.price_range <= max_price
        )

        if cuisine:
            query = query.filter(RestaurantDB.cuisine == cuisine.lower())

        db_results = query.all()

        db_time_ms = (datetime.now() - db_start).total_seconds() * 1000
        logger.info(
            f"💾 PostgreSQL: {len(db_results)} results in {db_time_ms:.1f}ms"
        )

        # Cache these results for next time
        if use_cache and db_results:
            logger.info("📝 Caching results in Redis...")
            await self._cache_results(db_results)

        # Convert to cache format with distances for consistent API
        return await self._db_to_cache_format(db_results, user_lat=lat, user_lon=lon)

    async def _cache_results(self, db_results: List[RestaurantDB]):
        """
        Cache PostgreSQL results in Redis

        Only caches restaurants that aren't already cached
        """
        cached_count = 0

        for db_restaurant in db_results:
            # Extract coordinates from PostGIS geography
            # Cast geography to geometry to use ST_Y/ST_X
            coords = self.db.query(
                func.ST_Y(cast(RestaurantDB.location, Geometry)),
                func.ST_X(cast(RestaurantDB.location, Geometry))
            ).filter_by(id=db_restaurant.id).first()

            if not coords:
                continue

            lat, lon = coords

            # Create cache entry
            cache_entry = RestaurantCache(
                db_id=db_restaurant.id,
                osm_id=db_restaurant.osm_id,
                name=db_restaurant.name,
                location=GeoPoint(latitude=lat, longitude=lon),
                address=str(db_restaurant.address) if db_restaurant.address else "",
                city=db_restaurant.city,
                cuisine=db_restaurant.cuisine,
                price_range=db_restaurant.price_range,
                rating=db_restaurant.rating,
                accepts_delivery=db_restaurant.accepts_delivery,
                outdoor_seating=db_restaurant.outdoor_seating,
                takeaway=db_restaurant.takeaway,
                wheelchair_accessible=db_restaurant.wheelchair_accessible,
                opening_hours=db_restaurant.opening_hours or {},
                phone=db_restaurant.phone,
                website=db_restaurant.website,
            )

            await cache_entry.insert()
            cached_count += 1

        logger.info(f"✅ Cached {cached_count} new restaurants")

    async def _db_to_cache_format(
        self,
        db_results: List[RestaurantDB],
        user_lat: float,
        user_lon: float
    ) -> List[tuple[RestaurantCache, float]]:
        """
        Convert PostgreSQL results to RestaurantCache format with distances

        This ensures the API always returns the same format,
        whether data came from cache or database
        """
        from geoalchemy2.functions import ST_Distance

        cache_results = []
        user_point = ST_SetSRID(ST_MakePoint(user_lon, user_lat), 4326)

        for db_restaurant in db_results:
            # Extract coordinates
            # Cast geography to geometry to use ST_Y/ST_X
            coords = self.db.query(
                func.ST_Y(cast(RestaurantDB.location, Geometry)),
                func.ST_X(cast(RestaurantDB.location, Geometry))
            ).filter_by(id=db_restaurant.id).first()

            if not coords:
                continue

            lat, lon = coords

            # Calculate distance using PostGIS
            distance_m = self.db.query(
                ST_Distance(
                    RestaurantDB.location,
                    user_point
                )
            ).filter_by(id=db_restaurant.id).scalar()

            distance_km = distance_m / 1000.0 if distance_m else 0.0

            # Create RestaurantCache object (not saved to Redis)
            cache_obj = RestaurantCache(
                db_id=db_restaurant.id,
                osm_id=db_restaurant.osm_id,
                name=db_restaurant.name,
                location=GeoPoint(latitude=lat, longitude=lon),
                address=str(db_restaurant.address) if db_restaurant.address else "",
                city=db_restaurant.city,
                cuisine=db_restaurant.cuisine,
                price_range=db_restaurant.price_range,
                rating=db_restaurant.rating,
                accepts_delivery=db_restaurant.accepts_delivery,
                outdoor_seating=db_restaurant.outdoor_seating,
                takeaway=db_restaurant.takeaway,
                wheelchair_accessible=db_restaurant.wheelchair_accessible,
                opening_hours=db_restaurant.opening_hours or {},
                phone=db_restaurant.phone,
                website=db_restaurant.website,
            )

            cache_results.append((cache_obj, distance_km))

        return cache_results

    async def warm_cache(self, city: str) -> int:
        """
        Pre-populate Redis cache with all restaurants in a city

        Args:
            city: City name

        Returns:
            Number of restaurants cached
        """
        logger.info(f"🔥 Warming Redis cache for {city}...")

        restaurants = self.db.query(RestaurantDB).filter_by(
            city=city,
            is_active=True
        ).all()

        logger.info(f"Found {len(restaurants)} active restaurants in {city}")

        await self._cache_results(restaurants)

        return len(restaurants)

    def invalidate_cache(self, restaurant_id: int):
        """
        Invalidate cache entry for a specific restaurant

        Call this when restaurant data is updated in PostgreSQL
        """
        # This would delete from Redis
        # Implementation left as exercise
        pass
