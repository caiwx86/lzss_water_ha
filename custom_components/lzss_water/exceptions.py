"""兴泸水务集成异常定义。"""

from __future__ import annotations


class LzssWaterError(Exception):
    """集成内所有异常的基类。"""


class LzssWaterConnectionError(LzssWaterError):
    """连接兴泸水务接口失败（网络、超时或 HTTP 错误）。"""


class LzssWaterAuthError(LzssWaterError):
    """访问令牌缺失、无效或已过期。"""


class LzssWaterApiError(LzssWaterError):
    """接口返回了业务错误。"""

    def __init__(self, message: str, code: str | int | None = None) -> None:
        """初始化业务异常并保存接口错误码。"""
        super().__init__(message)
        self.code = code


class LzssWaterDataError(LzssWaterError):
    """接口响应无法解析。"""
