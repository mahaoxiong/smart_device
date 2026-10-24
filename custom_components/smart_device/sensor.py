"""诊断传感器平台。

只暴露诊断信息。认证凭据（BpeSessionId）刻意不在此暴露——
原实现把它做成了实体状态，等于把会话令牌公开到状态机。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SmartDeviceCoordinator
from .entity import SmartDeviceEntity
from .runtime import SmartDeviceRuntimeData

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class SmartDeviceSensorDescription(SensorEntityDescription):
    """附带取值函数的传感器描述。"""

    value_fn: Callable[[SmartDeviceCoordinator], str | datetime | None]


SENSORS: tuple[SmartDeviceSensorDescription, ...] = (
    SmartDeviceSensorDescription(
        key="user_id",
        translation_key="user_id",
        icon="mdi:account",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.api.user_id,
    ),
    SmartDeviceSensorDescription(
        key="device_id",
        translation_key="device_id",
        icon="mdi:devices",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.device_id,
    ),
    SmartDeviceSensorDescription(
        key="last_update",
        translation_key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.last_success_time,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置诊断传感器。"""
    runtime: SmartDeviceRuntimeData = entry.runtime_data

    async_add_entities(
        SmartDeviceSensor(
            coordinator=runtime.coordinator,
            device_id=entry.data[CONF_DEVICE_ID],
            device_name=entry.title,
            description=description,
        )
        for description in SENSORS
    )


class SmartDeviceSensor(SmartDeviceEntity, SensorEntity):
    """闪优物联诊断传感器。"""

    entity_description: SmartDeviceSensorDescription

    def __init__(
        self,
        coordinator: SmartDeviceCoordinator,
        device_id: str,
        device_name: str,
        description: SmartDeviceSensorDescription,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator, device_id, device_name)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{device_id}_{description.key}"

    @property
    def native_value(self) -> str | datetime | None:
        """返回传感器取值。"""
        return self.entity_description.value_fn(self.coordinator)
