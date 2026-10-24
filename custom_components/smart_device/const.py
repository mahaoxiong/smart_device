"""闪优物联集成的常量定义。"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

# 集成信息
DOMAIN: Final = "smart_device"
MANUFACTURER: Final = "闪优物联"
MODEL: Final = "Smart Switch"

# ---------------------------------------------------------------------------
# 云端端点
#
# 注意：状态查询与控制端点由厂商以明文 HTTP 提供，且实测未开放 HTTPS。
# 修改前请先用真实账号验证，否则会导致集成完全不可用。
# ---------------------------------------------------------------------------
API_LOGIN_URL: Final = "https://auth.smyoo.com/v1/account/synweblogin"
API_SYNC_URL: Final = "https://auth.smyoo.com/api/gfriend/synloginMobile"
API_DEVICES_URL: Final = "https://auth.smyoo.com/api/gfriend/querydevices"
API_DEVICE_STATUS_URL: Final = "http://api.hjy1314.3uyun.com/api/gfriend/getdevicedata"
API_DEVICE_CONTROL_URL: Final = "http://api.hjy1314.3uyun.com/api/gfriend/setdevicedata"

# 轮询与超时
UPDATE_INTERVAL: Final = timedelta(seconds=30)
DEFAULT_TIMEOUT: Final = 10

# 开关操作后的状态确认
STATE_CHECK_RETRIES: Final = 5
STATE_CHECK_DELAY: Final = 3
STATE_CHECK_TIMEOUT: Final = 30

# API 重试
MAX_RETRY_COUNT: Final = 3

# 协议参数
APP_ID: Final = "1314"
DEFAULT_LOCALE: Final = "zh_CN"
DEFAULT_AREA_ID: Final = "1"

# 协议状态码
SESSION_EXPIRED_CODE: Final = -10297010
SUCCESS_CODE: Final = 0

# 设备状态取值
DEVICE_STATUS_ON: Final = 1
DEVICE_STATUS_OFF: Final = 0
