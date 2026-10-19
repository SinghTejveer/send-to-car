"""The actions: search (Google, OpenStreetMap, postcodes, your own places), send (to Teslemetry, waking first) and add favourite. Web calls faked."""

from __future__ import annotations

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.send_to_car.const import DOMAIN

AUTOCOMPLETE = "https://places.googleapis.com/v1/places:autocomplete"
DETAILS = "https://places.googleapis.com/v1/places/a"
TEXT = "https://places.googleapis.com/v1/places:searchText"
PHOTON = "https://photon.komoot.io/api/"
POSTCODE = "https://api.postcodes.io/postcodes/ME44BY"

GOOGLE_ANSWER = {
    "suggestions": [
        {
            "placePrediction": {
                "placeId": "a",
                "text": {"text": "St John's Car Park, Luton Road"},
                "distanceMeters": 13360,
                "structuredFormat": {"mainText": {"text": "St John's Car Park"}, "secondaryText": {"text": "Luton Road, Chatham"}},
            }
        }
    ]
}
DETAILS_ANSWER = {
    "id": "a",
    "displayName": {"text": "St John's (Upper) Car Park"},
    "formattedAddress": "Luton Road, Chatham ME4 4BY",
    "location": {"latitude": 51.381, "longitude": 0.531},
}
PHOTON_ANSWER = {
    "features": [
        {
            "properties": {"name": "St John's Car Park", "city": "Chatham", "postcode": "ME4 6AB", "countrycode": "GB"},
            "geometry": {"coordinates": [0.52, 51.38]},
        },
        {"properties": {"name": "Elsewhere", "countrycode": "US"}, "geometry": {"coordinates": [-80, 36]}},
    ]
}


async def search(hass: HomeAssistant, query: str, **extra) -> dict:
    return await hass.services.async_call(DOMAIN, "search", {"query": query, **extra}, blocking=True, return_response=True)


async def test_google_search_sends_the_key_in_a_header_biased_to_home(hass, setup_entry, aioclient_mock: AiohttpClientMocker) -> None:
    await setup_entry(google_places_key="KEY")
    aioclient_mock.post(AUTOCOMPLETE, json=GOOGLE_ANSWER)
    r = await search(hass, "st johns car park", session="s1")
    assert r["source"] == "google"
    top = r["results"][0]
    assert top["name"] == "St John's Car Park" and top["place_id"] == "a" and top["distance_mi"] == 8.3 and top["distance_km"] == 13.4
    _, url, body, headers = aioclient_mock.mock_calls[0]
    assert headers["X-Goog-Api-Key"] == "KEY" and "KEY" not in str(url)
    assert body["sessionToken"] == "s1" and body["includedRegionCodes"] == ["gb"]
    assert body["locationBias"]["circle"]["center"]["latitude"] == 51.44


async def test_no_key_uses_openstreetmap_in_the_country_only(hass, setup_entry, aioclient_mock: AiohttpClientMocker) -> None:
    await setup_entry()
    aioclient_mock.get(PHOTON, json=PHOTON_ANSWER)
    r = await search(hass, "st johns car park")
    assert r["source"] == "osm" and [x["name"] for x in r["results"]] == ["St John's Car Park"]
    assert not any("googleapis" in str(c[1]) for c in aioclient_mock.mock_calls)


async def test_google_failing_falls_back_and_says_why(hass, setup_entry, aioclient_mock: AiohttpClientMocker) -> None:
    await setup_entry(google_places_key="KEY")
    aioclient_mock.post(AUTOCOMPLETE, status=403)
    aioclient_mock.get(PHOTON, json=PHOTON_ANSWER)
    r = await search(hass, "st johns car park")
    assert r["source"] == "osm" and any(n.startswith("Google") for n in r["notes"])


async def test_a_postcode_is_looked_up_exactly(hass, setup_entry, aioclient_mock: AiohttpClientMocker) -> None:
    await setup_entry()
    aioclient_mock.get(POSTCODE, json={"result": {"latitude": 51.38, "longitude": 0.53, "admin_ward": "Luton", "admin_district": "Medway"}})
    aioclient_mock.get(PHOTON, json={"features": []})
    r = await search(hass, "me4 4by")
    assert r["results"][0]["name"] == "ME4 4BY" and r["results"][0]["source"] == "postcode"
    assert "Medway" in r["results"][0]["address"]


async def test_fewer_than_three_letters_does_not_search(hass, setup_entry, aioclient_mock: AiohttpClientMocker) -> None:
    await setup_entry()
    r = await search(hass, "ab")
    assert r["results"] == [] and aioclient_mock.call_count == 0


