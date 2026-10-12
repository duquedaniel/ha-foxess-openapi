"""Data update coordinators."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FoxESSApi, FoxESSError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Variables requested from /op/v1/device/real/query (keeps payloads small).
REALTIME_VARIABLES = [
    "pvPower", "pv1Power", "pv2Power", "pv1Volt", "pv2Volt", "pv1Current", "pv2Current",
    "loadsPower", "gridConsumptionPower", "feedinPower", "generationPower", "meterPower",
    "SoC", "SOH", "batTemperature", "batVolt", "batCurrent", "invBatPower",
    "batChargePower", "batDischargePower",
    "RVolt", "RCurrent", "RFreq", "invTemperation", "ambientTemperation",
    "runningState", "currentFault", "epsPower",
    "PVEnergyTotal", "generation", "feedin", "gridConsumption", "loads",
    "chargeEnergyToTal", "dischargeEnergyToTal",
]


class FoxESSRealtimeCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Polls real-time variables."""

    def __init__(self, hass: HomeAssistant, api: FoxESSApi, sn: str, minutes: int) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_realtime", update_interval=timedelta(minutes=minutes))
        self.api = api
        self.sn = sn

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            return await self.api.real_query(self.sn, REALTIME_VARIABLES)
        except FoxESSError as err:
            raise UpdateFailed(str(err)) from err


class FoxESSSettingsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls battery SoC limits and scheduler state (slower cadence)."""

    def __init__(self, hass: HomeAssistant, api: FoxESSApi, sn: str, minutes: int) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_settings", update_interval=timedelta(minutes=minutes))
        self.api = api
        self.sn = sn

    async def _async_update_data(self) -> dict[str, Any]:
        data: dict[str, Any] = dict(self.data or {})
        errors: list[str] = []
        for key, call in (
            ("soc", self.api.soc_get),
            ("scheduler_flag", self.api.scheduler_flag_get),
            ("scheduler", self.api.scheduler_get),
        ):
            try:
                data[key] = await call(self.sn)
            except FoxESSError as err:
                errors.append(str(err))
        try:
            data["access"] = await self.api.access_count()
        except FoxESSError as err:
            errors.append(str(err))
        if errors and not data:
            raise UpdateFailed("; ".join(errors))
        for e in errors:
            _LOGGER.warning("FoxESS settings partial failure: %s", e)
        return data
