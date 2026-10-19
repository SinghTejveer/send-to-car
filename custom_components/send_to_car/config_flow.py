"""Setup in three steps: the car, the search, the suggestions. The same search and suggestion settings can be changed later (Configure)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    CountrySelector,
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import providers as pv
from .cars import find_cars
from .const import (
    CONF_CALENDARS,
    CONF_CAR_DEVICE,
    CONF_COUNTRY,
    CONF_GOOGLE_KEY,
    CONF_POSTCODES,
    CONF_SUGGEST_FAVOURITES,
    CONF_SUGGEST_ZONES,
    CONF_WAKE,
    CONF_ZONE,
    DEFAULT_COUNTRY,
    DEFAULT_ZONE,
    DOMAIN,
)

TEST_QUERY = "Station"


async def validate_key(hass: HomeAssistant, key: str, country: str) -> str | None:
    """One small test search with the Google key -> an error key for the form, or None when it works."""
    try:
        await pv.google_autocomplete(async_get_clientsession(hass), key, TEST_QUERY, (hass.config.latitude, hass.config.longitude), country)
    except pv.InvalidKey:
        return "invalid_key"
    except pv.ProviderError:
        return "cannot_connect"
    return None


def search_schema(d: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_GOOGLE_KEY, description={"suggested_value": d.get(CONF_GOOGLE_KEY, "")}): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_ZONE, default=d.get(CONF_ZONE, DEFAULT_ZONE)): EntitySelector(EntitySelectorConfig(domain="zone")),
            vol.Required(CONF_COUNTRY, default=d.get(CONF_COUNTRY, DEFAULT_COUNTRY)): CountrySelector(),
            vol.Required(CONF_POSTCODES, default=d.get(CONF_POSTCODES, True)): BooleanSelector(),
        }
    )


def suggest_schema(d: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_CALENDARS, default=d.get(CONF_CALENDARS, [])): EntitySelector(EntitySelectorConfig(domain="calendar", multiple=True)),
            vol.Required(CONF_SUGGEST_FAVOURITES, default=d.get(CONF_SUGGEST_FAVOURITES, True)): BooleanSelector(),
            vol.Required(CONF_SUGGEST_ZONES, default=d.get(CONF_SUGGEST_ZONES, True)): BooleanSelector(),
        }
    )


def clean_key(data: dict[str, Any]) -> dict[str, Any]:
    data = dict(data)
    data[CONF_GOOGLE_KEY] = (data.get(CONF_GOOGLE_KEY) or "").strip()
    return data


class SendToCarConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a car."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        cars = [c for c in find_cars(self.hass) if c.supported]
        if not cars:
            return self.async_abort(reason="no_cars")
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_CAR_DEVICE])
            self._abort_if_unique_id_configured()
            self._data.update(user_input)
            return await self.async_step_search()
        options = [SelectOptionDict(value=c.device_id, label=f"{c.name} (via Teslemetry)") for c in cars]
        schema = vol.Schema(
            {
                vol.Required(CONF_CAR_DEVICE, default=cars[0].device_id): SelectSelector(SelectSelectorConfig(options=options)),
                vol.Required(CONF_WAKE, default=True): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_search(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = clean_key(user_input)
            if user_input[CONF_GOOGLE_KEY] and (err := await validate_key(self.hass, user_input[CONF_GOOGLE_KEY], user_input[CONF_COUNTRY])):
                errors[CONF_GOOGLE_KEY] = err
            else:
                self._data.update(user_input)
                return await self.async_step_suggestions()
        return self.async_show_form(step_id="search", data_schema=search_schema(user_input or {}), errors=errors)

    async def async_step_suggestions(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            car = next((c for c in find_cars(self.hass) if c.device_id == self._data[CONF_CAR_DEVICE]), None)
            return self.async_create_entry(title=f"Send to {car.name if car else 'car'}", data=self._data)
        return self.async_show_form(step_id="suggestions", data_schema=suggest_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SendToCarOptionsFlow()


class SendToCarOptionsFlow(OptionsFlow):
    """Change the search and the suggestions."""

    def __init__(self) -> None:
        self._options: dict[str, Any] = {}

    @property
    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = clean_key(user_input)
            key_changed = user_input[CONF_GOOGLE_KEY] != (self._current.get(CONF_GOOGLE_KEY) or "")
            if user_input[CONF_GOOGLE_KEY] and key_changed and (err := await validate_key(self.hass, user_input[CONF_GOOGLE_KEY], user_input[CONF_COUNTRY])):
                errors[CONF_GOOGLE_KEY] = err
            else:
                self._options.update(user_input)
                return await self.async_step_suggestions()
        return self.async_show_form(step_id="init", data_schema=search_schema(user_input or self._current), errors=errors)

    async def async_step_suggestions(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(data=self._options)
        return self.async_show_form(step_id="suggestions", data_schema=suggest_schema(self._current))
