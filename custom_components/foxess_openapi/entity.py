"""Shared entity helpers."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def device_info(data) -> DeviceInfo:
    det = data.detail or {}
    return DeviceInfo(
        identifiers={(DOMAIN, data.sn)},
        manufacturer="FoxESS",
        name=f"FoxESS {det.get('stationName') or data.sn}",
        model=det.get("deviceType") or det.get("productType"),
        serial_number=data.sn,
        sw_version=det.get("masterVersion"),
        hw_version=det.get("hardwareVersion"),
    )
