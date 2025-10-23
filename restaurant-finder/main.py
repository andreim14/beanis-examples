"""FastAPI application for restaurant finder"""
import logging
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
    limit: int = Query(20, description="Maximum results", ge=1, le=100),
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

        # Calculate distance for each result
        user_location = GeoPoint(lat=lat, lon=lon)

        # Format response
        restaurants = []
        for r in results:
            distance_m = r.location.distance_to(user_location)

            restaurants.append({
                "id": r.db_id,
                "name": r.name,
                "cuisine": r.cuisine,
                "rating": r.rating,
                "price_range": "$" * r.price_range,
                "distance_meters": round(distance_m, 0),
                "distance_km": round(distance_m / 1000, 2),
                "location": {
                    "latitude": r.location.latitude,
                    "longitude": r.location.longitude,
                    "address": r.address
                },
                "features": {
                    "delivery": r.accepts_delivery,
                    "outdoor_seating": r.outdoor_seating,
                    "takeaway": r.takeaway,
                    "wheelchair_accessible": r.wheelchair_accessible
                },
                "contact": {
                    "phone": r.phone,
                    "website": r.website
                },
                "opening_hours": r.opening_hours,
                "cache_age_seconds": round(r.cache_age_seconds, 1)
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


@app.get("/restaurants/{restaurant_id}")
async def get_restaurant(
    restaurant_id: int,
    db: Session = Depends(get_db)
):
    """Get details for a specific restaurant"""
    from models import RestaurantDB

    restaurant = db.query(RestaurantDB).filter_by(id=restaurant_id).first()

    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    # Extract coordinates
    from sqlalchemy import func
    from geoalchemy2.functions import ST_Y, ST_X

    coords = db.query(
        ST_Y(RestaurantDB.location),
        ST_X(RestaurantDB.location)
    ).filter_by(id=restaurant.id).first()

    lat, lon = coords if coords else (None, None)

    return {
        "id": restaurant.id,
        "osm_id": restaurant.osm_id,
        "name": restaurant.name,
        "cuisine": restaurant.cuisine,
        "rating": restaurant.rating,
        "price_range": "$" * restaurant.price_range,
        "location": {
            "latitude": lat,
            "longitude": lon,
            "address": restaurant.address,
            "city": restaurant.city,
            "country": restaurant.country
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
        "is_active": restaurant.is_active,
        "created_at": restaurant.created_at.isoformat(),
        "updated_at": restaurant.updated_at.isoformat()
    }


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
