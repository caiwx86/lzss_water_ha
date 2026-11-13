"""兴泸水务按钮平台。"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import LzssWaterDataUpdateCoordinator
from .entity import LzssWaterEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置按钮平台。"""
    coordinator: LzssWaterDataUpdateCoordinator = entry.runtime_data
    async_add_entities([LzssWaterRefreshButton(coordinator)])


class LzssWaterRefreshButton(LzssWaterEntity, ButtonEntity):
    """手动刷新水费数据。"""

    _attr_translation_key = "refresh"

    def __init__(self, coordinator: LzssWaterDataUpdateCoordinator) -> None:
        """初始化刷新按钮。"""
        super().__init__(coordinator, "refresh")

    async def async_press(self) -> None:
        """触发一次数据刷新。"""
        await self.coordinator.async_request_refresh()
