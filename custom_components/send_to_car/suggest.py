"""What the card shows before you type: today's calendar stops, favourites, recent places and zones, plus the car's battery and range."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .cars import car_by_device, car_status
from .const import CONF_CALENDARS, CONF_CAR_DEVICE, CONF_SUGGEST_FAVOURITES, CONF_SUGGEST_ZONES, SRC_FAVOURITE, SRC_RECENT
from .finder import Finder, public
from .search import distance_m, to_float

_LOGGER = logging.getLogger(__name__)
MAX_EACH = 5


def _when(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return dt_util.as_local(value)
    if isinstance(value, str):
        parsed = dt_util.parse_datetime(value)
        return dt_util.as_local(parsed) if parsed else None
    return None


async def calendar_stops(hass: HomeAssistant, calendars: list[str]) -> list[dict[str, Any]]:
    """The rest of today's events that have a location, earliest first. A calendar that fails is skipped."""
    if not calendars or not hass.services.has_service("calendar", "get_events"):
        return []
    now = dt_util.now()
    end = dt_util.start_of_local_day(now) + timedelta(days=1)
    try:
        resp = await hass.services.async_call(
            "calendar",
            "get_events",
            {"start_date_time": now, "end_date_time": end},
            target={"entity_id": calendars},
            blocking=True,
            return_response=True,
        )
    except HomeAssistantError as err:
        _LOGGER.debug("Calendar events could not be read: %s", err)
        return []
    out: list[dict[str, Any]] = []
    for entity_id, body in (resp or {}).items():
        for ev in (body or {}).get("events") or []:
            location = (ev.get("location") or "").strip()
            if not location:
                continue
            start = _when(ev.get("start"))
            out.append(
                {
                    "source": "calendar",
                    "name": ev.get("summary") or location,
                    "address": location,
                    "time": start.strftime("%H:%M") if start and ("T" in str(ev.get("start")) or isinstance(ev.get("start"), datetime)) else None,
                    "start": start.isoformat() if start else None,
                    "calendar": entity_id,
                }
            )
    out.sort(key=lambda e: e["start"] or "")
    return out[:MAX_EACH]


def zones(hass: HomeAssistant, here: tuple[float, float]) -> list[dict[str, Any]]:
    out = []
    for st in hass.states.async_all("zone"):
        lat, lon = to_float(st.attributes.get("latitude")), to_float(st.attributes.get("longitude"))
        if lat is None or lon is None or st.attributes.get("passive"):
            continue
        d = distance_m(here, (lat, lon))
        out.append(
            {
                "source": "zone",
                "name": st.name,
                "address": "",
                "latitude": lat,
                "longitude": lon,
                "place_id": None,
                "distance_km": round(d / 1000, 1),
                "distance_mi": round(d / 1609.344, 1),
                "duplicates": 0,
            }
        )
    return sorted(out, key=lambda z: z["distance_km"])[:MAX_EACH]


async def suggestions(hass: HomeAssistant, finder: Finder) -> dict[str, Any]:
    conf = finder.conf
    here = finder.centre()
    car = car_by_device(hass, conf.get(CONF_CAR_DEVICE, ""))

    def saved(kind: str, src: str) -> list[dict[str, Any]]:
        return [public({**p, "src": src, "distance_m": distance_m(here, (p["lat"], p["lon"]))}) for p in finder.saved[kind][:MAX_EACH]]

    show_saved = conf.get(CONF_SUGGEST_FAVOURITES, True)
    return {
        "car": {"name": car.name, **car_status(hass, car.device_id)} if car else None,
        "google": bool(finder.key),
        "calendar": await calendar_stops(hass, list(conf.get(CONF_CALENDARS) or [])),
        "favourites": saved("favourites", SRC_FAVOURITE) if show_saved else [],
        "recent": saved("recent", SRC_RECENT) if show_saved else [],
        "zones": zones(hass, here) if conf.get(CONF_SUGGEST_ZONES, True) else [],
        "last": finder.last,
    }
