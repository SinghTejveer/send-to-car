"""Diagnostics: the settings and saved places, with the key and positions hidden."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import SendToCarConfigEntry
from .const import CONF_GOOGLE_KEY

REDACT = {CONF_GOOGLE_KEY, "lat", "lon", "latitude", "longitude", "address"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: SendToCarConfigEntry) -> dict[str, Any]:
    finder = entry.runtime_data
    return {
        "settings": async_redact_data({**entry.data, **entry.options}, REDACT),
        "google_key_set": bool(finder.key),
        "favourites": async_redact_data(finder.saved["favourites"], REDACT),
        "recent": async_redact_data(finder.saved["recent"], REDACT),
    }
