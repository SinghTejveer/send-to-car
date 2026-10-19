"""Constants for Send to Car."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "send_to_car"

CONF_CAR_DEVICE: Final = "car_device"
CONF_WAKE: Final = "wake_before_send"
CONF_GOOGLE_KEY: Final = "google_places_key"
CONF_ZONE: Final = "search_zone"
CONF_COUNTRY: Final = "country"
CONF_POSTCODES: Final = "uk_postcodes"
CONF_CALENDARS: Final = "calendars"
CONF_SUGGEST_FAVOURITES: Final = "suggest_favourites"
CONF_SUGGEST_ZONES: Final = "suggest_zones"

DEFAULT_ZONE: Final = "zone.home"
DEFAULT_COUNTRY: Final = "GB"

ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_QUERY: Final = "query"
ATTR_SESSION: Final = "session"
ATTR_PLACE_ID: Final = "place_id"
ATTR_NAME: Final = "name"
ATTR_ADDRESS: Final = "address"

SERVICE_SEARCH: Final = "search"
SERVICE_SEND: Final = "send"
SERVICE_ADD_FAVOURITE: Final = "add_favourite"
SERVICE_REMOVE_FAVOURITE: Final = "remove_favourite"
SERVICE_SUGGESTIONS: Final = "suggestions"

CARD_URL: Final = "/send_to_car/send-to-car-card.js"

MIN_QUERY: Final = 3
MAX_QUERY: Final = 120
MAX_RESULTS: Final = 5
MAX_RECENT: Final = 10
SEARCH_RADIUS_M: Final = 50000.0
HTTP_TIMEOUT_S: Final = 8

SRC_GOOGLE: Final = "google"
SRC_OSM: Final = "osm"
SRC_POSTCODE: Final = "postcode"
SRC_FAVOURITE: Final = "favourite"
SRC_RECENT: Final = "recent"

STORAGE_VERSION: Final = 1
