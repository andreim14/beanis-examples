# Restaurant Finder - Redis Cache Example

A restaurant finder API demonstrating **Redis as a cache layer** over PostgreSQL, built with Beanis ODM and FastAPI.

## Features

- **🚀 Ultra-fast geo-spatial queries** - Redis cache with sub-200ms response times
- **📍 Proximity search** - Find restaurants within customizable radius
- **🔍 Advanced filtering** - Filter by cuisine, rating, and price range
- **💾 Smart caching** - PostgreSQL as source of truth, Redis for speed
- **🌍 Real data** - Import restaurants from OpenStreetMap
- **🎨 Simple CLI demo** - Interactive demo with performance metrics

## Architecture

```
┌─────────────┐
│   FastAPI   │  (API - Port 8000)
│     API     │
└──────┬──────┘
       │
       ├─────────────┐
       ▼             ▼
┌─────────┐   ┌──────────────┐
│  Redis  │   │  PostgreSQL  │
│  Cache  │   │   + PostGIS  │
│ (Beanis)│   │ (Source DB)  │
└─────────┘   └──────────────┘
```

### Cache-First Flow

1. **Query arrives** → Check Redis cache first
2. **Cache HIT** ⚡ → Return results in ~50-200ms
3. **Cache MISS** → Query PostgreSQL (~500-1000ms)
4. **Cache warm** → Store results in Redis for next time

## Quick Start

### 1. Prerequisites

- Python 3.11+
- Docker (for PostgreSQL and Redis)

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Start Databases

```bash
# PostgreSQL with PostGIS
docker run -d --name restaurant-postgres \
  -e POSTGRES_USER=restaurant_user \
  -e POSTGRES_PASSWORD=restaurant_pass \
  -e POSTGRES_DB=restaurant_db \
  -p 5432:5432 \
  postgis/postgis:15-3.3

# Redis
docker run -d --name restaurant-redis \
  -p 6379:6379 \
  redis:7-alpine
```

### 4. Import Sample Data

Import restaurants from OpenStreetMap for any location:

```bash
# Rome, Italy
curl -X POST "http://localhost:8000/import/area?lat=41.8902&lon=12.4922&radius_km=5"

# Paris, France
curl -X POST "http://localhost:8000/import/area?lat=48.8584&lon=2.2945&radius_km=5"

# New York City, USA
curl -X POST "http://localhost:8000/import/area?lat=40.7580&lon=-73.9855&radius_km=5"
```

### 5. Start API

```bash
python main.py
```

API will be available at `http://localhost:8000`

### 6. Run Interactive Demo

```bash
python demo.py
```

This will run a series of queries showing cache performance.

## API Endpoints

### Find Nearby Restaurants

```bash
GET /restaurants/nearby?lat=41.8902&lon=12.4922&radius=2
```

**Parameters:**
- `lat` (required) - Latitude
- `lon` (required) - Longitude
- `radius` (optional) - Search radius in km (default: 2.0)
- `cuisine` (optional) - Filter by cuisine type
- `min_rating` (optional) - Minimum rating (0-5)
- `max_price` (optional) - Maximum price range (1-4)
- `limit` (optional) - Max results (default: 1000)

**Response:**

```json
{
  "query": {
    "location": {"lat": 41.8902, "lon": 12.4922},
    "radius_km": 2.0,
    "filters": {
      "cuisine": null,
      "min_rating": 0,
      "max_price": 4
    }
  },
  "total": 156,
  "results": [
    {
      "id": 42,
      "name": "Trattoria Roma",
      "cuisine": "italian",
      "rating": 4.5,
      "price_range": "$$",
      "distance_meters": 120,
      "distance_km": 0.12,
      "location": {
        "latitude": 41.8912,
        "longitude": 12.4935,
        "address": "Via del Corso 123"
      },
      "features": {
        "delivery": true,
        "outdoor_seating": true,
        "takeaway": true,
        "wheelchair_accessible": false
      },
      "contact": {
        "phone": "+39 06 1234567",
        "website": "https://example.com"
      },
      "cache_age_seconds": 45.2
    }
  ]
}
```

### Import Restaurants from OpenStreetMap

```bash
POST /import/area?lat=41.8902&lon=12.4922&radius_km=5
```

Imports restaurants from OpenStreetMap and caches them in Redis.

### Get Statistics

```bash
GET /stats
```

Returns database and cache statistics:

```json
{
  "postgresql": {
    "total_restaurants": 5234,
    "active_restaurants": 5234
  },
  "redis_cache": {
    "cached_restaurants": 5234,
    "cache_coverage": "100.0%"
  }
}
```

## Performance

Real-world benchmarks with 2,643 restaurants (Paris dataset):

| Query Type | First Call (DB) | Cached Call | Speedup |
|-----------|----------------|-------------|---------|
| All restaurants (2km) | ~650ms | ~620ms | Consistent |
| With cuisine filter | ~680ms | ~615ms | ~10% faster |
| Small dataset (NYC) | ~300ms | ~270ms | ~10% faster |

**Note:** With proper indexes, Redis provides consistent sub-second response times and eliminates database load for repeated queries.

## Project Structure

```
restaurant-finder/
├── demo.py                 # CLI demo script
├── main.py                 # FastAPI application
├── database.py             # Database connections
├── models/
│   ├── db.py              # PostgreSQL models (SQLAlchemy)
│   └── cache.py           # Redis cache models (Beanis)
├── services/
│   ├── restaurant_service.py  # Business logic with cache-first strategy
│   └── osm_importer.py        # OpenStreetMap data import
└── requirements.txt
```

