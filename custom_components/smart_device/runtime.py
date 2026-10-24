"""运行时对象容器。"""

from __future__ import annotations

from dataclasses import dataclass

from .api import SmartDeviceAPI
from .coordinator import SmartDeviceCoordinator


@dataclass
class SmartDeviceRuntimeData:
    """挂在 hass.data 上的每个 config entry 的运行时对象。"""

    api: SmartDeviceAPI
    coordinator: SmartDeviceCoordinator
