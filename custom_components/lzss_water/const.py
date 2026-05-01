"""水费查询集成常量定义。"""
from datetime import timedelta

DOMAIN = "lzss_water"
DEFAULT_SCAN_INTERVAL = timedelta(hours=11, minutes=58, seconds=50)
CONF_ACCOUNT_NUMBER = "account_number"
CONF_TOKEN = "token"
API_BASE_URL = "https://osh.lzss.com/wx_lz/bill/arrearageKoi"

# 传感器ID
SENSOR_BALANCE = "lzss_water_balance"     # 余额传感器

# Error messages
ERROR_CONNECTION = "connection_error"
ERROR_TIMEOUT = "timeout_error"
ERROR_UNKNOWN = "unknown_error" 