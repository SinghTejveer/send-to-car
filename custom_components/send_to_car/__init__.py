"""Send to Car: search places, postcodes and calendar locations, and send them to your car's navigation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType

from .cars import car_by_device, send_position
from .const import (
    ATTR_ADDRESS,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_NAME,
    ATTR_PLACE_ID,
    ATTR_QUERY,
    ATTR_SESSION,
    CARD_URL,
    CONF_CAR_DEVICE,
    CONF_WAKE,
    DOMAIN,
    SERVICE_ADD_FAVOURITE,
    SERVICE_REMOVE_FAVOURITE,
    SERVICE_SEARCH,
    SERVICE_SEND,
    SERVICE_SUGGESTIONS,
)
from .finder import Finder
from .suggest import suggestions as build_suggestions

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
SIGNAL_UPDATE = f"{DOMAIN}_update"

type SendToCarConfigEntry = ConfigEntry[Finder]

SEARCH_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_QUERY): cv.string,
        vol.Optional(ATTR_SESSION): cv.string,
    }
)
PLACE_FIELDS = {
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    vol.Optional(ATTR_PLACE_ID): cv.string,
    vol.Optional(ATTR_QUERY): cv.string,
    vol.Optional(ATTR_NAME): cv.string,
    vol.Optional(ATTR_ADDRESS): cv.string,
    vol.Inclusive(CONF_LATITUDE, "position"): cv.latitude,
    vol.Inclusive(CONF_LONGITUDE, "position"): cv.longitude,
    vol.Optional(ATTR_SESSION): cv.string,
}


def _has_place(data: dict[str, Any]) -> dict[str, Any]:
    if not (data.get(ATTR_PLACE_ID) or data.get(ATTR_QUERY) or data.get(CONF_LATITUDE) is not None or data.get(ATTR_NAME)):
        raise vol.Invalid("Give a place: place_id, query, name, or latitude and longitude")
    return data


SEND_SCHEMA = vol.All(vol.Schema(PLACE_FIELDS), _has_place)
ENTRY_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string})
REMOVE_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string, vol.Required(ATTR_NAME): cv.string})


def _entry(hass: HomeAssistant, call: ServiceCall) -> SendToCarConfigEntry:
    """The config entry named in the call, or the only one there is."""
    loaded = [e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED]
    if entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
        for e in loaded:
            if e.entry_id == entry_id:
                return e
        raise ServiceValidationError(f"No loaded Send to Car entry with id {entry_id}")
    if len(loaded) == 1:
        return loaded[0]
    if not loaded:
        raise ServiceValidationError("Send to Car is not set up")
    raise ServiceValidationError("More than one car is set up: say which with config_entry_id")


def _resolve_kwargs(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "place_id": data.get(ATTR_PLACE_ID),
        "lat": data.get(CONF_LATITUDE),
        "lon": data.get(CONF_LONGITUDE),
        "query": data.get(ATTR_QUERY),
        "name": data.get(ATTR_NAME),
        "address": data.get(ATTR_ADDRESS),
        "session_token": data.get(ATTR_SESSION),
    }


def _out(r: dict[str, Any]) -> dict[str, Any]:
    return {"name": r.get("name") or "", "address": r.get("address") or "", "latitude": r["lat"], "longitude": r["lon"], "place_id": r.get("place_id")}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions once; each one finds its config entry."""

    async def search(call: ServiceCall) -> ServiceResponse:
        finder = _entry(hass, call).runtime_data
        return await finder.search(call.data[ATTR_QUERY], call.data.get(ATTR_SESSION))

    async def send(call: ServiceCall) -> ServiceResponse:
        entry = _entry(hass, call)
        finder = entry.runtime_data
        car = car_by_device(hass, finder.conf[CONF_CAR_DEVICE])
        if car is None:
            raise ServiceValidationError("The car set up for Send to Car is no longer in Home Assistant")
        place = await finder.resolve(**_resolve_kwargs(call.data))
        await send_position(hass, car, place["lat"], place["lon"], wake=bool(finder.conf.get(CONF_WAKE, True)))
        finder.add_recent(place)
        async_dispatcher_send(hass, f"{SIGNAL_UPDATE}_{entry.entry_id}")
        return {"car": car.name, **_out(place)}

    async def add_favourite(call: ServiceCall) -> ServiceResponse:
        entry = _entry(hass, call)
        place = await entry.runtime_data.resolve(**_resolve_kwargs(call.data))
        added = entry.runtime_data.add_favourite(place)
        async_dispatcher_send(hass, f"{SIGNAL_UPDATE}_{entry.entry_id}")
        return {"added": added, **_out(place)}

    async def suggestions(call: ServiceCall) -> ServiceResponse:
        return await build_suggestions(hass, _entry(hass, call).runtime_data)

    async def remove_favourite(call: ServiceCall) -> ServiceResponse:
        entry = _entry(hass, call)
        removed = entry.runtime_data.remove_favourite(call.data[ATTR_NAME])
        async_dispatcher_send(hass, f"{SIGNAL_UPDATE}_{entry.entry_id}")
        return {"removed": removed}

    hass.services.async_register(DOMAIN, SERVICE_SUGGESTIONS, suggestions, schema=ENTRY_SCHEMA, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE_FAVOURITE, remove_favourite, schema=REMOVE_SCHEMA, supports_response=SupportsResponse.OPTIONAL)
    await _register_card(hass)
    hass.services.async_register(DOMAIN, SERVICE_SEARCH, search, schema=SEARCH_SCHEMA, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, SERVICE_SEND, send, schema=SEND_SCHEMA, supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_ADD_FAVOURITE, add_favourite, schema=SEND_SCHEMA, supports_response=SupportsResponse.OPTIONAL)
    return True


