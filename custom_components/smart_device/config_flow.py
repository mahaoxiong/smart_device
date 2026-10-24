"""配置流程。

登录与设备选择都在这里完成。API 实例复用 Home Assistant 的共享 aiohttp
会话，因此流程结束后不会遗留未关闭的连接池。
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CannotConnect, InvalidAuth, SmartDeviceAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PHONE_PREFIX = "+86-"


class SmartDeviceConfigFlow(ConfigFlow, domain=DOMAIN):
    """闪优物联配置流程。"""

    VERSION = 1

    def __init__(self) -> None:
        """初始化配置流程。"""
        self._api: SmartDeviceAPI | None = None
        self._devices: list[dict[str, Any]] = []
        self._credentials: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """账号登录。"""
        errors: dict[str, str] = {}

        if user_input is not None:
            phone = user_input[CONF_USERNAME].strip()
            if not phone.startswith(PHONE_PREFIX):
                phone = f"{PHONE_PREFIX}{phone}"

            api = SmartDeviceAPI(
                session=async_get_clientsession(self.hass),
                username=phone,
                password=user_input[CONF_PASSWORD],
            )

            try:
                await api.async_login()
                devices = await api.async_get_devices()
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - 兜底，避免流程卡死
                _LOGGER.exception("登录时发生未预期错误")
                errors["base"] = "unknown"
            else:
                if not devices:
                    return self.async_abort(reason="no_devices")

                self._api = api
                self._devices = devices
                self._credentials = {
                    CONF_USERNAME: phone,
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                }
                return await self.async_step_select_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """选择要接入的设备。"""
        if self._api is None:
            # 流程被重建（例如浏览器刷新），重新走登录。
            return await self.async_step_user()

        errors: dict[str, str] = {}
        options = {
            device["mcuid"]: f"{device.get('mcuname') or device['mcuid']} ({device['mcuid']})"
            for device in self._devices
            if device.get("mcuid")
        }

        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]

            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured()

            try:
                status = await self._api.async_get_device_status(
                    device_id, force_refresh=True
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                if status is None:
                    errors["base"] = "device_offline"
                else:
                    name = next(
                        (
                            device.get("mcuname")
                            for device in self._devices
                            if device.get("mcuid") == device_id
                        ),
                        None,
                    ) or device_id

                    return self.async_create_entry(
                        title=name,
                        data={
                            **self._credentials,
                            CONF_NAME: name,
                            CONF_DEVICE_ID: device_id,
                        },
                    )

        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): vol.In(options),
                }
            ),
            errors=errors,
        )
