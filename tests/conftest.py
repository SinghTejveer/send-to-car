"""Shared test set-up: a Home Assistant with a Teslemetry car in its registries, and a recorder for the car commands."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

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

HOME = (51.44, 0.37)
VIN = "LRW3TESTVIN000001"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
async def car(hass: HomeAssistant) -> str:
    """A Teslemetry config entry with one car (a device with a location tracker and a wake button) and an energy site. -> the car's device id."""
    hass.config.latitude, hass.config.longitude = HOME
    hass.states.async_set("zone.home", "0", {"latitude": HOME[0], "longitude": HOME[1], "friendly_name": "Home"})
    tes = MockConfigEntry(domain="teslemetry", title="Teslemetry", data={})
    tes.add_to_hass(hass)
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)
    car_dev = dev_reg.async_get_or_create(config_entry_id=tes.entry_id, identifiers={("teslemetry", VIN)}, name="Model 3", model="Model 3")
    site = dev_reg.async_get_or_create(config_entry_id=tes.entry_id, identifiers={("teslemetry", "12345")}, name="My Home", model="Powerwall 3")
    ent_reg.async_get_or_create("device_tracker", "teslemetry", f"{VIN}-location", device_id=car_dev.id, config_entry=tes)
    ent_reg.async_get_or_create("button", "teslemetry", f"{VIN}-wake", device_id=car_dev.id, config_entry=tes, suggested_object_id="model_3_wake")
    ent_reg.async_get_or_create("sensor", "teslemetry", "12345-battery_power", device_id=site.id, config_entry=tes)
    return car_dev.id


@pytest.fixture
def car_calls(hass: HomeAssistant) -> list[tuple[str, str, dict[str, Any]]]:
    """Stand-ins for Teslemetry's navigation action and the button press, recording what was sent."""
    calls: list[tuple[str, str, dict[str, Any]]] = []

    async def record(call: ServiceCall) -> None:
        calls.append((call.domain, call.service, dict(call.data)))

    hass.services.async_register("teslemetry", "navigation_gps_request", record)
    hass.services.async_register("button", "press", record)
    return calls


def entry_data(car_id: str, **over: Any) -> dict[str, Any]:
    return {
        CONF_CAR_DEVICE: car_id,
        CONF_WAKE: True,
        CONF_GOOGLE_KEY: "",
        CONF_ZONE: "zone.home",
        CONF_COUNTRY: "GB",
        CONF_POSTCODES: True,
        CONF_CALENDARS: [],
        CONF_SUGGEST_FAVOURITES: True,
        CONF_SUGGEST_ZONES: True,
        **over,
    }


@pytest.fixture
async def setup_entry(hass: HomeAssistant, car: str):
    """Set Send to Car up for the car. Call it with any overrides of the settings. -> the config entry."""

    async def _setup(**over: Any) -> MockConfigEntry:
        entry = MockConfigEntry(domain=DOMAIN, title="Send to Model 3", unique_id=car, data=entry_data(car, **over))
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry

    return _setup
