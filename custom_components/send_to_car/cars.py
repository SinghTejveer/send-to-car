"""Cars that can receive a destination, found among the integrations already installed.

Version 1 supports Teslemetry, whose `teslemetry.navigation_gps_request` action sends coordinates to a car. Each supported integration is one
adapter: it lists its cars and sends a position. More adapters (Tessie, Tesla Fleet) can be added here without touching the rest.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

TESLEMETRY = "teslemetry"


@dataclass(frozen=True)
class Car:
    """A car that can receive a destination."""

    device_id: str
    name: str
    integration: str
    supported: bool


def _device_name(device: dr.DeviceEntry) -> str:
    return device.name_by_user or device.name or device.model or "Car"


def find_cars(hass: HomeAssistant) -> list[Car]:
    """Every car Home Assistant knows from a supported integration. A Teslemetry car is a Teslemetry device with a location tracker
    (energy sites and wall connectors have none)."""
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)
    cars: list[Car] = []
    for entry in hass.config_entries.async_entries(TESLEMETRY):
        for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
            entities = er.async_entries_for_device(ent_reg, device.id, include_disabled_entities=True)
            if any(e.domain == "device_tracker" for e in entities):
                cars.append(Car(device.id, _device_name(device), TESLEMETRY, True))
    return sorted(cars, key=lambda c: c.name.lower())


def car_by_device(hass: HomeAssistant, device_id: str) -> Car | None:
    return next((c for c in find_cars(hass) if c.device_id == device_id), None)


def _wake_button(hass: HomeAssistant, device_id: str) -> str | None:
    ent_reg = er.async_get(hass)
    for e in er.async_entries_for_device(ent_reg, device_id):
        if e.domain == "button" and (e.unique_id or "").endswith("-wake") and e.platform == TESLEMETRY:
            return e.entity_id
    return None


async def send_position(hass: HomeAssistant, car: Car, lat: float, lon: float, *, wake: bool) -> None:
    """Send a position to the car's navigation. Raises HomeAssistantError with a plain reason when it cannot."""
    if car.integration != TESLEMETRY or not car.supported:
        raise HomeAssistantError(f"Sending to {car.name} is not supported yet")
    if wake and (button := _wake_button(hass, car.device_id)):
        await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    await hass.services.async_call(
        TESLEMETRY,
        "navigation_gps_request",
        {"device_id": car.device_id, "gps": {"latitude": lat, "longitude": lon}, "order": 1},
        blocking=True,
    )