async def _register_card(hass: HomeAssistant) -> None:
    """Serve the card and load it on every dashboard, so it shows in the card picker with no extra step. Skipped when there is no web server
    (tests, safe mode)."""
    if getattr(hass, "http", None) is None:
        return
    try:
        from homeassistant.components.frontend import add_extra_js_url
        from homeassistant.components.http import StaticPathConfig

        path = Path(__file__).parent / "www" / "send-to-car-card.js"
        await hass.async_add_executor_job(_remove_stale_compressed, path)
        await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(path), cache_headers=False)])
        version = (await hass.async_add_executor_job(_version)) or "0"
        add_extra_js_url(hass, f"{CARD_URL}?v={version}")
    except Exception:
        _LOGGER.warning("Could not register the Send to Car card", exc_info=True)


def _remove_stale_compressed(path: Path) -> None:
    """A pre-compressed copy (.gz or .br) beside the card is sent to browsers in its place. Copies made from an older card would keep serving the
    old card after an update, so remove any that is older than the card itself."""
    for suffix in (".gz", ".br"):
        copy = path.with_name(path.name + suffix)
        try:
            if copy.exists() and copy.stat().st_mtime < path.stat().st_mtime:
                copy.unlink()
                _LOGGER.info("Removed an out-of-date compressed copy of the card: %s", copy.name)
        except OSError as err:
            _LOGGER.warning("Could not remove %s: %s", copy, err)


def _version() -> str:
    import json

    return json.loads((Path(__file__).parent / "manifest.json").read_text(encoding="utf-8")).get("version", "0")


async def async_setup_entry(hass: HomeAssistant, entry: SendToCarConfigEntry) -> bool:
    finder = Finder(hass, entry)
    await finder.async_load()
    entry.runtime_data = finder
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SendToCarConfigEntry) -> bool:
    await entry.runtime_data.async_flush()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _reload(hass: HomeAssistant, entry: SendToCarConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


@callback
def signal(entry: ConfigEntry) -> str:
    return f"{SIGNAL_UPDATE}_{entry.entry_id}"