## Key Technologies

- **[Beanis](https://github.com/andreim14/beanis)** - Redis ODM with Pydantic v2
- **FastAPI** - Modern Python web framework
- **SQLAlchemy** - SQL toolkit and ORM
- **GeoAlchemy2** - PostGIS support for SQLAlchemy
- **PostgreSQL + PostGIS** - Geo-spatial database
- **Redis** - In-memory cache with geo-spatial indexing

## Redis Cache Model

```python
from beanis import Document, Indexed, GeoPoint
from beanis.odm.indexes import IndexedField
from typing_extensions import Annotated

class RestaurantCache(Document):
    db_id: int  # Reference to PostgreSQL
    osm_id: str
    name: str

    # Geo-spatial index for proximity search
    location: Annotated[GeoPoint, IndexedField()]

    # Regular indexes for filtering
    cuisine: Indexed(str)
    city: Indexed(str)
    price_range: Indexed(int)
    rating: Indexed(float)
    is_active: Indexed(bool)

    # Additional fields
    address: Optional[str] = ""
    phone: Optional[str] = None
    website: Optional[str] = None
    opening_hours: Optional[Dict] = {}
    accepts_delivery: bool = False
    outdoor_seating: bool = False
    takeaway: bool = False
    wheelchair_accessible: bool = False

    class Settings:
        name = "restaurant_cache"
        indexes = ["location", "cuisine", "city", "price_range", "rating", "is_active"]
```

## Geo-Spatial Queries with Beanis

The core feature - finding nearby restaurants using Redis geo-spatial indexes:

```python
from beanis.odm.indexes import IndexManager

# Find restaurants within radius with distances
results = await IndexManager.find_by_geo_radius_with_distance(
    redis_client=redis,
    document_class=RestaurantCache,
    field_name="location",
    longitude=12.4922,
    latitude=41.8902,
    radius=2,
    unit="km"
)

# Returns: [(doc_id, distance_km), ...]
for doc_id, distance in results:
    restaurant = await RestaurantCache.get(doc_id)
    print(f"{restaurant.name}: {distance}km away")
```

## Cache-First Query Strategy

The `RestaurantService` implements an intelligent cache-first strategy:

```python
async def find_nearby(self, lat, lon, radius_km, **filters):
    # 1. Try Redis cache first
    results = await IndexManager.find_by_geo_radius_with_distance(...)

    if results:
        logger.info("⚡ Redis cache HIT")
        return results

    # 2. Cache miss - query PostgreSQL
    logger.info("💾 PostgreSQL fallback")
    db_results = self.db.query(RestaurantDB).filter(
        ST_DWithin(RestaurantDB.location, point, radius_km * 1000)
    ).all()

    # 3. Cache the results for next time
    await self._cache_results(db_results)

    return db_results
```

## Example Usage

### Python

```python
import requests

# Find Italian restaurants near Colosseum
response = requests.get(
    "http://localhost:8000/restaurants/nearby",
    params={
        "lat": 41.8902,
        "lon": 12.4922,
        "radius": 2.0,
        "cuisine": "italian",
        "min_rating": 4.0,
        "max_price": 3
    }
)

data = response.json()
print(f"Found {data['total']} restaurants")

for r in data['results'][:5]:
    print(f"{r['name']} - {r['distance_km']}km - {r['price_range']}")
```

### cURL

```bash
# Find all restaurants within 5km
curl "http://localhost:8000/restaurants/nearby?lat=41.8902&lon=12.4922&radius=5"

# Filter by cuisine
curl "http://localhost:8000/restaurants/nearby?lat=41.8902&lon=12.4922&cuisine=italian"

# High-rated, budget-friendly
curl "http://localhost:8000/restaurants/nearby?lat=41.8902&lon=12.4922&min_rating=4.5&max_price=2"
```

## Development

### Clearing Cache

```bash
# Via Redis CLI
docker exec restaurant-redis redis-cli FLUSHDB

# Or restart Redis
docker restart restaurant-redis
```

### Checking Cache Contents

```bash
# Check cache size
docker exec restaurant-redis redis-cli DBSIZE

# View all keys
docker exec restaurant-redis redis-cli KEYS "*"

# Check geo-spatial index
docker exec restaurant-redis redis-cli GEORADIUS restaurant_cache:location 12.4922 41.8902 2 km
```

### Database Connection

```bash
# Connect to PostgreSQL
docker exec -it restaurant-postgres psql -U restaurant_user -d restaurant_db

# Check tables
\dt

# Count restaurants
SELECT COUNT(*) FROM restaurants;

# Check geo-spatial data
SELECT name, ST_AsText(location) FROM restaurants LIMIT 5;
```

## Troubleshooting

### Port Already in Use

```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9
```

### Database Connection Errors

```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Check Redis is running
docker ps | grep redis

# Restart databases
docker restart restaurant-postgres restaurant-redis
```

### Cache Not Working

```bash
# Verify Redis connection
docker exec restaurant-redis redis-cli PING

# Expected output: PONG

# Check cache size
docker exec restaurant-redis redis-cli DBSIZE
```

## License

MIT

## Credits

- Restaurant data from [OpenStreetMap](https://www.openstreetmap.org/)
- Built with [Beanis](https://github.com/andreim14/beanis) Redis ODM
- Geo-spatial queries powered by Redis GEORADIUS

## Learn More

- [Beanis Documentation](https://github.com/andreim14/beanis)
- [Redis Geo Commands](https://redis.io/commands/?group=geo)
- [PostGIS Documentation](https://postgis.net/documentation/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
