"""The search providers: Google Places (New), postcodes.io and Photon (OpenStreetMap). Async, no Home Assistant state.

Every call takes an aiohttp session, so Home Assistant's shared session is used and tests can pass a fake one.
Searches go from Home Assistant to the provider only; the Google key is sent in a header, never in a URL.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import aiohttp

from .const import HTTP_TIMEOUT_S, SEARCH_RADIUS_M, SRC_GOOGLE, SRC_OSM, SRC_POSTCODE
from .search import Result, distance_m, parse_postcode

GOOGLE = "https://places.googleapis.com/v1"
POSTCODES = "https://api.postcodes.io"
PHOTON = "https://photon.komoot.io/api/"
USER_AGENT = "HomeAssistant-SendToCar/0.1 (+https://github.com/SinghTejveer/send-to-car)"
FIELDS_DETAIL = "id,displayName,formattedAddress,location"
FIELDS_TEXT = "places.id,places.displayName,places.formattedAddress,places.location"


class ProviderError(Exception):
    """A provider could not answer."""


class InvalidKey(ProviderError):
    """Google refused the API key."""


async def _json(
    session: aiohttp.ClientSession, method: str, url: str, *, body: Any = None, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None
) -> Any:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
    try:
        async with session.request(method, url, json=body, headers=hdrs, params=params, timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_S)) as resp:
            if resp.status in (400, 401, 403) and "googleapis" in url:
                raise InvalidKey(f"Google answered {resp.status}")
            if resp.status == 404:
                return {}
            if resp.status >= 400:
                raise ProviderError(f"{url.split('/')[2]} answered {resp.status}")
            return await resp.json(content_type=None)
    except (TimeoutError, aiohttp.ClientError) as err:
        raise ProviderError(f"{url.split('/')[2]}: {err.__class__.__name__}") from err


def _google_headers(key: str, mask: str | None = None) -> dict[str, str]:
    h = {"X-Goog-Api-Key": key}
    if mask:
        h["X-Goog-FieldMask"] = mask
    return h


def _bias(here: tuple[float, float]) -> dict[str, Any]:
    return {"circle": {"center": {"latitude": here[0], "longitude": here[1]}, "radius": SEARCH_RADIUS_M}}


def _region(country: str) -> str:
    return (country or "").lower()


async def google_autocomplete(
    session: aiohttp.ClientSession, key: str, query: str, here: tuple[float, float], country: str, session_token: str | None = None
) -> list[Result]:
    """Up to five Google suggestions, biased to the search centre. Positions come later, from place details."""
    body: dict[str, Any] = {"input": query, "origin": {"latitude": here[0], "longitude": here[1]}, "locationBias": _bias(here)}
    if country:
        body["includedRegionCodes"] = [_region(country)]
    if session_token:
        body["sessionToken"] = session_token
    data = await _json(session, "POST", f"{GOOGLE}/places:autocomplete", body=body, headers=_google_headers(key))
    out: list[Result] = []
    for s in data.get("suggestions") or []:
        p = s.get("placePrediction")
        if not p:
            continue
        sf = p.get("structuredFormat") or {}
        name = (sf.get("mainText") or {}).get("text") or (p.get("text") or {}).get("text") or ""
        dm = p.get("distanceMeters")
        out.append(
            {
                "src": SRC_GOOGLE,
                "place_id": p.get("placeId"),
                "name": name,
                "address": (sf.get("secondaryText") or {}).get("text") or "",
                "lat": None,
                "lon": None,
                "distance_m": float(dm) if isinstance(dm, (int, float)) else None,
            }
        )
    return out


async def google_details(session: aiohttp.ClientSession, key: str, place_id: str, session_token: str | None = None) -> Result | None:
    """The position, name and address of a Google place id."""
    params = {"sessionToken": session_token} if session_token else None
    d = await _json(session, "GET", f"{GOOGLE}/places/{quote(place_id, safe='')}", headers=_google_headers(key, FIELDS_DETAIL), params=params)
    loc = d.get("location") or {}
    if loc.get("latitude") is None:
        return None
    return {
        "src": SRC_GOOGLE,
        "place_id": d.get("id") or place_id,
        "name": (d.get("displayName") or {}).get("text") or "",
        "address": d.get("formattedAddress") or "",
        "lat": loc["latitude"],
        "lon": loc["longitude"],
        "distance_m": None,
    }


async def google_text(session: aiohttp.ClientSession, key: str, text: str, here: tuple[float, float], country: str) -> Result | None:
    """The best Google match for free text, such as a calendar event's location."""
    body: dict[str, Any] = {"textQuery": text, "locationBias": _bias(here)}
    if country:
        body["regionCode"] = _region(country)
    d = await _json(session, "POST", f"{GOOGLE}/places:searchText", body=body, headers=_google_headers(key, FIELDS_TEXT))
    p = (d.get("places") or [None])[0]
    if not p or (p.get("location") or {}).get("latitude") is None:
        return None
    loc = p["location"]
    return {
        "src": SRC_GOOGLE,
        "place_id": p.get("id"),
        "name": (p.get("displayName") or {}).get("text") or text,
        "address": p.get("formattedAddress") or "",
        "lat": loc["latitude"],
        "lon": loc["longitude"],
        "distance_m": distance_m(here, (loc["latitude"], loc["longitude"])),
    }


