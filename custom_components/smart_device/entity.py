"""实体基类。"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import SmartDeviceCoordinator


class SmartDeviceEntity(CoordinatorEntity[SmartDeviceCoordinator]):
    """闪优物联实体基类，统一设备注册信息。"""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmartDeviceCoordinator,
        device_id: str,
        device_name: str,
    ) -> None:
        """初始化实体。"""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )
