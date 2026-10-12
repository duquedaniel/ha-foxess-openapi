"""Scheduler master switch (/op/v1/device/scheduler/*/flag)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import FoxESSError
from .const import DOMAIN
from .entity import device_info


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FoxSchedulerSwitch(data)])


class FoxSchedulerSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "Scheduler (mode scheduler)"
    _attr_icon = "mdi:calendar-sync"

    def __init__(self, data) -> None:
        super().__init__(data.settings)
        self._data = data
        self._attr_unique_id = f"{data.sn}_scheduler_enable"
        self._attr_device_info = device_info(data)

    @property
    def _flag(self) -> dict:
        return (self.coordinator.data or {}).get("scheduler_flag") or {}

    @property
    def available(self) -> bool:
        return super().available and self._flag.get("support", True) not in (False, 0)

    @property
    def is_on(self):
        v = self._flag.get("enable")
        return None if v is None else bool(int(v)) if not isinstance(v, bool) else v

    async def _set(self, on: bool) -> None:
        try:
            await self._data.api.scheduler_flag_set(self._data.sn, on)
        except FoxESSError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)
