"""Searching, resolving a place to a position, and the favourites and recent places of one car (one config entry)."""

from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from . import providers as pv
from .const import (
    CONF_COUNTRY,
    CONF_GOOGLE_KEY,
    CONF_POSTCODES,
    CONF_ZONE,
    DEFAULT_COUNTRY,
    DEFAULT_ZONE,
    DOMAIN,
    MAX_QUERY,
    MAX_RECENT,
    MIN_QUERY,
    SRC_FAVOURITE,
    SRC_RECENT,
    STORAGE_VERSION,
)
from .search import Result, distance_m, matches_words, merge, norm, source_of, to_float

_LOGGER = logging.getLogger(__name__)


def _place(r: Result) -> dict[str, Any]:
    """What is kept of a place in favourites and recent: no source, no distance."""
    return {"name": r.get("name") or "", "address": r.get("address") or "", "lat": r["lat"], "lon": r["lon"], "place_id": r.get("place_id")}


class Finder:
    """The search and the saved places for one config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store: Store[dict[str, list[dict[str, Any]]]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.saved: dict[str, list[dict[str, Any]]] = {"favourites": [], "recent": []}
        self.last: dict[str, Any] | None = None
        self._dirty = False

    async def async_load(self) -> None:
        data = await self.store.async_load()
        if data:
            self.saved = {"favourites": list(data.get("favourites") or []), "recent": list(data.get("recent") or [])}

    def _save(self) -> None:
        self._dirty = True
        self.store.async_delay_save(lambda: self.saved, 2)

    async def async_flush(self) -> None:
        """Write a pending change now (on unload or reload), instead of waiting for the delayed save."""
        if self._dirty:
            await self.store.async_save(self.saved)
            self._dirty = False

    # ------------------------------------------------ settings
    @property
    def conf(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    @property
    def key(self) -> str | None:
        return (self.conf.get(CONF_GOOGLE_KEY) or "").strip() or None

    @property
    def country(self) -> str:
        return self.conf.get(CONF_COUNTRY) or DEFAULT_COUNTRY

    def centre(self) -> tuple[float, float]:
        """Search near this zone (home by default), else Home Assistant's own location."""
        st = self.hass.states.get(self.conf.get(CONF_ZONE) or DEFAULT_ZONE)
        if st:
            lat, lon = to_float(st.attributes.get("latitude")), to_float(st.attributes.get("longitude"))
            if lat is not None and lon is not None:
                return lat, lon
        return self.hass.config.latitude, self.hass.config.longitude

    @property
    def _session(self):
        return async_get_clientsession(self.hass)

    # ------------------------------------------------ search
    def mine(self, query: str, here: tuple[float, float]) -> list[Result]:
        """Favourites, then recent places, whose name or address has every word of the query."""
        out: list[Result] = []
        for src, items in ((SRC_FAVOURITE, self.saved["favourites"]), (SRC_RECENT, self.saved["recent"])):
            for it in items:
                if it.get("lat") is not None and matches_words(query, it.get("name"), it.get("address")):
                    out.append({**it, "src": src, "distance_m": distance_m(here, (it["lat"], it["lon"]))})
        return out

    async def search(self, query: str, session_token: str | None = None) -> dict[str, Any]:
        """Up to five places for what was typed: your own, a postcode, then Google (or OpenStreetMap)."""
        q = (query or "").strip()[:MAX_QUERY]
        if len(q) < MIN_QUERY:
            return {"query": q, "results": [], "source": "none", "notes": []}
        here, key, notes = self.centre(), self.key, []
        google: list[Result] = []
        postcode: list[Result] = []
        osm: list[Result] = []
        if self.conf.get(CONF_POSTCODES, True) and self.country.upper() == "GB":
            try:
                postcode = await pv.postcode(self._session, q, here)
            except pv.ProviderError as err:
                notes.append(f"postcodes.io: {err}")
        if key:
            try:
                google = await pv.google_autocomplete(self._session, key, q, here, self.country, session_token)
            except pv.ProviderError as err:
                notes.append(f"Google: {err}")
                _LOGGER.warning("Google Places search failed: %s", err)
        if not google:
            try:
                osm = await pv.photon(self._session, q, here, self.country)
            except pv.ProviderError as err:
                notes.append(f"OpenStreetMap: {err}")
        results = merge(google, postcode, osm, self.mine(q, here))
        return {"query": q, "results": [_public(r) for r in results], "source": source_of(google, osm), "notes": notes}

    async def resolve(
        self,
        *,
        place_id: str | None = None,
        lat: Any = None,
        lon: Any = None,
        query: str | None = None,
        name: str | None = None,
        address: str | None = None,
        session_token: str | None = None,
    ) -> Result:
        """A place with a position: from coordinates, a Google place id, or free text (a postcode, an address, a calendar location)."""
        la, lo = to_float(lat), to_float(lon)
        if la is not None and lo is not None:
            return {"src": "given", "name": name or f"{la:.5f}, {lo:.5f}", "address": address or "", "lat": la, "lon": lo, "place_id": place_id}
        here, key = self.centre(), self.key
        try:
            if place_id:
                if not key:
                    raise ServiceValidationError("A Google place id needs a Google Places key in the integration's settings")
                r = await pv.google_details(self._session, key, place_id, session_token)
                if r:
                    return {**r, "name": r["name"] or name or "", "address": r["address"] or address or ""}
            text = (query or name or "").strip()[:200]
            if text:
                for mine in self.mine(text, here)[:1]:
                    if norm(mine["name"]) == norm(text):
                        return mine
                if key:
                    r = await pv.google_text(self._session, key, text, here, self.country)
                    if r:
                        return r
                found = (await pv.postcode(self._session, text, here)) or (await pv.photon(self._session, text, here, self.country))
                if found:
                    return found[0]
        except pv.ProviderError as err:
            raise ServiceValidationError(f"Could not look the place up: {err}") from err
        raise ServiceValidationError(f"Could not find “{query or name or place_id}”. Try adding the town or the postcode.")

    # ------------------------------------------------ saved places
    def add_recent(self, r: Result) -> None:
        p = _place(r)
        rest = [
            x for x in self.saved["recent"] if not (norm(x["name"]) == norm(p["name"]) and abs(x["lat"] - p["lat"]) < 1e-4 and abs(x["lon"] - p["lon"]) < 1e-4)
        ]
        self.saved["recent"] = [p, *rest][:MAX_RECENT]
        self.last = {**p, "at": time.time()}
        self._save()

    def add_favourite(self, r: Result) -> bool:
        """-> False when it is already a favourite."""
        p = _place(r)
        if any(norm(x["name"]) == norm(p["name"]) and abs(x["lat"] - p["lat"]) < 1e-4 for x in self.saved["favourites"]):
            return False
        self.saved["favourites"].append(p)
        self._save()
        return True

    def remove_favourite(self, name: str) -> bool:
        before = len(self.saved["favourites"])
        self.saved["favourites"] = [x for x in self.saved["favourites"] if norm(x["name"]) != norm(name)]
        if len(self.saved["favourites"]) != before:
            self._save()
            return True
        return False


def _public(r: Result) -> dict[str, Any]:
    """A result as the search action returns it."""
    d = r.get("distance_m")
    return {
        "source": r["src"],
        "name": r.get("name") or "",
        "address": r.get("address") or "",
        "latitude": r.get("lat"),
        "longitude": r.get("lon"),
        "place_id": r.get("place_id"),
        "distance_km": round(d / 1000, 1) if d is not None else None,
        "distance_mi": round(d / 1609.344, 1) if d is not None else None,
        "duplicates": r.get("duplicates", 0),
    }