async def postcode(session: aiohttp.ClientSession, query: str, here: tuple[float, float]) -> list[Result]:
    """An exact UK postcode (or its outward area) from postcodes.io; [] when the query is not a postcode."""
    pc = parse_postcode(query)
    if not pc:
        return []
    outward, inward = pc
    if inward:
        r = (await _json(session, "GET", f"{POSTCODES}/postcodes/{quote(outward + inward)}")).get("result") or {}
        if r.get("latitude") is None:
            return []
        where = ", ".join(x for x in (r.get("admin_ward"), r.get("admin_district")) if x)
        name, addr = f"{outward} {inward}", f"{where} · the centre of the postcode" if where else "The centre of the postcode"
    else:
        r = (await _json(session, "GET", f"{POSTCODES}/outcodes/{quote(outward)}")).get("result") or {}
        if r.get("latitude") is None:
            return []
        where = ", ".join((r.get("admin_district") or [])[:2])
        name, addr = outward, f"{where} · the centre of the area" if where else "The centre of the area"
    pos = (r["latitude"], r["longitude"])
    return [{"src": SRC_POSTCODE, "place_id": None, "name": name, "address": addr, "lat": pos[0], "lon": pos[1], "distance_m": distance_m(here, pos)}]


async def photon(session: aiohttp.ClientSession, query: str, here: tuple[float, float], country: str) -> list[Result]:
    """OpenStreetMap places from Photon, biased to the search centre and kept to the country."""
    d = await _json(session, "GET", PHOTON, params={"q": query, "limit": 6, "lat": here[0], "lon": here[1], "lang": "en"})
    out: list[Result] = []
    for f in d.get("features") or []:
        p = f.get("properties") or {}
        c = (f.get("geometry") or {}).get("coordinates") or [None, None]
        if country and p.get("countrycode") and p["countrycode"].upper() != country.upper():
            continue
        name = p.get("name") or " ".join(x for x in (p.get("housenumber"), p.get("street")) if x)
        if not name or len(c) < 2 or c[1] is None:
            continue
        addr = ", ".join(x for x in (p.get("street") if p.get("name") else None, p.get("city") or p.get("town") or p.get("county"), p.get("postcode")) if x)
        out.append({"src": SRC_OSM, "place_id": None, "name": name, "address": addr, "lat": c[1], "lon": c[0], "distance_m": distance_m(here, (c[1], c[0]))})
    return out
