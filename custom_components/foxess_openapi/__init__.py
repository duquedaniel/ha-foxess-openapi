"""FoxESS Cloud Open API integration (read + control)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import time as dtime
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FoxESSApi, FoxESSError
from .const import (
    CONF_API_KEY,
    CONF_DEVICE_SN,
    CONF_REALTIME_INTERVAL,
    CONF_SETTINGS_INTERVAL,
    DEFAULT_REALTIME_INTERVAL,
    DEFAULT_SETTINGS_INTERVAL,
    DOMAIN,
    FORCE_CHARGE_MODES,
    GROUP_KEYS,
    SETTING_KEYS,
    WORK_MODES,
)
from .coordinator import FoxESSRealtimeCoordinator, FoxESSSettingsCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.NUMBER, Platform.SWITCH]


@dataclass
class FoxESSData:
    api: FoxESSApi
    sn: str
    realtime: FoxESSRealtimeCoordinator
    settings: FoxESSSettingsCoordinator
    detail: dict[str, Any]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = FoxESSApi(async_get_clientsession(hass), entry.data[CONF_API_KEY])
    sn = entry.data[CONF_DEVICE_SN]
    opts = entry.options
    realtime = FoxESSRealtimeCoordinator(
        hass, api, sn, opts.get(CONF_REALTIME_INTERVAL, DEFAULT_REALTIME_INTERVAL)
    )
    settings = FoxESSSettingsCoordinator(
        hass, api, sn, opts.get(CONF_SETTINGS_INTERVAL, DEFAULT_SETTINGS_INTERVAL)
    )
    try:
        detail = await api.device_detail(sn)
    except FoxESSError as err:
        _LOGGER.warning("Could not read device detail: %s", err)
        detail = {}

    await realtime.async_config_entry_first_refresh()
    await settings.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = FoxESSData(api, sn, realtime, settings, detail)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload_on_options))
    _register_services(hass)
    return True


async def _reload_on_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok


# --------------------------------------------------------------------- services
def _get(hass: HomeAssistant, sn: str | None) -> FoxESSData:
    entries: dict[str, FoxESSData] = hass.data.get(DOMAIN, {})
    if not entries:
        raise HomeAssistantError("No FoxESS Open API entry loaded")
    if sn:
        for d in entries.values():
            if d.sn == sn:
                return d
        raise HomeAssistantError(f"Unknown inverter SN {sn}")
    return next(iter(entries.values()))


def _split_window(start: dtime, end: dtime) -> list[tuple[int, int, int, int]]:
    """Return (sh, sm, eh, em) tuples; splits windows that cross midnight."""
    if (start.hour, start.minute) == (end.hour, end.minute):
        raise HomeAssistantError("start_time and end_time must differ")
    if (end.hour, end.minute) > (start.hour, start.minute):
        return [(start.hour, start.minute, end.hour, end.minute)]
    out = [(start.hour, start.minute, 23, 59)]
    if (end.hour, end.minute) != (0, 0):
        out.append((0, 0, end.hour, end.minute))
    return out


def _validate_group(g: dict[str, Any]) -> dict[str, Any]:
    if g["workMode"] not in WORK_MODES:
        raise HomeAssistantError(f"workMode must be one of {WORK_MODES}")
    if g["fdSoc"] < g["minSocOnGrid"]:
        # Documented constraint: "value of fdsoc must be equal or greater than minSocOnGrid"
        raise HomeAssistantError("fdSoc must be >= minSocOnGrid")
    return g


GROUP_SCHEMA = vol.Schema(
    {
        vol.Optional("enable", default=1): vol.In([0, 1]),
        vol.Required("startHour"): vol.All(int, vol.Range(0, 23)),
        vol.Required("startMinute"): vol.All(int, vol.Range(0, 59)),
        vol.Required("endHour"): vol.All(int, vol.Range(0, 23)),
        vol.Required("endMinute"): vol.All(int, vol.Range(0, 59)),
        vol.Required("workMode"): vol.In(WORK_MODES),
        vol.Required("minSocOnGrid"): vol.All(int, vol.Range(10, 100)),
        vol.Required("fdSoc"): vol.All(int, vol.Range(0, 100)),
        vol.Required("fdPwr"): vol.All(int, vol.Range(min=0)),
        vol.Optional("maxSoc"): vol.All(int, vol.Range(10, 100)),
    }
)

SN = vol.Optional("device_sn")

SCHEMA_SET_SCHEDULE = vol.Schema({SN: cv.string, vol.Required("groups"): [GROUP_SCHEMA],
                                  vol.Optional("enable_scheduler", default=True): cv.boolean})
SCHEMA_FORCE_CHARGE = vol.Schema(
    {
        SN: cv.string,
        vol.Required("start_time"): cv.time,
        vol.Required("end_time"): cv.time,
        vol.Required("target_soc"): vol.All(vol.Coerce(int), vol.Range(10, 100)),
        vol.Required("power"): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional("min_soc_on_grid"): vol.All(vol.Coerce(int), vol.Range(10, 100)),
        vol.Optional("max_soc", default=100): vol.All(vol.Coerce(int), vol.Range(10, 100)),
        vol.Optional("mode", default="ForceCharge"): vol.In(list(FORCE_CHARGE_MODES)),
        vol.Optional("replace_all", default=False): cv.boolean,
    }
)
SCHEMA_SN_ONLY = vol.Schema({SN: cv.string})
SCHEMA_SET_SETTING = vol.Schema({SN: cv.string, vol.Required("key"): vol.In(SETTING_KEYS),
                                 vol.Required("value"): cv.string})
SCHEMA_GET_SETTING = vol.Schema({SN: cv.string, vol.Required("key"): vol.In(SETTING_KEYS)})
SCHEMA_SET_MIN_SOC = vol.Schema({SN: cv.string,
                                 vol.Required("min_soc"): vol.All(vol.Coerce(int), vol.Range(10, 100)),
                                 vol.Required("min_soc_on_grid"): vol.All(vol.Coerce(int), vol.Range(10, 100))})


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "force_charge"):
        return

    async def _wrap(coro):
        try:
            return await coro
        except FoxESSError as err:
            raise HomeAssistantError(str(err)) from err

    async def set_schedule(call: ServiceCall) -> None:
        d = _get(hass, call.data.get("device_sn"))
        groups = [_validate_group(dict(g)) for g in call.data["groups"]]
        await _wrap(d.api.scheduler_set(d.sn, groups))
        if call.data["enable_scheduler"]:
            await _wrap(d.api.scheduler_flag_set(d.sn, True))
        await d.settings.async_request_refresh()

    async def force_charge(call: ServiceCall) -> None:
        d = _get(hass, call.data.get("device_sn"))
        min_grid = call.data.get("min_soc_on_grid")
        if min_grid is None:
            min_grid = int((d.settings.data or {}).get("soc", {}).get("minSocOnGrid", 10))
        target = call.data["target_soc"]
        if target < min_grid:
            raise HomeAssistantError("target_soc must be >= min_soc_on_grid")
        charge_groups = [
            {
                "enable": 1, "startHour": sh, "startMinute": sm, "endHour": eh, "endMinute": em,
                "workMode": call.data["mode"], "minSocOnGrid": min_grid, "fdSoc": target,
                "fdPwr": call.data["power"], "maxSoc": call.data["max_soc"],
            }
            for sh, sm, eh, em in _split_window(call.data["start_time"], call.data["end_time"])
        ]
        kept: list[dict[str, Any]] = []
        max_groups = 8
        if not call.data["replace_all"]:
            # Keep every enabled, non-force-charge group (e.g. the 00:00-23:59 SelfUse base),
            # read fresh from the inverter so we never write from a stale cache.
            current = await _wrap(d.api.scheduler_get(d.sn))
            max_groups = int(current.get("maxGroupCount") or len(current.get("groups", [])) or 8)
            kept = [
                {k: g[k] for k in GROUP_KEYS if k in g}
                for g in current.get("groups", [])
                if g.get("enable") == 1
                and g.get("workMode") in WORK_MODES
                and g.get("workMode") not in FORCE_CHARGE_MODES
            ]
        # Force-charge window(s) first, as in the inverter's own ordering.
        groups = charge_groups + kept
        if len(groups) > max_groups:
            raise HomeAssistantError(f"Schedule would need {len(groups)} groups; inverter allows {max_groups}")
        await _wrap(d.api.scheduler_set(d.sn, groups))
        await _wrap(d.api.scheduler_flag_set(d.sn, True))
        await d.settings.async_request_refresh()

    async def disable_scheduler(call: ServiceCall) -> None:
        d = _get(hass, call.data.get("device_sn"))
        await _wrap(d.api.scheduler_flag_set(d.sn, False))
        await d.settings.async_request_refresh()

    async def set_min_soc(call: ServiceCall) -> None:
        d = _get(hass, call.data.get("device_sn"))
        await _wrap(d.api.soc_set(d.sn, call.data["min_soc"], call.data["min_soc_on_grid"]))
        await d.settings.async_request_refresh()

    async def set_setting(call: ServiceCall) -> None:
        d = _get(hass, call.data.get("device_sn"))
        await _wrap(d.api.setting_set(d.sn, call.data["key"], call.data["value"]))

    async def get_setting(call: ServiceCall) -> dict[str, Any]:
        d = _get(hass, call.data.get("device_sn"))
        return await _wrap(d.api.setting_get(d.sn, call.data["key"]))

    async def get_schedule(call: ServiceCall) -> dict[str, Any]:
        d = _get(hass, call.data.get("device_sn"))
        return await _wrap(d.api.scheduler_get(d.sn))

    hass.services.async_register(DOMAIN, "set_schedule", set_schedule, SCHEMA_SET_SCHEDULE)
    hass.services.async_register(DOMAIN, "force_charge", force_charge, SCHEMA_FORCE_CHARGE)
    hass.services.async_register(DOMAIN, "disable_scheduler", disable_scheduler, SCHEMA_SN_ONLY)
    hass.services.async_register(DOMAIN, "set_min_soc", set_min_soc, SCHEMA_SET_MIN_SOC)
    hass.services.async_register(DOMAIN, "set_setting", set_setting, SCHEMA_SET_SETTING)
    hass.services.async_register(DOMAIN, "get_setting", get_setting, SCHEMA_GET_SETTING,
                                 supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "get_schedule", get_schedule, SCHEMA_SN_ONLY,
                                 supports_response=SupportsResponse.ONLY)
