"""兴泸水务二进制传感器平台。"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_UNPAID_AMOUNT, ATTR_UNPAID_COUNT
from .coordinator import LzssWaterDataUpdateCoordinator
from .entity import LzssWaterEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置二进制传感器平台。"""
    coordinator: LzssWaterDataUpdateCoordinator = entry.runtime_data
    async_add_entities([LzssWaterUnpaidBinarySensor(coordinator)])


class LzssWaterUnpaidBinarySensor(LzssWaterEntity, BinarySensorEntity):
    """表示当前账户是否存在欠费。"""

    _attr_translation_key = "unpaid"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: LzssWaterDataUpdateCoordinator) -> None:
        """初始化欠费状态传感器。"""
        super().__init__(coordinator, "unpaid")

    @property
    def is_on(self) -> bool | None:
        """存在未缴账单时为 on，无法判断时为 unknown。"""
        data = self.coordinator.data
        if data is None:
            return None
        return data.has_unpaid

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回欠费笔数与金额。"""
        attributes = dict(super().extra_state_attributes)
        data = self.coordinator.data
        if data is not None:
            if data.unpaid_count is not None:
                attributes[ATTR_UNPAID_COUNT] = data.unpaid_count
            if data.unpaid_amount is not None:
                attributes[ATTR_UNPAID_AMOUNT] = data.unpaid_amount
        return attributes
