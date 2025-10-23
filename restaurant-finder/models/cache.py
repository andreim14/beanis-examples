"""Beanis Redis cache models"""
from beanis import Document, Indexed, GeoPoint
from typing import Optional
from datetime import datetime
from pydantic import Field


class RestaurantCache(Document):
    """
    Redis cache model - mirrors PostgreSQL data for fast queries

    Features:
    - GeoPoint for ultra-fast geo-spatial queries (Redis GEORADIUS)
    - Indexed fields create sorted sets for filtering
    - Cache metadata tracks freshness
    """

    # Source tracking
    db_id: int  # PostgreSQL ID reference
    osm_id: str  # OpenStreetMap ID

    # Core data
    name: str
    location: GeoPoint  # ⭐ Automatically creates Redis geo-spatial index
    address: str
    city: Indexed[str]  # Creates sorted set for city filtering

    # Searchable attributes (indexed for fast filtering)
    cuisine: Indexed[str]  # italian, japanese, etc.
    price_range: Indexed[int]  # 1-4 ($-$$$$)
    rating: Indexed[float]  # 0-5 stars

    # Features
    accepts_delivery: bool = True
    outdoor_seating: bool = False
    takeaway: bool = False
    wheelchair_accessible: bool = False
    opening_hours: dict = {}

    # Contact
    phone: Optional[str] = None
    website: Optional[str] = None

    # Cache metadata
    is_active: Indexed[bool] = True
    cached_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "RestaurantCache"

    @property
    def cache_age_seconds(self) -> float:
        """Calculate how old this cache entry is"""
        return (datetime.now() - self.cached_at).total_seconds()

    def is_stale(self, max_age_seconds: int = 3600) -> bool:
        """
        Check if cache entry should be refreshed

        Args:
            max_age_seconds: Maximum age in seconds (default: 1 hour)

        Returns:
            True if entry is older than max_age
        """
        return self.cache_age_seconds > max_age_seconds

    def __str__(self):
        return f"{self.name} ({self.cuisine}) - {self.rating}⭐ - {self.city}"
