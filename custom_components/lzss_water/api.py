"""兴泸水务 HTTP 客户端。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

from .const import API_BASE_URL, API_TIMEOUT, API_USER_AGENT
from .exceptions import (
    LzssWaterAuthError,
    LzssWaterConnectionError,
    LzssWaterDataError,
)
from .models import WaterBillData
from .parser import parse_html, parse_response


class LzssWaterApiClient:
    """封装兴泸水务账单查询接口。

    使用 Home Assistant 共享的 aiohttp 会话，调用方无需关闭会话。
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        account_number: str,
        token: str,
        timeout: float = API_TIMEOUT,
    ) -> None:
        """初始化客户端。"""
        self._session = session
        self._account_number = account_number
        self._token = token.strip()
        self._timeout = timeout

    @property
    def account_number(self) -> str:
        """返回户号。"""
        return self._account_number

    async def async_fetch_bill(self) -> WaterBillData:
        """查询当前户号的水费数据。"""
        if not self._token:
            raise LzssWaterAuthError("未配置访问令牌")

        headers = {
            "User-Agent": API_USER_AGENT,
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": self._token,
        }

        try:
            async with asyncio.timeout(self._timeout):
                async with self._session.post(
                    API_BASE_URL,
                    json={"userNo": self._account_number},
                    headers=headers,
                ) as response:
                    status = response.status
                    content_type = response.headers.get("Content-Type", "")
                    text = await response.text()
        except TimeoutError as err:
            raise LzssWaterConnectionError(
                f"请求兴泸水务接口超时（{self._timeout:g} 秒）"
            ) from err
        except aiohttp.ClientError as err:
            raise LzssWaterConnectionError(f"连接兴泸水务接口失败: {err}") from err

        if status in (401, 403):
            raise LzssWaterAuthError(f"接口返回 HTTP {status}，访问令牌可能已失效")
        if status >= 400:
            raise LzssWaterConnectionError(f"接口返回 HTTP {status}")

        body = text.strip()
        if not body:
            raise LzssWaterDataError("接口返回了空响应")

        try:
            payload: Any = json.loads(body)
        except json.JSONDecodeError:
            if "html" in content_type.lower() or body.startswith("<"):
                return parse_html(body)
            raise LzssWaterDataError("接口返回的内容不是有效的 JSON") from None

        return parse_response(payload)
