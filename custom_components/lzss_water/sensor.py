"""兴泸水务传感器平台。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_BILLS
from .coordinator import LzssWaterDataUpdateCoordinator
from .entity import LzssWaterEntity
from .models import WaterBillData

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class LzssWaterSensorEntityDescription(SensorEntityDescription):
    """描述一个水费传感器。"""

    value_fn: Callable[[WaterBillData], Any]


SENSORS: tuple[LzssWaterSensorEntityDescription, ...] = (
    LzssWaterSensorEntityDescription(
        key="balance",
        translation_key="balance",
        native_unit_of_measurement="元",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: data.balance,
    ),
    LzssWaterSensorEntityDescription(
        key="unpaid_count",
        translation_key="unpaid_count",
        native_unit_of_measurement="笔",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: data.unpaid_count,
    ),
    LzssWaterSensorEntityDescription(
        key="unpaid_amount",
        translation_key="unpaid_amount",
        native_unit_of_measurement="元",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: data.unpaid_amount,
    ),
    LzssWaterSensorEntityDescription(
        key="account_name",
        translation_key="account_name",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.account_name,
    ),
    LzssWaterSensorEntityDescription(
        key="service_address",
        translation_key="service_address",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.address,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置传感器平台。"""
    coordinator: LzssWaterDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        LzssWaterSensor(coordinator, description) for description in SENSORS
    )


class LzssWaterSensor(LzssWaterEntity, SensorEntity):
    """兴泸水务传感器。"""

    entity_description: LzssWaterSensorEntityDescription

    def __init__(
        self,
        coordinator: LzssWaterDataUpdateCoordinator,
        description: LzssWaterSensorEntityDescription,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """返回传感器值。"""
        data = self.coordinator.data
        if data is None:
            return None
        return self.entity_description.value_fn(data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回实体属性，欠费金额额外附带账单明细。"""
        attributes = dict(super().extra_state_attributes)
        data = self.coordinator.data
        if (
            data is not None
            and data.unpaid_bills
            and self.entity_description.key == "unpaid_amount"
        ):
            attributes[ATTR_BILLS] = [bill.as_dict() for bill in data.unpaid_bills]
        return attributes
