"""兴泸水务配置流程。"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import LzssWaterApiClient
from .const import (
    CONF_ACCOUNT_NUMBER,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    MAX_SCAN_INTERVAL_HOURS,
    MIN_SCAN_INTERVAL_HOURS,
    NAME,
)
from .exceptions import (
    LzssWaterAuthError,
    LzssWaterConnectionError,
    LzssWaterDataError,
    LzssWaterError,
)

_LOGGER = logging.getLogger(__name__)

TOKEN_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)


async def _async_validate_input(
    hass: HomeAssistant, account_number: str, token: str
) -> None:
    """调用接口验证户号和令牌是否可用。"""
    client = LzssWaterApiClient(async_get_clientsession(hass), account_number, token)
    data = await client.async_fetch_bill()
    if all(
        value is None for value in (data.balance, data.unpaid_count, data.unpaid_amount)
    ):
        raise LzssWaterDataError("接口未返回可识别的水费数据")


class LzssWaterConfigFlow(ConfigFlow, domain=DOMAIN):
    """处理兴泸水务的配置、重认证流程。"""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """添加账户。"""
        errors: dict[str, str] = {}
        if user_input is not None:
            account_number = str(user_input[CONF_ACCOUNT_NUMBER]).strip()
            token = str(user_input[CONF_TOKEN]).strip()

            await self.async_set_unique_id(account_number)
            self._abort_if_unique_id_configured()

            try:
                await _async_validate_input(self.hass, account_number, token)
            except LzssWaterAuthError:
                errors["base"] = "invalid_auth"
            except LzssWaterDataError:
                errors["base"] = "no_data"
            except LzssWaterConnectionError:
                errors["base"] = "cannot_connect"
            except LzssWaterError:
                _LOGGER.exception("验证兴泸水务账户时发生错误")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"{NAME} {account_number}",
                    data={
                        CONF_ACCOUNT_NUMBER: account_number,
                        CONF_TOKEN: token,
                    },
                    options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL_HOURS},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCOUNT_NUMBER): selector.TextSelector(),
                    vol.Required(CONF_TOKEN): TOKEN_SELECTOR,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """令牌过期时进入重新授权流程。"""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """更新访问令牌。"""
        entry_id = self.context.get("entry_id")
        entry: ConfigEntry | None = (
            self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
        )
        if entry is None:
            return self.async_abort(reason="unknown")

        errors: dict[str, str] = {}
        if user_input is not None:
            token = str(user_input[CONF_TOKEN]).strip()
            try:
                await _async_validate_input(
                    self.hass, entry.data[CONF_ACCOUNT_NUMBER], token
                )
            except LzssWaterAuthError:
                errors["base"] = "invalid_auth"
            except LzssWaterDataError:
                errors["base"] = "no_data"
            except LzssWaterConnectionError:
                errors["base"] = "cannot_connect"
            except LzssWaterError:
                _LOGGER.exception("重新授权兴泸水务账户时发生错误")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_TOKEN: token},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): TOKEN_SELECTOR}),
            errors=errors,
            description_placeholders={
                "account_number": entry.data[CONF_ACCOUNT_NUMBER]
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """返回选项流程。"""
        return LzssWaterOptionsFlow()


class LzssWaterOptionsFlow(OptionsFlow):
    """调整更新间隔等选项。"""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """处理选项表单。"""
        entry = self.hass.config_entries.async_get_entry(self.handler)
        if entry is None:
            return self.async_abort(reason="unknown")

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])},
            )

        current = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_SCAN_INTERVAL_HOURS,
                            max=MAX_SCAN_INTERVAL_HOURS,
                        ),
                    )
                }
            ),
        )
