"""兴泸水务集成常量。"""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "lzss_water"
NAME: Final = "兴泸水务"
MANUFACTURER: Final = "兴泸水务"
MODEL: Final = "水费查询"
CONFIGURATION_URL: Final = "https://osh.lzss.com/"

CONF_ACCOUNT_NUMBER: Final = "account_number"
CONF_TOKEN: Final = "token"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_SCAN_INTERVAL_HOURS: Final = 12
MIN_SCAN_INTERVAL_HOURS: Final = 1
MAX_SCAN_INTERVAL_HOURS: Final = 168

API_BASE_URL: Final = "https://osh.lzss.com/wx_lz/bill/arrearageKoi"
API_TIMEOUT: Final = 15
API_USER_AGENT: Final = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

ATTR_ACCOUNT_NUMBER: Final = "account_number"
ATTR_BILLING_MONTH: Final = "billing_month"
ATTR_BILLS: Final = "bills"
ATTR_LAST_UPDATE: Final = "last_update"
ATTR_UNPAID_AMOUNT: Final = "unpaid_amount"
ATTR_UNPAID_COUNT: Final = "unpaid_count"
