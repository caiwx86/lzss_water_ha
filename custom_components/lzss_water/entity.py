"""兴泸水务实体基类。"""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ACCOUNT_NUMBER,
    ATTR_BILLING_MONTH,
    ATTR_LAST_UPDATE,
    CONFIGURATION_URL,
    DOMAIN,
    MANUFACTURER,
    MODEL,
)
from .coordinator import LzssWaterDataUpdateCoordinator


class LzssWaterEntity(CoordinatorEntity[LzssWaterDataUpdateCoordinator]):
    """所有平台实体共用的基类。"""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LzssWaterDataUpdateCoordinator, key: str) -> None:
        """初始化实体。"""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.account_number}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.account_number)},
            name=coordinator.device_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=CONFIGURATION_URL,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回所有实体共用的属性。"""
        attributes: dict[str, Any] = {
            ATTR_ACCOUNT_NUMBER: self.coordinator.account_number,
        }
        if self.coordinator.last_fetched_at is not None:
            attributes[ATTR_LAST_UPDATE] = self.coordinator.last_fetched_at.isoformat(
                timespec="seconds"
            )
        data = self.coordinator.data
        if data is not None and data.billing_month:
            attributes[ATTR_BILLING_MONTH] = data.billing_month
        return attributes
