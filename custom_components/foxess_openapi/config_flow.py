"""Config flow for FoxESS Cloud Open API."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FoxESSApi, FoxESSAuthError, FoxESSError
from .const import (
    CONF_API_KEY,
    CONF_DEVICE_SN,
    CONF_REALTIME_INTERVAL,
    CONF_SETTINGS_INTERVAL,
    DEFAULT_REALTIME_INTERVAL,
    DEFAULT_SETTINGS_INTERVAL,
    DOMAIN,
    MIN_REALTIME_INTERVAL,
)


class FoxESSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._api_key: str | None = None
        self._devices: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY].strip()
            api = FoxESSApi(async_get_clientsession(self.hass), self._api_key)
            try:
                devices = await api.device_list()
            except FoxESSAuthError:
                errors["base"] = "invalid_auth"
            except FoxESSError:
                errors["base"] = "cannot_connect"
            else:
                self._devices = {
                    d["deviceSN"]: f'{d["deviceSN"]} ({d.get("deviceType", "?")} - {d.get("stationName", "")})'
                    for d in devices
                }
                if not self._devices:
                    errors["base"] = "no_devices"
                else:
                    return await self.async_step_device()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    async def async_step_device(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            sn = user_input[CONF_DEVICE_SN]
            await self.async_set_unique_id(sn)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"FoxESS {sn}",
                data={CONF_API_KEY: self._api_key, CONF_DEVICE_SN: sn},
            )
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema({vol.Required(CONF_DEVICE_SN): vol.In(self._devices)}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return FoxESSOptionsFlow()


class FoxESSOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        o = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_REALTIME_INTERVAL, default=o.get(CONF_REALTIME_INTERVAL, DEFAULT_REALTIME_INTERVAL)
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_REALTIME_INTERVAL, max=60)),
                    vol.Required(
                        CONF_SETTINGS_INTERVAL, default=o.get(CONF_SETTINGS_INTERVAL, DEFAULT_SETTINGS_INTERVAL)
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=240)),
                }
            ),
        )
