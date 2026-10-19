"""The card's starting list (send_to_car.suggestions) and removing a favourite."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.send_to_car.const import DOMAIN

from .conftest import VIN


async def suggestions(hass: HomeAssistant) -> dict:
    return await hass.services.async_call(DOMAIN, "suggestions", {}, blocking=True, return_response=True)


def fake_calendar(hass: HomeAssistant, events: dict[str, list[dict]]) -> list[dict]:
    """A stand-in for calendar.get_events that answers per calendar and records what was asked."""
    asked: list[dict] = []

    async def get_events(call: ServiceCall):
        asked.append(dict(call.data))
        return {e: {"events": events.get(e, [])} for e in call.data["entity_id"]}

    hass.services.async_register("calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY)
    return asked


async def test_todays_calendar_stops_with_a_location_earliest_first(hass, setup_entry) -> None:
    now = dt_util.now()
    later, sooner = (now + timedelta(hours=3)).isoformat(), (now + timedelta(hours=1)).isoformat()
    asked = fake_calendar(
        hass,
        {
            "calendar.family": [
                {"summary": "Dentist", "start": later, "end": later, "location": "12 High Street, Rochester"},
                {"summary": "Call mum", "start": sooner, "end": sooner, "location": ""},
            ],
            "calendar.work": [{"summary": "Client visit", "start": sooner, "end": sooner, "location": "Canary Wharf, London"}],
        },
    )
    await setup_entry(calendars=["calendar.family", "calendar.work"])
    s = await suggestions(hass)
    assert [e["name"] for e in s["calendar"]] == ["Client visit", "Dentist"], "events without a location are left out"
    assert s["calendar"][1]["address"] == "12 High Street, Rochester" and s["calendar"][1]["time"]
    assert asked[0]["entity_id"] == ["calendar.family", "calendar.work"]


async def test_no_calendars_chosen_asks_no_calendar(hass, setup_entry) -> None:
    asked = fake_calendar(hass, {})
    await setup_entry()
    assert (await suggestions(hass))["calendar"] == [] and asked == []


async def test_favourites_recent_and_zones_with_distances(hass, setup_entry, car_calls) -> None:
    hass.states.async_set("zone.work", "0", {"latitude": 51.5054, "longitude": -0.0235, "friendly_name": "Work"})
    await setup_entry(wake_before_send=False)
    await hass.services.async_call(DOMAIN, "add_favourite", {"name": "Waterfront Way", "latitude": 51.38, "longitude": 0.53}, blocking=True)
    await hass.services.async_call(DOMAIN, "send", {"name": "Office", "latitude": 51.5054, "longitude": -0.0235}, blocking=True)
    s = await suggestions(hass)
    assert s["favourites"][0]["name"] == "Waterfront Way" and s["favourites"][0]["source"] == "favourite" and s["favourites"][0]["distance_km"] > 0
    assert s["recent"][0]["name"] == "Office" and s["last"]["name"] == "Office"
    assert [z["name"] for z in s["zones"]] == ["Home", "Work"], "nearest zone first"


async def test_switched_off_parts_are_empty(hass, setup_entry) -> None:
    await setup_entry(suggest_favourites=False, suggest_zones=False)
    await hass.services.async_call(DOMAIN, "add_favourite", {"name": "X", "latitude": 51.0, "longitude": 0.1}, blocking=True)
    s = await suggestions(hass)
    assert s["favourites"] == [] and s["recent"] == [] and s["zones"] == []


async def test_car_battery_and_range_come_from_its_sensors(hass, setup_entry, car: str) -> None:
    ent_reg = er.async_get(hass)
    tes = hass.config_entries.async_entries("teslemetry")[0]
    b = ent_reg.async_get_or_create(
        "sensor", "teslemetry", f"{VIN}-charge_state_battery_level", device_id=car, config_entry=tes, suggested_object_id="model_3_battery"
    )
    r = ent_reg.async_get_or_create(
        "sensor", "teslemetry", f"{VIN}-charge_state_battery_range", device_id=car, config_entry=tes, suggested_object_id="model_3_range"
    )
    hass.states.async_set(b.entity_id, "78", {"unit_of_measurement": "%"})
    hass.states.async_set(r.entity_id, "231.4", {"unit_of_measurement": "mi"})
    await setup_entry(google_places_key="KEY")
    s = await suggestions(hass)
    assert s["car"] == {"name": "Model 3", "battery": 78.0, "range": 231.4, "range_unit": "mi", "battery_entity": b.entity_id, "range_entity": r.entity_id}
    assert s["google"] is True


async def test_car_without_those_sensors_still_has_a_name(hass, setup_entry) -> None:
    await setup_entry()
    car = (await suggestions(hass))["car"]
    assert car["name"] == "Model 3" and car["battery"] is None


async def test_remove_a_favourite_by_name(hass, setup_entry) -> None:
    await setup_entry()
    await hass.services.async_call(DOMAIN, "add_favourite", {"name": "Gym", "latitude": 51.0, "longitude": 0.1}, blocking=True)
    r = await hass.services.async_call(DOMAIN, "remove_favourite", {"name": "gym"}, blocking=True, return_response=True)
    again = await hass.services.async_call(DOMAIN, "remove_favourite", {"name": "Gym"}, blocking=True, return_response=True)
    assert r == {"removed": True} and again == {"removed": False}
    assert (await suggestions(hass))["favourites"] == []
