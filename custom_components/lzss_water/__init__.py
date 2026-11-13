"""兴泸水务集成初始化。"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import LzssWaterApiClient
from .const import (
    CONF_ACCOUNT_NUMBER,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL_HOURS,
    MAX_SCAN_INTERVAL_HOURS,
    MIN_SCAN_INTERVAL_HOURS,
)
from .coordinator import LzssWaterDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]

CONFIG_VERSION = 2


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置兴泸水务集成。"""
    client = LzssWaterApiClient(
        async_get_clientsession(hass),
        entry.data[CONF_ACCOUNT_NUMBER],
        entry.data[CONF_TOKEN],
    )
    coordinator = LzssWaterDataUpdateCoordinator(hass, entry, client)

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载兴泸水务集成。"""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """把旧版配置迁移到当前版本。"""
    if entry.version > CONFIG_VERSION:
        _LOGGER.error(
            "配置版本 %s 高于当前支持的版本 %s，无法迁移",
            entry.version,
            CONFIG_VERSION,
        )
        return False

    if entry.version == 1:
        data = dict(entry.data)
        options = dict(entry.options)
        legacy_interval = data.pop(CONF_SCAN_INTERVAL, None)
        if legacy_interval is not None and CONF_SCAN_INTERVAL not in options:
            options[CONF_SCAN_INTERVAL] = _normalize_interval(legacy_interval)
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, version=CONFIG_VERSION
        )
        _LOGGER.info("已将兴泸水务配置迁移到版本 %s", CONFIG_VERSION)

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """选项变化后重新加载集成。"""
    await hass.config_entries.async_reload(entry.entry_id)


def _normalize_interval(value: Any) -> int:
    """把旧版秒数或小时数统一为 1-168 小时。"""
    if isinstance(value, timedelta):
        hours = value.total_seconds() / 3600
    else:
        try:
            hours = float(value)
        except (TypeError, ValueError):
            return DEFAULT_SCAN_INTERVAL_HOURS
        if hours > MAX_SCAN_INTERVAL_HOURS:
            # 旧 README 中的 scan_interval 单位是秒（例如 28800）
            hours /= 3600
    return max(MIN_SCAN_INTERVAL_HOURS, min(MAX_SCAN_INTERVAL_HOURS, round(hours)))
