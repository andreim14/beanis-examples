"""FastAPI application for restaurant finder"""
import logging
import math
from typing import Optional
from fastapi import FastAPI, Query, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db, init_redis_cache, close_redis
from services import RestaurantService
from models import RestaurantCache
from beanis import GeoPoint

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Restaurant Finder API",
    description="Find nearby restaurants using Redis cache + PostgreSQL",
    version="1.0.0"
)


# === Lifecycle Events ===

@app.on_event("startup")
async def startup_event():
    """Initialize Redis cache on startup"""
    logger.info("🚀 Starting Restaurant Finder API...")
    await init_redis_cache()
    logger.info("✅ Application startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    """Close Redis connection on shutdown"""
    logger.info("👋 Shutting down Restaurant Finder API...")
    await close_redis()
    logger.info("✅ Application shutdown complete")


# === API Endpoints ===

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "Restaurant Finder API",
        "version": "1.0.0"
    }


@app.get("/restaurants/nearby")
async def find_nearby_restaurants(
    lat: float = Query(..., description="Your latitude", ge=-90, le=90),
    lon: float = Query(..., description="Your longitude", ge=-180, le=180),
    radius: float = Query(2.0, description="Search radius in km", gt=0, le=50),
    cuisine: Optional[str] = Query(None, description="Filter by cuisine type"),
    min_rating: float = Query(0, description="Minimum rating", ge=0, le=5),
    max_price: int = Query(4, description="Maximum price range (1-4)", ge=1, le=4),
    limit: int = Query(1000, description="Maximum results", ge=1, le=10000),
    db: Session = Depends(get_db)
):
    """
    Find restaurants near a location

    **Example queries:**
    - `/restaurants/nearby?lat=41.8902&lon=12.4922` - All restaurants within 2km
    - `/restaurants/nearby?lat=41.8902&lon=12.4922&radius=5&cuisine=italian` - Italian within 5km
    - `/restaurants/nearby?lat=41.8902&lon=12.4922&min_rating=4.5&max_price=2` - High-rated, cheap

    **Response includes:**
    - Restaurant details (name, cuisine, rating, price)
    - Distance from your location
    - Cache age (how fresh the data is)
    """

    try:
        service = RestaurantService(db)

        # Query with cache-first strategy
        results = await service.find_nearby(
            lat=lat,
            lon=lon,
            radius_km=radius,
            cuisine=cuisine,
            min_rating=min_rating,
            max_price=max_price,
            use_cache=True
        )

        # Limit results
        results = results[:limit]

        # Format response
        restaurants = []
        for restaurant, distance_km in results:
            restaurants.append({
                "id": restaurant.db_id,
                "name": restaurant.name,
                "cuisine": restaurant.cuisine,
                "rating": restaurant.rating,
                "price_range": "$" * restaurant.price_range,
                "distance_meters": round(distance_km * 1000, 0),
                "distance_km": round(distance_km, 2),
                "location": {
                    "latitude": restaurant.location.latitude,
                    "longitude": restaurant.location.longitude,
                    "address": restaurant.address
                },
                "features": {
                    "delivery": restaurant.accepts_delivery,
                    "outdoor_seating": restaurant.outdoor_seating,
                    "takeaway": restaurant.takeaway,
                    "wheelchair_accessible": restaurant.wheelchair_accessible
                },
                "contact": {
                    "phone": restaurant.phone,
                    "website": restaurant.website
                },
                "opening_hours": restaurant.opening_hours,
                "cache_age_seconds": round(restaurant.cache_age_seconds, 1)
            })

        # Sort by distance
        restaurants.sort(key=lambda x: x["distance_meters"])

        return {
            "query": {
                "location": {"lat": lat, "lon": lon},
                "radius_km": radius,
                "filters": {
                    "cuisine": cuisine,
                    "min_rating": min_rating,
                    "max_price": max_price
                }
            },
            "total": len(restaurants),
            "results": restaurants
        }

    except Exception as e:
        logger.error(f"Error finding restaurants: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Get database and cache statistics"""
    from models import RestaurantDB

    # Postgres stats
    total_restaurants = db.query(RestaurantDB).count()
    active_restaurants = db.query(RestaurantDB).filter_by(is_active=True).count()

    # Redis stats
    cached_restaurants = await RestaurantCache.count()

    return {
        "postgresql": {
            "total_restaurants": total_restaurants,
            "active_restaurants": active_restaurants
        },
        "redis_cache": {
            "cached_restaurants": cached_restaurants,
            "cache_coverage": f"{(cached_restaurants / total_restaurants * 100):.1f}%"
                if total_restaurants > 0 else "0%"
        }
    }


@app.post("/import/area")
async def import_area(
    lat: float = Query(..., description="Center latitude"),
    lon: float = Query(..., description="Center longitude"),
    radius_km: float = Query(5.0, description="Search radius in km", gt=0, le=20),
    db: Session = Depends(get_db)
):
    """
    Import restaurants from OpenStreetMap for a specific area

    This will:
    1. Query OpenStreetMap Overpass API for restaurants
    2. Save them to PostgreSQL
    3. Cache them in Redis
    """
    from services.osm_importer import OSMImporter
    from services.restaurant_service import RestaurantService

    try:
        logger.info(f"Importing restaurants around ({lat}, {lon}) within {radius_km}km")

        # Initialize importer
        importer = OSMImporter()

        # Fetch from OpenStreetMap using bounding box
        # Calculate bounding box (approximate)
        lat_offset = radius_km / 111.0  # 1 degree lat ≈ 111 km
        lon_offset = radius_km / (111.0 * abs(math.cos(math.radians(lat))))  # adjust for longitude

        bbox = {
            "south": lat - lat_offset,
            "west": lon - lon_offset,
            "north": lat + lat_offset,
            "east": lon + lon_offset
        }

        # Fetch restaurants from OSM
        osm_data = importer.fetch_by_bbox(bbox)

        if not osm_data:
            return {
                "status": "no_results",
                "imported": 0,
                "message": "No restaurants found in this area on OpenStreetMap"
            }

        # Save to PostgreSQL
        saved_count = importer.save_to_db(osm_data, db)

        # Warm cache for this area
        service = RestaurantService(db)
        cached_count = 0

        # Get all restaurants in the area we just imported
        from models import RestaurantDB
        from geoalchemy2.functions import ST_SetSRID, ST_MakePoint, ST_DWithin

        point = ST_SetSRID(ST_MakePoint(lon, lat), 4326)
        nearby_restaurants = db.query(RestaurantDB).filter(
            ST_DWithin(
                RestaurantDB.location,
                point,
                radius_km * 1000  # meters
            ),
            RestaurantDB.is_active == True
        ).all()

        # Cache them
        if nearby_restaurants:
            await service._cache_results(nearby_restaurants)
            cached_count = len(nearby_restaurants)

        logger.info(f"✅ Imported {saved_count} new restaurants, cached {cached_count}")

        return {
            "status": "success",
            "imported": saved_count,
            "cached": cached_count,
            "total_found": len(osm_data),
            "message": f"Successfully imported {saved_count} restaurants and cached {cached_count}"
        }

    except Exception as e:
        logger.error(f"Error importing restaurants: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
