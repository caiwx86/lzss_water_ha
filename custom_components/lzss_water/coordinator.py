"""水费查询集成数据更新协调器。"""
from __future__ import annotations

import logging
from datetime import timedelta, datetime
from typing import Any, Dict

import aiohttp
import async_timeout
from bs4 import BeautifulSoup

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import API_BASE_URL, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

class WaterBillDataUpdateCoordinator(DataUpdateCoordinator):
    """水费数据更新协调器类。"""

    def __init__(
        self,
        hass: HomeAssistant,
        account_number: str,
        token: str,
        update_interval: timedelta = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """初始化协调器。"""
        super().__init__(
            hass,
            _LOGGER,
            name="兴泸水务",
            update_interval=update_interval,
        )
        self._account_number = account_number
        self._token = token
        self._session = aiohttp.ClientSession()

    @property
    def account_number(self) -> str:
        """返回账号。"""
        return self._account_number

    async def _fetch_data(self) -> Dict[str, Any]:
        """获取水费数据。"""
        data_json = { "userNo":f"{self._account_number}"}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"{self._token}"
        }

        # 使用 json= 让 aiohttp 正确把 body 序列化为 JSON
        async with self._session.post(API_BASE_URL, json=data_json, headers=headers) as response:
            response.raise_for_status()

            # 根据返回的 Content-Type 决定解析方式：优先处理 JSON，否则回退到 HTML 解析
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                try:
                    resp_json = await response.json()
                except Exception as e:
                    _LOGGER.error("解析 JSON 响应失败: %s", e)
                    raise UpdateFailed(f"解析 JSON 响应失败: {e}")

                balance = self._extract_balance_from_json(resp_json)
                return {"balance": balance}

            # 非 JSON 回退到原始 HTML 解析
            html = await response.text()

        soup = BeautifulSoup(html, 'html.parser')
        listview = soup.find('ul', {'id': 'listview'})

        if not listview:
            raise UpdateFailed("未找到数据列表")

        return {"balance": self._extract_balance(listview)}

    async def _async_update_data(self) -> Dict[str, Any]:
        """从水费网站获取数据。"""
        try:
            async with async_timeout.timeout(10):
                current_date = datetime.now()
                data = await self._fetch_data()

                return {
                    "current_balance": data["balance"],
                }

        except Exception as err:
            _LOGGER.error("获取数据失败: %s", str(err))
            raise UpdateFailed(f"Error: {err}")

    def _extract_balance(self, element: BeautifulSoup) -> float:
        """从HTML元素中提取余额。"""
        try:
            items = element.find_all('li')
            for item in items:
                text = item.text.strip()
                if "余额" in text:
                    value = ''.join(c for c in text if c.isdigit() or c == '.')
                    return float(value) if value else 0.0
            return 0.0
        except Exception as e:
            _LOGGER.error("提取余额时出错: %s", str(e))
            return 0.0

    def _extract_balance_from_json(self, data: Dict[str, Any]) -> float:
        """从 JSON 响应中提取余额。

        该方法尽量兼容几种常见结构：
        - {"balance": 123.45}
        - {"balance": "123.45"}
        - {"data": {"balance": 123.45}}
        - 嵌套或不同命名时，尽最大努力查找包含关键字 "balance" 或 "余额" 的字段。
        """
        try:
            # 直接键
            if isinstance(data, dict):
                # 常用键
                for key in ("balance", "余额", "amount", "balanceAmount"):
                    if key in data:
                        return self._to_float(data[key])

                # 嵌套 data 字段
                if "data" in data and isinstance(data["data"], dict):
                    for key in ("balance", "余额", "amount", "balanceAmount"):
                        if key in data["data"]:
                            return self._to_float(data["data"][key])

                # 遍历所有数值字段尝试匹配字段名中含 balance/余额 的键
                for k, v in data.items():
                    if isinstance(k, str) and ("balance" in k.lower() or "余额" in k):
                        return self._to_float(v)

            # 无法找到时返回 0.0
            return 0.0
        except Exception as e:
            _LOGGER.error("从 JSON 中提取余额出错: %s", e)
            return 0.0

    def _to_float(self, value: Any) -> float:
        """把任意值安全转换为 float，遇到不可解析的返回 0.0。"""
        try:
            if value is None:
                return 0.0
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                # 去掉千分位逗号和空格
                s = value.replace(',', '').strip()
                # 保留数字和小数点、前导负号
                filtered = ''.join(ch for ch in s if (ch.isdigit() or ch in '.-'))
                return float(filtered) if filtered not in ('', '.', '-', '-.') else 0.0
            # 其他类型尝试直接转
            return float(value)
        except Exception:
            return 0.0

    async def async_close(self) -> None:
        """关闭HTTP会话。"""
        await self._session.close() 