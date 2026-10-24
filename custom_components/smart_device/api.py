"""闪优物联云端 API 客户端。

这是整个集成里唯一与厂商接口打交道的地方。所有端点、payload 结构与
错误码行为均来自对真实接口的实测，修改前请先用真实账号验证，
否则极易导致集成整体不可用。

设计约束：
- session 由 Home Assistant 统一创建并注入，本类不创建、不关闭它。
- 所有异常统一收敛为 CannotConnect / InvalidAuth 两类。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import aiohttp

from .const import (
    API_DEVICE_CONTROL_URL,
    API_DEVICE_STATUS_URL,
    API_DEVICES_URL,
    API_LOGIN_URL,
    API_SYNC_URL,
    APP_ID,
    DEFAULT_AREA_ID,
    DEFAULT_LOCALE,
    DEFAULT_TIMEOUT,
    MAX_RETRY_COUNT,
    SESSION_EXPIRED_CODE,
    STATUS_CACHE_TTL,
    SUCCESS_CODE,
)

_LOGGER = logging.getLogger(__name__)


class SmartDeviceError(Exception):
    """集成内所有异常的基类。"""


class CannotConnect(SmartDeviceError):
    """网络不可达、接口报错或响应格式异常。"""


class InvalidAuth(SmartDeviceError):
    """账号密码错误，或凭据已被服务端吊销。"""


class SmartDeviceAPI:
    """闪优物联云端接口封装。"""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
    ) -> None:
        """初始化。

        Args:
            session: Home Assistant 管理的共享 aiohttp 会话。
            username: 带 +86- 前缀的手机号。
            password: 账号密码。
        """
        self._session = session
        self._username = username
        self._password = password

        self._app_id = APP_ID
        self._login_lock = asyncio.Lock()
        self._status_cache: dict[str, tuple[float, dict[str, Any]]] = {}

        self.token: str | None = None
        self.user_id: str | None = None
        self.bpe_session_id: str | None = None

    # ------------------------------------------------------------------
    # 认证
    # ------------------------------------------------------------------

    async def async_login(self) -> None:
        """用账号密码换取 ticket 与 BpeSessionId。"""
        async with self._login_lock:
            await self._async_login_locked()

    async def async_ensure_login(self) -> None:
        """确保当前持有可用的会话 ID。"""
        if self.bpe_session_id is None:
            await self.async_login()

    async def _async_login_locked(self) -> None:
        """登录流程本体，调用方必须已持有 _login_lock。"""
        params = {
            "appid": self._app_id,
            "areaid": DEFAULT_AREA_ID,
            "phone": self._username,
            "password": self._password,
            "locale": DEFAULT_LOCALE,
            "autologin": "true",
        }

        try:
            async with asyncio.timeout(DEFAULT_TIMEOUT):
                async with self._session.get(API_LOGIN_URL, params=params) as resp:
                    resp.raise_for_status()
                    data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(f"登录请求失败: {err}") from err
        except ValueError as err:
            raise CannotConnect(f"登录响应不是合法 JSON: {err}") from err

        if data.get("code") != SUCCESS_CODE:
            raise InvalidAuth(
                f"登录被拒绝 (code={data.get('code')}, msg={data.get('msg')})"
            )

        account = data.get("data") or {}
        ticket = account.get("ticket")
        user_id = account.get("userid")
        if not ticket or user_id is None:
            raise InvalidAuth("登录响应缺少 ticket 或 userid")

        self.token = ticket
        self.user_id = str(user_id)
        _LOGGER.debug("账号 %s 登录成功", self.user_id)

        await self._async_sync_login()

    async def _async_sync_login(self) -> None:
        """二次握手，从响应 Cookie 中取出 BpeSessionId。"""
        payload = {
            "BpeSessionId": "",
            "appId": int(self._app_id),
            "endpointOS": "",
            "clientVersion": "",
            "ticket": self.token,
            "deviceId": "",
            "context": "",
        }
        headers = {
            "Content-Type": "application/json",
            "User-Id": self.user_id or "",
            "Authorization": f"Bearer {self.token}",
        }

        try:
            async with asyncio.timeout(DEFAULT_TIMEOUT):
                async with self._session.post(
                    API_SYNC_URL, json=payload, headers=headers
                ) as resp:
                    resp.raise_for_status()
                    cookie = resp.cookies.get("BpeSessionId")
                    session_id = cookie.value if cookie is not None else None
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(f"同步登录失败: {err}") from err

        if not session_id:
            raise CannotConnect("同步登录未返回 BpeSessionId")

        self.bpe_session_id = session_id

    async def _async_relogin(self, stale_session_id: str | None) -> None:
        """会话过期后重新登录。

        若在等待锁期间其他请求已经完成了刷新，则直接返回，避免并发重复登录。
        """
        async with self._login_lock:
            if (
                self.bpe_session_id is not None
                and self.bpe_session_id != stale_session_id
            ):
                _LOGGER.debug("会话已被其他请求刷新，跳过重复登录")
                return
            await self._async_login_locked()

    # ------------------------------------------------------------------
    # 通用请求
    # ------------------------------------------------------------------

    async def _async_call_api(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        retry: int = 0,
    ) -> dict[str, Any]:
        """发起一次 POST 请求，并在会话过期时自动重登重试。"""
        if retry >= MAX_RETRY_COUNT:
            raise CannotConnect(f"请求重试 {retry} 次后仍然失败")

        await self.async_ensure_login()
        stale_session_id = self.bpe_session_id
        headers = {
            "Content-Type": "application/json",
            "Cookie": f"BpeSessionId={stale_session_id}",
        }

        try:
            async with asyncio.timeout(DEFAULT_TIMEOUT):
                async with self._session.post(
                    url, json=payload, headers=headers
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(f"请求 {url} 失败: {err}") from err
        except ValueError as err:
            raise CannotConnect(f"响应不是合法 JSON: {err}") from err

        if not isinstance(data, dict):
            raise CannotConnect("接口响应格式异常，预期 JSON 对象")

        result_code = data.get("resultCode")

        if result_code == SESSION_EXPIRED_CODE:
            _LOGGER.debug("会话已过期，重新登录后重试")
            await self._async_relogin(stale_session_id)
            return await self._async_call_api(url, payload, retry=retry + 1)

        if result_code != SUCCESS_CODE:
            raise CannotConnect(
                f"接口返回错误 (code={result_code}, msg={data.get('resultMsg')})"
            )

        return data

    # ------------------------------------------------------------------
    # 业务接口
    # ------------------------------------------------------------------

    async def async_get_devices(self) -> list[dict[str, Any]]:
        """获取账号下的设备列表。"""
        await self.async_ensure_login()
        payload = {
            "appId": self._app_id,
            "endpointOS": "",
            "clientVersion": "",
            "deviceId": "",
            "BpeSessionId": self.bpe_session_id,
            "locale": "",
        }

        data = await self._async_call_api(API_DEVICES_URL, payload)

        raw = (data.get("data") or {}).get("mcuinfos")
        if not raw:
            return []

        try:
            devices = json.loads(raw)
        except ValueError as err:
            raise CannotConnect(f"设备列表解析失败: {err}") from err

        if not isinstance(devices, list):
            raise CannotConnect("设备列表格式异常")

        return devices

    async def async_get_device_status(
        self,
        device_id: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any] | None:
        """获取设备状态数据点。

        Args:
            device_id: 设备 mcuid。
            force_refresh: 跳过缓存。开关操作后的确认流程必须为 True，
                否则会读到操作前的旧状态。

        Returns:
            解析后的 datapoint 字典；设备无响应或格式异常时返回 None。
        """
        if not force_refresh:
            cached = self._status_cache.get(device_id)
            if cached is not None and time.monotonic() - cached[0] < STATUS_CACHE_TTL:
                return cached[1]

        payload = {"mcuid": device_id, "appId": self._app_id}
        data = await self._async_call_api(API_DEVICE_STATUS_URL, payload)

        raw = (data.get("data") or {}).get("devicedatas")
        if not raw:
            _LOGGER.debug("设备 %s 未返回状态数据", device_id)
            return None

        try:
            entries = json.loads(raw)
            datapoint = json.loads(entries[0]["datapoint"])
        except (ValueError, KeyError, IndexError, TypeError) as err:
            _LOGGER.warning("设备 %s 状态解析失败: %s", device_id, err)
            return None

        if not isinstance(datapoint, dict):
            _LOGGER.warning("设备 %s 状态格式异常: %s", device_id, datapoint)
            return None

        self._status_cache[device_id] = (time.monotonic(), datapoint)
        return datapoint

    async def async_control_device(self, device_id: str, status: int) -> None:
        """下发开关指令。

        Args:
            device_id: 设备 mcuid。
            status: DEVICE_STATUS_ON 或 DEVICE_STATUS_OFF。
        """
        payload = {
            "mcuid": device_id,
            "appId": self._app_id,
            "datatype": 1,
            "datapoint": json.dumps({"status": status}),
        }

        await self._async_call_api(API_DEVICE_CONTROL_URL, payload)
        # 指令已下发，缓存里的状态必然过期。
        self._status_cache.pop(device_id, None)

    def clear_cache(self) -> None:
        """清空状态缓存。"""
        self._status_cache.clear()
