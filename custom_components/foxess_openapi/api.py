"""Minimal async client for the FoxESS Cloud Open API.

Reference: https://www.foxesscloud.com/i18n/en/OpenApiDocument.html
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

import aiohttp

from .const import (
    DEFAULT_BASE_URL,
    ERRNO_TOO_FREQUENT,
    PATH_ACCESS_COUNT,
    PATH_DEVICE_DETAIL,
    PATH_DEVICE_LIST,
    PATH_REAL_QUERY,
    PATH_SCHED_FLAG_GET,
    PATH_SCHED_FLAG_SET,
    PATH_SCHED_GET,
    PATH_SCHED_SET,
    PATH_SETTING_GET,
    PATH_SETTING_SET,
    PATH_SOC_GET,
    PATH_SOC_SET,
    QUERY_SPACING_S,
    UPDATE_SPACING_S,
)

_LOGGER = logging.getLogger(__name__)

USER_AGENT = "HomeAssistant-foxess_openapi/0.1"


class FoxESSError(Exception):
    """Generic API error."""

    def __init__(self, msg: str, errno: int | None = None) -> None:
        super().__init__(msg)
        self.errno = errno


class FoxESSAuthError(FoxESSError):
    """API key rejected."""


class FoxESSRateLimitError(FoxESSError):
    """errno 40400 - too many requests."""


class FoxESSApi:
    """Thin wrapper around the documented endpoints."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self._session = session
        self._key = api_key.strip()
        self._base = base_url.rstrip("/")
        self._lock = asyncio.Lock()
        self._last_call: dict[str, float] = {}
        # The doc's table says url+"\r\n"+token+"\r\n"+timestamp, while the
        # official Python sample builds it with a raw f-string (fr'...'),
        # i.e. literal backslash-r-backslash-n. We start with the sample's
        # behaviour and auto-switch once if the server rejects the signature.
        self._literal_sep = True
        self._sep_confirmed = False

    # ------------------------------------------------------------------ core
    def _headers(self, path: str) -> dict[str, str]:
        ts = str(round(time.time() * 1000))
        sep = "\\r\\n" if self._literal_sep else "\r\n"
        raw = f"{path}{sep}{self._key}{sep}{ts}"
        return {
            "token": self._key,
            "timestamp": ts,
            "signature": hashlib.md5(raw.encode("utf-8")).hexdigest(),
            "lang": "en",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }

    async def _throttle(self, path: str, is_update: bool) -> None:
        spacing = UPDATE_SPACING_S if is_update else QUERY_SPACING_S
        last = self._last_call.get(path, 0.0)
        wait = last + spacing - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call[path] = time.monotonic()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        is_update: bool = False,
    ) -> Any:
        async with self._lock:
            for attempt in range(2):
                await self._throttle(path, is_update)
                try:
                    async with self._session.request(
                        method,
                        self._base + path,
                        params=params,
                        json=json,
                        headers=self._headers(path),
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        resp.raise_for_status()
                        data = await resp.json(content_type=None)
                except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                    raise FoxESSError(f"Connection error on {path}: {err}") from err

                errno = data.get("errno") if isinstance(data, dict) else None
                if errno == 0:
                    self._sep_confirmed = True
                    return data.get("result")

                msg = data.get("msg", "") if isinstance(data, dict) else str(data)
                if errno == ERRNO_TOO_FREQUENT:
                    raise FoxESSRateLimitError(f"{path}: too frequent ({msg})", errno)
                # First-ever call failed: try the other signature separator once.
                if attempt == 0 and not self._sep_confirmed:
                    _LOGGER.debug("errno %s on %s, retrying with other signature separator", errno, path)
                    self._literal_sep = not self._literal_sep
                    continue
                if not self._sep_confirmed:
                    raise FoxESSAuthError(f"{path}: errno {errno} {msg}", errno)
                raise FoxESSError(f"{path}: errno {errno} {msg}", errno)
        raise FoxESSError(f"{path}: request failed")

    # ------------------------------------------------------------- endpoints
    async def device_list(self) -> list[dict[str, Any]]:
        res = await self._request("POST", PATH_DEVICE_LIST, json={"currentPage": 1, "pageSize": 100})
        return (res or {}).get("data", [])

    async def device_detail(self, sn: str) -> dict[str, Any]:
        return await self._request("GET", PATH_DEVICE_DETAIL, params={"sn": sn}) or {}

    async def real_query(self, sn: str, variables: list[str] | None = None) -> dict[str, dict[str, Any]]:
        body: dict[str, Any] = {"sns": [sn]}
        if variables:
            body["variables"] = variables
        res = await self._request("POST", PATH_REAL_QUERY, json=body) or []
        out: dict[str, dict[str, Any]] = {}
        for dev in res:
            if dev.get("deviceSN") != sn:
                continue
            for item in dev.get("datas", []):
                out[item["variable"]] = item
        return out

    async def soc_get(self, sn: str) -> dict[str, Any]:
        return await self._request("GET", PATH_SOC_GET, params={"sn": sn}) or {}

    async def soc_set(self, sn: str, min_soc: int, min_soc_on_grid: int) -> Any:
        return await self._request(
            "POST", PATH_SOC_SET,
            json={"sn": sn, "minSoc": int(min_soc), "minSocOnGrid": int(min_soc_on_grid)},
            is_update=True,
        )

    async def setting_get(self, sn: str, key: str) -> dict[str, Any]:
        return await self._request("POST", PATH_SETTING_GET, json={"sn": sn, "key": key}) or {}

    async def setting_set(self, sn: str, key: str, value: str) -> Any:
        return await self._request(
            "POST", PATH_SETTING_SET, json={"sn": sn, "key": key, "value": str(value)}, is_update=True
        )

    async def scheduler_flag_get(self, sn: str) -> dict[str, Any]:
        return await self._request("POST", PATH_SCHED_FLAG_GET, json={"deviceSN": sn}) or {}

    async def scheduler_flag_set(self, sn: str, enable: bool) -> Any:
        return await self._request(
            "POST", PATH_SCHED_FLAG_SET, json={"deviceSN": sn, "enable": 1 if enable else 0}, is_update=True
        )

    async def scheduler_get(self, sn: str) -> dict[str, Any]:
        return await self._request("POST", PATH_SCHED_GET, json={"deviceSN": sn}) or {}

    async def scheduler_set(self, sn: str, groups: list[dict[str, Any]]) -> Any:
        return await self._request(
            "POST", PATH_SCHED_SET, json={"deviceSN": sn, "groups": groups}, is_update=True
        )

    async def access_count(self) -> dict[str, Any]:
        return await self._request("GET", PATH_ACCESS_COUNT) or {}
