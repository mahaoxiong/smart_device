"""开关平台。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import CannotConnect, InvalidAuth
from .const import (
    DEVICE_STATUS_OFF,
    DEVICE_STATUS_ON,
    DOMAIN,
    STATE_CHECK_DELAY,
    STATE_CHECK_RETRIES,
    STATE_CHECK_TIMEOUT,
)
from .coordinator import SmartDeviceCoordinator
from .entity import SmartDeviceEntity
from .runtime import SmartDeviceRuntimeData

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置开关实体。"""
    runtime: SmartDeviceRuntimeData = entry.runtime_data
    async_add_entities(
        [
            SmartDeviceSwitch(
                coordinator=runtime.coordinator,
                device_id=entry.data[CONF_DEVICE_ID],
                device_name=entry.title,
            )
        ]
    )


class SmartDeviceSwitch(SmartDeviceEntity, SwitchEntity):
    """设备主开关。"""

    # 主实体沿用设备名，避免出现「设备名 设备名」的重复命名。
    _attr_name = None

    def __init__(
        self,
        coordinator: SmartDeviceCoordinator,
        device_id: str,
        device_name: str,
    ) -> None:
        """初始化开关。"""
        super().__init__(coordinator, device_id, device_name)
        self._attr_unique_id = f"{DOMAIN}_{device_id}_switch"

    @property
    def is_on(self) -> bool | None:
        """返回当前开关状态。"""
        return self.coordinator.data

    async def async_turn_on(self, **kwargs: Any) -> None:
        """开机。"""
        await self._async_control(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """关机。"""
        await self._async_control(False)

    async def _async_control(self, turn_on: bool) -> None:
        """下发指令并做乐观更新。

        服务调用只等待一次接口往返，状态确认放到后台任务里，
        避免前端点击后长时间转圈。
        """
        action = "开机" if turn_on else "关机"
        target = DEVICE_STATUS_ON if turn_on else DEVICE_STATUS_OFF

        try:
            await self.coordinator.api.async_control_device(self._device_id, target)
        except InvalidAuth as err:
            self.coordinator.async_start_reauth()
            raise HomeAssistantError(f"认证已失效，请重新认证: {err}") from err
        except CannotConnect as err:
            raise HomeAssistantError(f"{action}失败: {err}") from err

        _LOGGER.debug("%s指令已下发: %s", action, self._device_id)
        self.coordinator.apply_optimistic_state(turn_on)
        self.hass.async_create_task(
            self._async_verify_state(turn_on),
            f"smart_device_verify_{self._device_id}",
        )

    async def _async_verify_state(self, expected_on: bool) -> None:
        """在后台确认设备是否真的到达目标状态。"""
        expected = DEVICE_STATUS_ON if expected_on else DEVICE_STATUS_OFF

        try:
            async with asyncio.timeout(STATE_CHECK_TIMEOUT):
                for attempt in range(1, STATE_CHECK_RETRIES + 1):
                    await asyncio.sleep(STATE_CHECK_DELAY)

                    try:
                        status = await self.coordinator.api.async_get_device_status(
                            self._device_id
                        )
                    except (CannotConnect, InvalidAuth) as err:
                        _LOGGER.debug(
                            "第 %d 次状态确认失败: %s", attempt, err
                        )
                        continue

                    if status is None:
                        continue

                    if status.get("status") == expected:
                        self.coordinator.async_set_updated_data(expected_on)
                        _LOGGER.debug(
                            "设备 %s 已确认%s",
                            self._device_id,
                            "开启" if expected_on else "关闭",
                        )
                        return

        except TimeoutError:
            _LOGGER.warning(
                "设备 %s 未在 %d 秒内确认到目标状态，改由轮询纠正",
                self._device_id,
                STATE_CHECK_TIMEOUT,
            )
        except Exception:  # noqa: BLE001 - 后台任务异常不应冒泡
            _LOGGER.exception("设备 %s 状态确认任务异常", self._device_id)
            return

        try:
            await self.coordinator.async_request_refresh()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("触发状态刷新失败", exc_info=True)
