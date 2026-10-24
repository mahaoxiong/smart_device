"""设备状态轮询协调器。"""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api import CannotConnect, SmartDeviceAPI
from .const import (
    DEVICE_STATUS_OFF,
    DEVICE_STATUS_ON,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class SmartDeviceCoordinator(DataUpdateCoordinator[bool]):
    """周期拉取设备开关状态。

    data 为 True / False，代表设备当前的开关状态。失败时抛出 UpdateFailed，
    这样实体才会被正确标记为不可用——这是原实现最大的缺陷所在。
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: SmartDeviceAPI,
        device_id: str,
        name: str,
    ) -> None:
        """初始化协调器。"""
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=UPDATE_INTERVAL,
        )
        self.api = api
        self.device_id = device_id
        self.last_success_time: datetime | None = None

    async def _async_update_data(self) -> bool:
        """拉取一次设备状态。"""
        try:
            status = await self.api.async_get_device_status(self.device_id)
        except CannotConnect as err:
            raise UpdateFailed(f"获取设备状态失败: {err}") from err

        if status is None:
            raise UpdateFailed("设备未返回有效状态")

        value = status.get("status")
        if value not in (DEVICE_STATUS_ON, DEVICE_STATUS_OFF):
            raise UpdateFailed(f"设备返回了未知状态值: {value!r}")

        self.last_success_time = dt_util.utcnow()
        return value == DEVICE_STATUS_ON

    def apply_optimistic_state(self, turn_on: bool) -> None:
        """指令下发后立即把本地状态推进到目标值，避免 UI 等待轮询。

        下一轮轮询会用云端真实状态覆盖它。
        """
        self.async_set_updated_data(turn_on)
