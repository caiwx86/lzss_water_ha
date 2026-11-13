"""兴泸水务诊断信息。"""

from __future__ import annotations

import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ACCOUNT_NUMBER, CONF_TOKEN, DOMAIN
from .coordinator import LzssWaterDataUpdateCoordinator

_REDACTED = "**REDACTED**"


def _normalize(key: Any) -> str:
    """归一化字段名。"""
    return re.sub(r"[\s_\-./\\]", "", str(key)).lower()


_MASKED_KEYS = {_normalize(key) for key in (CONF_ACCOUNT_NUMBER, "user_no", "userno")}
_REDACTED_KEYS = {
    _normalize(key)
    for key in (
        CONF_TOKEN,
        "authorization",
        "password",
        "name",
        "username",
        "account_name",
        "customername",
        "address",
        "useraddress",
        "accountaddress",
        "addressdetail",
        "installaddress",
        "phone",
        "mobile",
        "idcard",
        "id_number",
        "户名",
        "姓名",
        "地址",
        "电话",
        "手机号",
        "身份证",
    )
}


def _mask(value: Any) -> str:
    """只保留末尾 4 位，便于识别账户但不泄露完整户号。"""
    text = str(value)
    if len(text) <= 4:
        return "*" * len(text)
    return "*" * (len(text) - 4) + text[-4:]


def _redact(value: Any) -> Any:
    """递归脱敏。"""
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, child in value.items():
            normalized = _normalize(key)
            if normalized in _REDACTED_KEYS:
                redacted[key] = _REDACTED
            elif normalized in _MASKED_KEYS:
                redacted[key] = _mask(child)
            else:
                redacted[key] = _redact(child)
        return redacted
    if isinstance(value, list):
        return [_redact(child) for child in value]
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """返回用于问题排查的诊断信息。"""
    coordinator: LzssWaterDataUpdateCoordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": {
            "domain": DOMAIN,
            "version": entry.version,
            "data": _redact(dict(entry.data)),
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval is not None
                else None
            ),
            "last_exception": (
                str(coordinator.last_exception)
                if coordinator.last_exception is not None
                else None
            ),
        },
        "data": _redact(data.as_dict()) if data is not None else None,
    }
