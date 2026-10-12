"""Sensors for FoxESS Cloud Open API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, RUNNING_STATE
from .entity import device_info

P, E, V, A = SensorDeviceClass.POWER, SensorDeviceClass.ENERGY, SensorDeviceClass.VOLTAGE, SensorDeviceClass.CURRENT
T = SensorDeviceClass.TEMPERATURE
M, TI = SensorStateClass.MEASUREMENT, SensorStateClass.TOTAL_INCREASING
KW, KWH = UnitOfPower.KILO_WATT, UnitOfEnergy.KILO_WATT_HOUR


@dataclass(frozen=True, kw_only=True)
class FoxSensorDesc(SensorEntityDescription):
    variable: str


def d(var, name, dc=None, unit=None, sc=M, cat=None, enabled=True, prec=None):
    return FoxSensorDesc(
        key=var, variable=var, name=name, device_class=dc, native_unit_of_measurement=unit,
        state_class=sc, entity_category=cat, entity_registry_enabled_default=enabled,
        suggested_display_precision=prec,
    )


REALTIME_SENSORS: tuple[FoxSensorDesc, ...] = (
    d("pvPower", "PV power", P, KW, prec=3),
    d("pv1Power", "PV1 power", P, KW, prec=3),
    d("pv2Power", "PV2 power", P, KW, prec=3),
    d("pv1Volt", "PV1 voltage", V, UnitOfElectricPotential.VOLT, enabled=False),
    d("pv2Volt", "PV2 voltage", V, UnitOfElectricPotential.VOLT, enabled=False),
    d("pv1Current", "PV1 current", A, UnitOfElectricCurrent.AMPERE, enabled=False),
    d("pv2Current", "PV2 current", A, UnitOfElectricCurrent.AMPERE, enabled=False),
    d("loadsPower", "Load power", P, KW, prec=3),
    d("gridConsumptionPower", "Grid import power", P, KW, prec=3),
    d("feedinPower", "Grid export power", P, KW, prec=3),
    d("generationPower", "Inverter output power", P, KW, prec=3),
    d("meterPower", "Meter power", P, KW, prec=3, enabled=False),
    d("SoC", "Battery SoC", SensorDeviceClass.BATTERY, PERCENTAGE),
    d("SOH", "Battery SoH", None, PERCENTAGE, cat=EntityCategory.DIAGNOSTIC),
    d("batTemperature", "Battery temperature", T, UnitOfTemperature.CELSIUS),
    d("batVolt", "Battery voltage", V, UnitOfElectricPotential.VOLT, enabled=False),
    d("batCurrent", "Battery current", A, UnitOfElectricCurrent.AMPERE, enabled=False),
    d("invBatPower", "Battery power (+discharge/-charge)", P, KW, prec=3),
    d("batChargePower", "Battery charge power", P, KW, prec=3),
    d("batDischargePower", "Battery discharge power", P, KW, prec=3),
    d("RVolt", "Grid voltage", V, UnitOfElectricPotential.VOLT),
    d("RCurrent", "Grid current", A, UnitOfElectricCurrent.AMPERE, enabled=False),
    d("RFreq", "Grid frequency", SensorDeviceClass.FREQUENCY, UnitOfFrequency.HERTZ),
    d("invTemperation", "Inverter temperature", T, UnitOfTemperature.CELSIUS, cat=EntityCategory.DIAGNOSTIC),
    d("ambientTemperation", "Ambient temperature", T, UnitOfTemperature.CELSIUS, cat=EntityCategory.DIAGNOSTIC),
    d("epsPower", "EPS power", P, KW, enabled=False),
    d("currentFault", "Current fault", sc=None, cat=EntityCategory.DIAGNOSTIC),
    # Energy counters
    d("PVEnergyTotal", "PV energy total", E, KWH, sc=TI),
    d("generation", "Generation total", E, KWH, sc=TI),
    d("feedin", "Grid export total", E, KWH, sc=TI),
    d("gridConsumption", "Grid import total", E, KWH, sc=TI),
    d("loads", "Load energy total", E, KWH, sc=TI),
    d("chargeEnergyToTal", "Battery charge total", E, KWH, sc=TI),
    d("dischargeEnergyToTal", "Battery discharge total", E, KWH, sc=TI),
)


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    ents: list[SensorEntity] = [FoxRealtimeSensor(data, desc) for desc in REALTIME_SENSORS]
    ents += [
        FoxRunningStateSensor(data),
        FoxScheduleSensor(data),
        FoxAccessSensor(data),
    ]
    async_add_entities(ents)


class _Base(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, data, key: str) -> None:
        super().__init__(coordinator)
        self._data = data
        self._attr_unique_id = f"{data.sn}_{key}"
        self._attr_device_info = device_info(data)


class FoxRealtimeSensor(_Base, SensorEntity):
    entity_description: FoxSensorDesc

    def __init__(self, data, desc: FoxSensorDesc) -> None:
        super().__init__(data.realtime, data, desc.key)
        self.entity_description = desc

    @property
    def _item(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get(self.entity_description.variable)

    @property
    def available(self) -> bool:
        return super().available and self._item is not None

    @property
    def native_value(self):
        item = self._item
        if item is None:
            return None
        val = item.get("value")
        if self.entity_description.native_unit_of_measurement is None:
            return val
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self):
        item = self._item
        return {"inverter_time": item.get("time")} if item else None


class FoxRunningStateSensor(_Base, SensorEntity):
    _attr_name = "Running state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(RUNNING_STATE.values()) + ["unknown"]

    def __init__(self, data) -> None:
        super().__init__(data.realtime, data, "runningState")

    @property
    def native_value(self):
        item = (self.coordinator.data or {}).get("runningState")
        if not item:
            return None
        try:
            return RUNNING_STATE.get(int(float(item["value"])), "unknown")
        except (TypeError, ValueError):
            return "unknown"


class FoxScheduleSensor(_Base, SensorEntity):
    """Shows the scheduler groups; state = active group's work mode."""

    _attr_name = "Schedule"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, data) -> None:
        super().__init__(data.settings, data, "schedule")

    @property
    def _sched(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("scheduler") or {}

    @property
    def native_value(self):
        groups = [g for g in self._sched.get("groups", []) if g.get("enable") == 1]
        return f"{len(groups)} active group(s)"

    @property
    def extra_state_attributes(self):
        s = self._sched
        return {
            "master_switch": s.get("enable"),
            "groups": [
                {k: g.get(k) for k in ("enable", "startHour", "startMinute", "endHour", "endMinute",
                                       "workMode", "minSocOnGrid", "fdSoc", "fdPwr", "maxSoc")}
                for g in s.get("groups", [])
            ],
        }


class FoxAccessSensor(_Base, SensorEntity):
    _attr_name = "API calls remaining"
    _attr_icon = "mdi:api"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = M

    def __init__(self, data) -> None:
        super().__init__(data.settings, data, "api_remaining")

    @property
    def native_value(self):
        acc = (self.coordinator.data or {}).get("access") or {}
        try:
            return int(float(acc.get("remaining")))
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self):
        acc = (self.coordinator.data or {}).get("access") or {}
        return {"total": acc.get("total")}
