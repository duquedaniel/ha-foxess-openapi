"""Number entities: battery min SoC limits (/op/v0/device/battery/soc/*)."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import FoxESSError
from .const import DOMAIN
from .entity import device_info


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        FoxMinSoc(data, "minSoc", "Battery min SoC (off-grid)"),
        FoxMinSoc(data, "minSocOnGrid", "Battery min SoC (on-grid)"),
    ])


class FoxMinSoc(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_native_min_value = 10  # documented range 10-100
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, data, field: str, name: str) -> None:
        super().__init__(data.settings)
        self._data = data
        self._field = field
        self._attr_name = name
        self._attr_unique_id = f"{data.sn}_{field}"
        self._attr_device_info = device_info(data)

    @property
    def _soc(self) -> dict:
        return (self.coordinator.data or {}).get("soc") or {}

    @property
    def native_value(self):
        v = self._soc.get(self._field)
        return None if v is None else float(v)

    async def async_set_native_value(self, value: float) -> None:
        soc = dict(self._soc)
        if "minSoc" not in soc or "minSocOnGrid" not in soc:
            raise HomeAssistantError("Current SoC settings unknown; refresh first")
        soc[self._field] = int(value)
        try:
            await self._data.api.soc_set(self._data.sn, soc["minSoc"], soc["minSocOnGrid"])
        except FoxESSError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()
