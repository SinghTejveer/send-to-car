"""The last destination sent, with the favourites and recent places as attributes (the card reads them)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SendToCarConfigEntry, signal
from .const import CONF_CAR_DEVICE, DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: SendToCarConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([LastDestinationSensor(entry)])


class LastDestinationSensor(SensorEntity):
    """State: the name of the last place sent to the car."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_destination"
    _attr_icon = "mdi:map-marker-down"
    _attr_should_poll = False

    def __init__(self, entry: SendToCarConfigEntry) -> None:
        self._entry = entry
        self._finder = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}-last_destination"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Send to Car",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, signal(self._entry), self._updated))

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        last = self._finder.last or (self._finder.saved["recent"][0] if self._finder.saved["recent"] else None)
        return (last or {}).get("name") or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last = self._finder.last or {}
        return {
            "car_device_id": self._finder.conf.get(CONF_CAR_DEVICE),
            "address": last.get("address"),
            "latitude": last.get("lat"),
            "longitude": last.get("lon"),
            "sent_at": datetime.fromtimestamp(last["at"], UTC).isoformat() if last.get("at") else None,
            "favourites": self._finder.saved["favourites"],
            "recent": self._finder.saved["recent"],
        }
