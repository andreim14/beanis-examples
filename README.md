# Beanis Examples

Production-ready examples demonstrating [Beanis](https://github.com/andreim14/beanis) - a Redis ODM for Python with Pydantic integration.

## Examples

### 1. Restaurant Finder (Geo-Spatial Cache)

**[📁 restaurant-finder/](./restaurant-finder/)**

Build a lightning-fast restaurant finder using:
- **OpenStreetMap** for real restaurant data
- **PostgreSQL + PostGIS** as source of truth
- **Redis + Beanis** as cache layer (90% faster queries)
- **FastAPI** REST API

**Features:**
- Geo-spatial queries (find nearby restaurants)
- Cache-first strategy with fallback
- Real-world data import from OSM
- Production-ready architecture

**Performance:** 6ms (cached) vs 76ms (database) - **92% faster**

[Read the tutorial →](https://andreim14.github.io/blog/2025/using-redis-as-geo-spatial-cache/)

---

## More Examples Coming Soon

- **Real-time Leaderboard**: Gaming scores with sorted sets
- **URL Shortener**: Click tracking and analytics
- **Session Store**: User sessions with TTL
- **Job Queue**: Background task processing

## Contributing

Have an example idea? Open an issue or PR!

## License

MIT
