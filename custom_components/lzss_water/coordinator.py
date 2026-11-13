"""兴泸水务数据更新协调器。"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import LzssWaterApiClient
from .const import (
    CONF_ACCOUNT_NUMBER,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    MAX_SCAN_INTERVAL_HOURS,
    MIN_SCAN_INTERVAL_HOURS,
    NAME,
)
from .exceptions import LzssWaterAuthError, LzssWaterError
from .models import WaterBillData

_LOGGER = logging.getLogger(__name__)


class LzssWaterDataUpdateCoordinator(DataUpdateCoordinator[WaterBillData]):
    """按设定间隔获取水费数据。"""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: LzssWaterApiClient,
    ) -> None:
        """初始化协调器。"""
        interval = _interval_from_options(entry)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.data[CONF_ACCOUNT_NUMBER]}",
            update_interval=interval,
        )
        self.config_entry = entry
        self.client = client
        self.account_number: str = entry.data[CONF_ACCOUNT_NUMBER]
        self.device_name = f"{NAME} {self.account_number}"
        self.last_fetched_at: datetime | None = None

    async def _async_update_data(self) -> WaterBillData:
        """执行一次数据更新。"""
        try:
            data = await self.client.async_fetch_bill()
        except LzssWaterAuthError as err:
            raise ConfigEntryAuthFailed(f"访问令牌无效或已过期: {err}") from err
        except LzssWaterError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:  # 协调器边界兜底，避免集成崩溃
            _LOGGER.exception("更新水费数据时发生未预期的错误")
            raise UpdateFailed(f"更新水费数据失败: {err}") from err

        self.last_fetched_at = dt_util.now()
        _LOGGER.debug(
            "已更新户号 %s 的水费数据: 余额=%s, 欠费笔数=%s, 欠费金额=%s",
            self.account_number,
            data.balance,
            data.unpaid_count,
            data.unpaid_amount,
        )
        return data


def _interval_from_options(entry: ConfigEntry) -> timedelta:
    """从选项读取更新间隔，非法值回退到默认值。"""
    raw = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS)
    try:
        hours = float(raw)
    except (TypeError, ValueError):
        _LOGGER.warning(
            "更新间隔 %s 无效，使用默认值 %s 小时", raw, DEFAULT_SCAN_INTERVAL_HOURS
        )
        hours = DEFAULT_SCAN_INTERVAL_HOURS
    if not math.isfinite(hours) or hours <= 0:
        hours = DEFAULT_SCAN_INTERVAL_HOURS
    return timedelta(
        hours=max(MIN_SCAN_INTERVAL_HOURS, min(hours, MAX_SCAN_INTERVAL_HOURS))
    )
