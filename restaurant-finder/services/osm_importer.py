"""Fetch restaurant data from OpenStreetMap"""
import logging
import requests
from typing import List, Dict, Optional
from config import settings

logger = logging.getLogger(__name__)


class OSMImporter:
    """
    Fetch restaurant data from OpenStreetMap using Overpass API

    The Overpass API allows querying OSM data with a custom query language.
    Rate limit: ~1 request/second, be respectful!
    """

    def __init__(self):
        self.overpass_url = settings.OSM_OVERPASS_URL
        self.timeout = settings.OSM_TIMEOUT_SECONDS

    def fetch_restaurants(
        self,
        city: str,
        country: str = "Italy",
        admin_level: int = 8
    ) -> List[Dict]:
        """
        Fetch all restaurants in a city from OpenStreetMap

        Args:
            city: City name (e.g., "Roma", "Milano")
            country: Country name (default: "Italy")
            admin_level: OSM admin level (8 = city, 6 = province)

        Returns:
            List of restaurant dictionaries with OSM data

        Note:
            This can take 20-60 seconds for large cities!
            OSM data quality varies - some fields may be missing.
        """

        logger.info(f"🌍 Fetching restaurants from OpenStreetMap for {city}, {country}...")

        # Overpass QL query
        # Finds all nodes and ways tagged as restaurants in the city
        query = f"""
        [out:json][timeout:{self.timeout}];
        area[name="{city}"]["admin_level"="{admin_level}"]->.searchArea;
        (
          node["amenity"="restaurant"](area.searchArea);
          way["amenity"="restaurant"](area.searchArea);
        );
        out center;
        """

        try:
            response = requests.post(
                self.overpass_url,
                data={"data": query},
                timeout=self.timeout
            )
            response.raise_for_status()

        except requests.exceptions.Timeout:
            logger.error(f"❌ Timeout fetching data from OSM (>{self.timeout}s)")
            return []

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error fetching data from OSM: {e}")
            return []

        data = response.json()
        elements = data.get("elements", [])

        logger.info(f"📦 Received {len(elements)} elements from OSM")

        # Parse OSM data into our format
        restaurants = []
        for element in elements:
            restaurant = self._parse_osm_element(element, city, country)
            if restaurant:
                restaurants.append(restaurant)

        logger.info(f"✅ Parsed {len(restaurants)} restaurants")
        return restaurants

    def _parse_osm_element(
        self,
        element: Dict,
        city: str,
        country: str
    ) -> Optional[Dict]:
        """
        Parse an OSM element into our restaurant format

        Args:
            element: OSM element (node or way)
            city: City name
            country: Country name

        Returns:
            Restaurant dict or None if invalid
        """

        tags = element.get("tags", {})

        # Get coordinates
        # Nodes have lat/lon directly, ways have a center point
        if element["type"] == "node":
            lat = element.get("lat")
            lon = element.get("lon")
        elif "center" in element:
            lat = element["center"].get("lat")
            lon = element["center"].get("lon")
        else:
            return None  # No coordinates

        if not lat or not lon:
            return None

        # Extract restaurant data
        restaurant = {
            "osm_id": f"osm_{element['type']}_{element['id']}",
            "name": tags.get("name", "Unknown Restaurant"),
            "latitude": lat,
            "longitude": lon,
            "city": city,
            "country": country,

            # Cuisine
            "cuisine": tags.get("cuisine", "general"),

            # Address
            "address": self._build_address(tags),

            # Contact
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "website": tags.get("website") or tags.get("contact:website"),

            # Features
            "outdoor_seating": self._parse_bool(tags.get("outdoor_seating")),
            "delivery": self._parse_bool(tags.get("delivery")),
            "takeaway": self._parse_bool(tags.get("takeaway")),
            "wheelchair": self._parse_bool(tags.get("wheelchair")),

            # Hours
            "opening_hours": tags.get("opening_hours"),
        }

        return restaurant

    def _build_address(self, tags: Dict) -> str:
        """Build address string from OSM tags"""
        parts = []

        if street := tags.get("addr:street"):
            parts.append(street)

        if housenumber := tags.get("addr:housenumber"):
            parts.append(housenumber)

        return " ".join(parts) if parts else ""

    def _parse_bool(self, value: Optional[str]) -> bool:
        """Parse OSM yes/no values to boolean"""
        if not value:
            return False

        return value.lower() in ("yes", "true", "1")
