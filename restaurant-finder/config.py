"""Application configuration"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings loaded from environment variables"""

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://restaurant_user:restaurant_pass@localhost:5432/restaurant_db"
    )
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Application
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

    # OpenStreetMap
    OSM_TIMEOUT_SECONDS: int = int(os.getenv("OSM_TIMEOUT_SECONDS", "60"))
    OSM_OVERPASS_URL: str = "http://overpass-api.de/api/interpreter"


settings = Settings()
