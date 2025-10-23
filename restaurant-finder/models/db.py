"""PostgreSQL models with PostGIS support"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from geoalchemy2 import Geography
from datetime import datetime

Base = declarative_base()


class RestaurantDB(Base):
    """
    PostgreSQL model for restaurants - Source of truth

    Uses PostGIS Geography type for accurate distance calculations
    """
    __tablename__ = "restaurants"

    id = Column(Integer, primary_key=True, index=True)
    osm_id = Column(String, unique=True, index=True, nullable=False)

    # Basic info
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text)

    # Location - PostGIS geography for accurate distance calculations
    # SRID 4326 = WGS84 (standard lat/lon coordinates)
    location = Column(Geography(geometry_type='POINT', srid=4326), nullable=False)

    address = Column(String)
    city = Column(String, index=True)
    country = Column(String, default="Italy")

    # Contact
    phone = Column(String)
    website = Column(String)

    # Searchable attributes
    cuisine = Column(String, index=True)
    price_range = Column(Integer, default=2)  # 1-4 ($-$$$$)
    rating = Column(Float, default=0.0, index=True)

    # Features
    outdoor_seating = Column(Boolean, default=False)
    accepts_delivery = Column(Boolean, default=False)
    takeaway = Column(Boolean, default=False)
    wheelchair_accessible = Column(Boolean, default=False)

    # Hours
    opening_hours = Column(JSON)  # {"monday": "9:00-22:00", ...}

    # Metadata
    is_active = Column(Boolean, default=True, index=True)
    total_reviews = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    def __repr__(self):
        return f"<Restaurant(id={self.id}, name='{self.name}', cuisine='{self.cuisine}')>"
