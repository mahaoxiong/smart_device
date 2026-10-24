"""闪优物联集成入口。

只负责生命周期编排：构造 API、登录、首轮刷新、转发平台。
所有协议细节在 api.py，轮询逻辑在 coordinator.py。
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_PASSWORD,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CannotConnect, InvalidAuth, SmartDeviceAPI
from .coordinator import SmartDeviceCoordinator
from .runtime import SmartDeviceRuntimeData

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置一个配置条目。"""
    api = SmartDeviceAPI(
        session=async_get_clientsession(hass),
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
    )

    try:
        await api.async_login()
    except InvalidAuth as err:
        # 凭据问题需要用户介入，走重新认证流程。
        raise ConfigEntryAuthFailed(str(err)) from err
    except CannotConnect as err:
        # 网络问题由 HA 自动退避重试。
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = SmartDeviceCoordinator(
        hass=hass,
        api=api,
        device_id=entry.data[CONF_DEVICE_ID],
        name=entry.title,
    )
    # 首轮刷新完成后再转发平台，避免实体建好后读到空数据。
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = SmartDeviceRuntimeData(api=api, coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载一个配置条目。"""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
