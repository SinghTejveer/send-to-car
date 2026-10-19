"""Setup: the three steps, the Google key check, no cars, the same car twice, and changing settings later."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.send_to_car.const import (
    CONF_CALENDARS,
    CONF_CAR_DEVICE,
    CONF_COUNTRY,
    CONF_GOOGLE_KEY,
    CONF_POSTCODES,
    CONF_SUGGEST_FAVOURITES,
    CONF_SUGGEST_ZONES,
    CONF_WAKE,
    CONF_ZONE,
    DOMAIN,
)

AUTOCOMPLETE = "https://places.googleapis.com/v1/places:autocomplete"
SEARCH = {CONF_ZONE: "zone.home", CONF_COUNTRY: "GB", CONF_POSTCODES: True}
SUGGEST = {CONF_CALENDARS: [], CONF_SUGGEST_FAVOURITES: True, CONF_SUGGEST_ZONES: False}


async def test_three_steps_without_a_key(hass: HomeAssistant, car: str, aioclient_mock: AiohttpClientMocker) -> None:
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert r["type"] is FlowResultType.FORM and r["step_id"] == "user"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_CAR_DEVICE: car, CONF_WAKE: False})
    assert r["step_id"] == "search"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_GOOGLE_KEY: "  ", **SEARCH})
    assert r["step_id"] == "suggestions"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], SUGGEST)
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["title"] == "Send to Model 3"
    assert r["data"][CONF_CAR_DEVICE] == car and r["data"][CONF_GOOGLE_KEY] == "" and r["data"][CONF_WAKE] is False
    assert aioclient_mock.call_count == 0, "no key: Google is never asked"


async def test_a_good_key_is_checked_once_with_the_key_in_a_header(hass: HomeAssistant, car: str, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(AUTOCOMPLETE, json={"suggestions": []})
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_CAR_DEVICE: car, CONF_WAKE: True})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_GOOGLE_KEY: "AIzaGOOD", **SEARCH})
    assert r["step_id"] == "suggestions"
    assert aioclient_mock.call_count == 1
    _, url, _, headers = aioclient_mock.mock_calls[0]
    assert "AIzaGOOD" not in str(url) and headers["X-Goog-Api-Key"] == "AIzaGOOD"


async def test_a_refused_key_shows_an_error_on_the_form(hass: HomeAssistant, car: str, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(AUTOCOMPLETE, status=403, json={"error": {"status": "PERMISSION_DENIED"}})
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_CAR_DEVICE: car, CONF_WAKE: True})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_GOOGLE_KEY: "AIzaBAD", **SEARCH})
    assert r["type"] is FlowResultType.FORM and r["step_id"] == "search"
    assert r["errors"] == {CONF_GOOGLE_KEY: "invalid_key"}


async def test_google_unreachable_says_so(hass: HomeAssistant, car: str, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(AUTOCOMPLETE, exc=TimeoutError())
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_CAR_DEVICE: car, CONF_WAKE: True})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_GOOGLE_KEY: "AIzaX", **SEARCH})
    assert r["errors"] == {CONF_GOOGLE_KEY: "cannot_connect"}


async def test_no_cars_stops_with_a_reason(hass: HomeAssistant) -> None:
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "no_cars"


async def test_only_cars_are_offered_not_the_energy_site(hass: HomeAssistant, car: str) -> None:
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    options = r["data_schema"].schema[CONF_CAR_DEVICE].config["options"]
    assert [o["value"] for o in options] == [car]
    assert "Model 3" in options[0]["label"]


async def test_the_same_car_twice_is_refused(hass: HomeAssistant, setup_entry, car: str) -> None:
    await setup_entry()
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_CAR_DEVICE: car, CONF_WAKE: True})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "already_configured"


async def test_configure_changes_the_search_and_checks_a_new_key(hass: HomeAssistant, setup_entry, aioclient_mock: AiohttpClientMocker) -> None:
    entry = await setup_entry()
    aioclient_mock.post(AUTOCOMPLETE, json={"suggestions": []})
    r = await hass.config_entries.options.async_init(entry.entry_id)
    assert r["step_id"] == "init"
    r = await hass.config_entries.options.async_configure(r["flow_id"], {CONF_GOOGLE_KEY: "AIzaNEW", **SEARCH})
    assert r["step_id"] == "suggestions"
    r = await hass.config_entries.options.async_configure(r["flow_id"], {**SUGGEST, CONF_CALENDARS: ["calendar.family"]})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_GOOGLE_KEY] == "AIzaNEW" and entry.options[CONF_CALENDARS] == ["calendar.family"]
    assert entry.runtime_data.key == "AIzaNEW"