async def test_send_a_google_pick_wakes_then_navigates(hass, setup_entry, car_calls, car: str, aioclient_mock: AiohttpClientMocker) -> None:
    entry = await setup_entry(google_places_key="KEY")
    aioclient_mock.get(DETAILS, json=DETAILS_ANSWER)
    r = await hass.services.async_call(DOMAIN, "send", {"place_id": "a", "session": "s1"}, blocking=True, return_response=True)
    assert [c[:2] for c in car_calls] == [("button", "press"), ("teslemetry", "navigation_gps_request")]
    assert car_calls[0][2]["entity_id"] == "button.model_3_wake"
    nav = car_calls[1][2]
    assert nav["device_id"] == car and nav["gps"] == {"latitude": 51.381, "longitude": 0.531}
    assert r["car"] == "Model 3" and r["name"] == "St John's (Upper) Car Park"
    await hass.async_block_till_done()
    st = hass.states.get("sensor.send_to_model_3_last_destination")
    assert st.state == "St John's (Upper) Car Park" and st.attributes["recent"][0]["lat"] == 51.381
    assert entry.runtime_data.saved["recent"][0]["name"] == "St John's (Upper) Car Park"


async def test_send_coordinates_without_waking_when_switched_off(hass, setup_entry, car_calls) -> None:
    await setup_entry(wake_before_send=False)
    await hass.services.async_call(DOMAIN, "send", {"latitude": 51.5, "longitude": -0.12, "name": "Somewhere"}, blocking=True)
    assert [c[:2] for c in car_calls] == [("teslemetry", "navigation_gps_request")]


async def test_send_a_calendar_location_by_text(hass, setup_entry, car_calls, aioclient_mock: AiohttpClientMocker) -> None:
    await setup_entry(google_places_key="KEY")
    aioclient_mock.post(
        TEXT,
        json={
            "places": [
                {"id": "z", "displayName": {"text": "Dentist"}, "formattedAddress": "12 High St, Rochester", "location": {"latitude": 51.39, "longitude": 0.5}}
            ]
        },
    )
    r = await hass.services.async_call(DOMAIN, "send", {"query": "12 High Street, Rochester"}, blocking=True, return_response=True)
    assert r["latitude"] == 51.39 and car_calls[-1][2]["gps"]["latitude"] == 51.39


async def test_a_place_that_cannot_be_found_says_so_and_sends_nothing(hass, setup_entry, car_calls, aioclient_mock: AiohttpClientMocker) -> None:
    await setup_entry()
    aioclient_mock.get(PHOTON, json={"features": []})
    with pytest.raises(ServiceValidationError, match="Could not find"):
        await hass.services.async_call(DOMAIN, "send", {"query": "nowhere at all"}, blocking=True)
    assert car_calls == []


async def test_a_place_must_be_given(hass, setup_entry) -> None:
    await setup_entry()
    with pytest.raises((vol.Invalid, ServiceValidationError)):
        await hass.services.async_call(DOMAIN, "send", {}, blocking=True)


async def test_favourites_are_saved_once_and_found_by_search_first(hass, setup_entry, aioclient_mock: AiohttpClientMocker) -> None:
    await setup_entry()
    fav = {"name": "Waterfront Way", "address": "Chatham ME4 4DH", "latitude": 51.38, "longitude": 0.53}
    r1 = await hass.services.async_call(DOMAIN, "add_favourite", fav, blocking=True, return_response=True)
    r2 = await hass.services.async_call(DOMAIN, "add_favourite", fav, blocking=True, return_response=True)
    assert r1["added"] is True and r2["added"] is False
    aioclient_mock.get(PHOTON, json=PHOTON_ANSWER)
    r = await search(hass, "waterfront")
    assert r["results"][0]["source"] == "favourite" and r["results"][0]["name"] == "Waterfront Way"


async def test_saved_places_survive_a_restart(hass, setup_entry, car_calls) -> None:
    entry = await setup_entry(wake_before_send=False)
    await hass.services.async_call(DOMAIN, "send", {"latitude": 51.5, "longitude": -0.12, "name": "Office"}, blocking=True)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.saved["recent"][0]["name"] == "Office"


async def test_two_cars_need_an_entry_id(hass, setup_entry, car: str) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    await setup_entry()
    other = MockConfigEntry(domain=DOMAIN, title="Send to other", unique_id="other", data={"car_device": "x"})
    other.add_to_hass(hass)
    await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError, match="config_entry_id"):
        await search(hass, "anything")
