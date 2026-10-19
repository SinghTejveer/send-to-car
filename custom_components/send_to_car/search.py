"""Merging search results: pure functions, no Home Assistant, no network.

A result is a dict:
    src      one of google, osm, postcode, favourite, recent
    name     what to show
    address  the line under it
    lat/lon  position, or None (Google autocomplete gives a place id instead; the position is looked up when it is picked)
    place_id Google's id, or None
    distance_m  straight-line metres from the search centre, or None
    duplicates  how many results share this name (0 when it is unique), set by merge()
"""

from __future__ import annotations

import math
import re
from typing import Any

from .const import MAX_RESULTS, SRC_GOOGLE, SRC_OSM

Result = dict[str, Any]

POSTCODE = re.compile(r"^\s*([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})?\s*$", re.IGNORECASE)
POSTCODE_IN = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE)
SAME_PLACE_M = 50.0
EARTH_R_M = 6371008.8


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Straight-line metres between two (lat, lon) points."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return EARTH_R_M * 2 * math.asin(math.sqrt(h))


def to_float(value: Any) -> float | None:
    """A finite float, or None for '', 'None', missing or not a number."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def norm(text: Any) -> str:
    """Lower case, letters and digits only, single spaces."""
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def parse_postcode(text: str) -> tuple[str, str] | None:
    """A UK postcode, full ('ME4 4BY') or outward only ('ME4'), as (outward, inward); inward is '' for an outward code."""
    m = POSTCODE.match(text)
    if not m:
        return None
    return m.group(1).upper(), (m.group(2) or "").upper()


def matches_words(query: str, *fields: Any) -> bool:
    """True when every word of the query is in one of the fields."""
    words = norm(query).split()
    hay = norm(" ".join(str(f or "") for f in fields))
    return bool(words) and all(w in hay for w in words)


def mark_duplicates(results: list[Result]) -> list[Result]:
    """Results sharing a name get duplicates = how many share it, so the card can say '2 with this name'."""
    count: dict[str, int] = {}
    for r in results:
        count[norm(r["name"])] = count.get(norm(r["name"]), 0) + 1
    for r in results:
        n = count[norm(r["name"])]
        r["duplicates"] = n if n > 1 else 0
    return results


def _same_place(r: Result, o: Result) -> bool:
    if r.get("place_id") and r.get("place_id") == o.get("place_id"):
        return True
    if norm(r["name"]) != norm(o["name"]):
        return False
    pr, po = POSTCODE_IN.search(r.get("address") or ""), POSTCODE_IN.search(o.get("address") or "")
    if pr and po and norm(pr.group(0)) == norm(po.group(0)):
        return True  # the same name in the same postcode: one place written twice
    if r.get("lat") is not None and o.get("lat") is not None:
        near = distance_m((r["lat"], r["lon"]), (o["lat"], o["lon"])) < SAME_PLACE_M
        return near and (norm(r.get("address")) == norm(o.get("address")) or r["src"] != o["src"])
    return False


def merge(google: list[Result], postcode: list[Result], osm: list[Result], mine: list[Result], limit: int = MAX_RESULTS) -> list[Result]:
    """One list: your own matching places first (at most 2), the postcode, then Google (or OpenStreetMap when Google gave nothing).

    The same place twice (the same Google id, or the same name within about 50 m at the same address or from another source) is kept once;
    two places sharing a name a street apart (two car parks) stay two. OpenStreetMap results are put nearest first; Google's own order is kept.
    """
    out: list[Result] = []
    osm_sorted = sorted(osm, key=lambda r: r["distance_m"] if r.get("distance_m") is not None else math.inf)
    for r in mine[:2] + postcode + (google if google else osm_sorted):
        if len(out) >= limit:
            break
        if not any(_same_place(r, o) for o in out):
            out.append(r)
    return mark_duplicates(out)


def source_of(google: list[Result], osm: list[Result]) -> str:
    """Which outside source answered: google, osm or none."""
    return SRC_GOOGLE if google else SRC_OSM if osm else "none"
