"""兴泸水务接口响应解析器。

上游接口没有公开文档，返回结构也曾多次变化，因此这里采用「精确字段名匹配 +
保守的账单列表回退」两层策略：

1. 递归查找常见的中英文字段名（余额、欠费笔数、欠费金额等）；
2. 如果响应主体是账单数组，则根据账单记录推导欠费笔数和欠费金额。

解析器不依赖 Home Assistant，方便单独做单元测试。
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Iterator, Mapping
from typing import Any

from .exceptions import LzssWaterApiError, LzssWaterAuthError, LzssWaterDataError
from .models import UnpaidBill, WaterBillData

_LOGGER = logging.getLogger(__name__)

_MISSING = object()

# 上游成功码目前观察到 10001 表示 token 过期，推测成功码为 10000；
# 同时兼容常见的 0 / 200 / "00000" 等写法。
_SUCCESS_TEXT_CODES = frozenset(
    {"0", "200", "10000", "0000", "00000", "000000", "success", "ok"}
)
_AUTH_TEXT_CODES = frozenset({"401", "403", "10001", "10002"})
_AUTH_HINTS = (
    "token",
    "授权",
    "登录",
    "过期",
    "失效",
    "未认证",
    "重新授权",
    "unauthorized",
    "invalid auth",
    "expired",
)

BALANCE_KEYS = frozenset(
    {
        "balance",
        "accountbalance",
        "availablebalance",
        "currentbalance",
        "remainingbalance",
        "accountremain",
        "余额",
        "账户余额",
        "剩余余额",
        "当前余额",
        "水费余额",
        "预存余额",
        "yue",
    }
)
UNPAID_COUNT_KEYS = frozenset(
    {
        "unpaidcount",
        "arrearagecount",
        "arrearagenum",
        "arrearscount",
        "unpaidnum",
        "owecount",
        "owedcount",
        "totalunpaidcount",
        "欠费笔数",
        "未缴费笔数",
        "待缴费笔数",
        "欠费次数",
        "欠费数量",
    }
)
UNPAID_AMOUNT_KEYS = frozenset(
    {
        "unpaidamount",
        "arrearageamount",
        "arrearagemoney",
        "arrearsamount",
        "totalarrears",
        "totalunpaid",
        "totalunpaidamount",
        "oweamount",
        "owedamount",
        "debtamount",
        "欠费金额",
        "未缴费金额",
        "欠费总额",
        "欠费合计",
        "欠费总金额",
        "应缴金额",
        "应缴总额",
        "待缴金额",
    }
)
BILLING_MONTH_KEYS = frozenset(
    {
        "billmonth",
        "billingmonth",
        "billperiod",
        "billingperiod",
        "currentmonth",
        "month",
        "period",
        "账期",
        "月份",
        "当前月份",
        "水费月份",
        "所属期",
        "抄表月份",
    }
)
ACCOUNT_NAME_KEYS = frozenset(
    {
        "username",
        "customername",
        "accountname",
        "ownername",
        "户名",
        "客户名称",
        "用户名称",
    }
)
ADDRESS_KEYS = frozenset(
    {
        "address",
        "useraddress",
        "accountaddress",
        "addressdetail",
        "installaddress",
        "addr",
        "useraddr",
        "用水地址",
        "用户地址",
        "安装地址",
        "地址",
    }
)

BILL_AMOUNT_KEYS = frozenset(
    {
        "amount",
        "billamount",
        "fee",
        "money",
        "price",
        "receivable",
        "receivableamount",
        "payable",
        "payableamount",
        "payamount",
        "shouldpay",
        "应缴金额",
        "欠费金额",
        "金额",
        "水费",
        "费用",
        "水费金额",
        "应缴费用",
        "未缴金额",
    }
)
BILL_PERIOD_KEYS = frozenset(
    {
        "period",
        "month",
        "billmonth",
        "billdate",
        "billingmonth",
        "date",
        "账期",
        "月份",
        "所属期",
        "水费月份",
        "抄表月份",
        "账单日期",
        "出账日期",
    }
)
BILL_DUE_KEYS = frozenset(
    {
        "duedate",
        "deadline",
        "paydate",
        "paydeadline",
        "expiredate",
        "缴费期限",
        "应缴日期",
        "截止日期",
        "缴费截止日期",
    }
)
BILL_STATUS_KEYS = frozenset(
    {
        "status",
        "state",
        "paystatus",
        "paymentstatus",
        "payflag",
        "ispaid",
        "缴费状态",
        "状态",
        "是否缴费",
    }
)
BILL_DESCRIPTION_KEYS = frozenset(
    {
        "description",
        "desc",
        "type",
        "name",
        "item",
        "billtype",
        "费用类型",
        "项目",
        "摘要",
        "备注",
    }
)

_PAID_HINTS = (
    "已缴",
    "已交",
    "已支付",
    "已结清",
    "缴费成功",
    "结清",
    "paid",
    "settled",
    "success",
)
_UNPAID_HINTS = (
    "未缴",
    "欠费",
    "待缴",
    "应缴",
    "未支付",
    "未结清",
    "not paid",
    "not settled",
    "unpaid",
    "arrear",
    "overdue",
)
_UNPAID_CONTEXT_HINTS = (
    "unpaid",
    "arrear",
    "owe",
    "debt",
    "欠费",
    "未缴",
    "待缴",
    "应缴",
    "未支付",
)
_GENERIC_COUNT_KEYS = frozenset(
    {"count", "num", "number", "qty", "笔数", "数量", "次数"}
)
_GENERIC_AMOUNT_KEYS = frozenset(
    {"amount", "money", "fee", "金额", "费用", "总计", "合计"}
)
_GENERIC_LIST_KEYS = frozenset(
    {
        "rows",
        "list",
        "bills",
        "billlist",
        "details",
        "detail",
        "items",
        "records",
        "data",
    }
)

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_CLEAN_RE = re.compile(r"\s+")


def parse_response(response: Any) -> WaterBillData:
    """解析 JSON 响应（含业务状态码信封）。"""
    if not isinstance(response, (Mapping, list, tuple)):
        raise LzssWaterDataError(f"无法解析接口响应类型: {type(response).__name__}")

    code = _first_present(
        response, ("code", "status", "errcode", "errorCode", "error_code")
    )
    if code is not _MISSING and not _is_success_code(code):
        description = _first_present(
            response, ("description", "message", "msg", "errmsg", "error")
        )
        message = _to_text(description) or f"接口返回错误码 {code}"
        if _is_auth_error(code, message):
            raise LzssWaterAuthError(message)
        raise LzssWaterApiError(message, code=code)

    payload = _unwrap(response)
    data = WaterBillData(raw=response)

    if isinstance(payload, Mapping):
        _apply_scalars(data, payload)
    elif isinstance(response, Mapping):
        # 主体是数组时，仍尝试读取信封旁的汇总字段
        _apply_scalars(data, response)

    data.unpaid_bills = _extract_bills(response)
    _apply_bill_fallbacks(data)

    if all(
        value is None
        for value in (
            data.balance,
            data.unpaid_count,
            data.unpaid_amount,
            data.billing_month,
        )
    ):
        _LOGGER.warning(
            "未能从接口响应中识别水费字段，响应键: %s", _describe_shape(response)
        )
    return data


def parse_html(html: str) -> WaterBillData:
    """解析旧版网页接口返回的 HTML（作为兼容回退）。"""
    try:
        from bs4 import BeautifulSoup
    except ImportError as err:  # pragma: no cover - 依赖已在 manifest 中声明
        raise LzssWaterDataError("缺少 beautifulsoup4，无法解析 HTML 响应") from err

    soup = BeautifulSoup(html, "html.parser")
    container = soup.find("ul", {"id": "listview"}) or soup.body or soup
    texts = [
        _clean_text(" ".join(item.stripped_strings))
        for item in container.find_all("li")
    ]
    if not texts:
        texts = [_clean_text(text) for text in container.stripped_strings][:500]

    data = WaterBillData(raw={"format": "html"})
    data.balance = _label_value(
        texts, ("账户余额", "水费余额", "当前余额", "剩余余额", "余额"), _to_float
    )
    data.unpaid_count = _label_value(
        texts, ("未缴费笔数", "欠费笔数", "待缴费笔数", "欠费次数"), _to_int
    )
    data.unpaid_amount = _label_value(
        texts, ("未缴费金额", "欠费金额", "欠费总额", "应缴金额", "待缴金额"), _to_float
    )

    if all(
        value is None for value in (data.balance, data.unpaid_count, data.unpaid_amount)
    ):
        raise LzssWaterDataError("未在 HTML 响应中找到水费数据")
    return data


def _first_present(response: Any, keys: tuple[str, ...]) -> Any:
    """返回第一个存在且非 None 的键值，找不到时返回哨兵对象。"""
    if not isinstance(response, Mapping):
        return _MISSING
    for key in keys:
        if key in response and response[key] is not None:
            return response[key]
    return _MISSING


def _unwrap(response: Any) -> Any:
    """剥掉常见的结果信封，返回真正的数据主体。"""
    if not isinstance(response, Mapping):
        return response
    for key in ("data", "result", "body"):
        if key in response and response[key] is not None:
            return response[key]
    for key in ("rows", "list"):
        if isinstance(response.get(key), list):
            return response[key]
    return response


def _is_success_code(code: Any) -> bool:
    """判断业务状态码是否表示成功。"""
    if isinstance(code, bool):
        return code
    if isinstance(code, (int, float)):
        return code in (0, 200, 10000)
    return str(code).strip().lower() in _SUCCESS_TEXT_CODES


def _is_auth_error(code: Any, message: str) -> bool:
    """判断业务错误是否属于鉴权问题。"""
    if isinstance(code, bool):
        return False
    if isinstance(code, (int, float)) and code in (401, 403, 10001, 10002):
        return True
    if str(code).strip().lower() in _AUTH_TEXT_CODES:
        return True
    lowered = message.lower()
    return any(hint in lowered for hint in _AUTH_HINTS)


def _apply_scalars(data: WaterBillData, payload: Any) -> None:
    """从任意嵌套结构中提取标量字段。"""
    if (value := _find_scalar(payload, BALANCE_KEYS)) is not None:
        data.balance = _to_float(value)
    if (value := _find_scalar(payload, UNPAID_COUNT_KEYS)) is not None:
        data.unpaid_count = _to_int(value)
    if (
        data.unpaid_count is None
        and (
            value := _find_context_scalar(
                payload, _GENERIC_COUNT_KEYS, _UNPAID_CONTEXT_HINTS
            )
        )
        is not None
    ):
        data.unpaid_count = _to_int(value)
    if (value := _find_scalar(payload, UNPAID_AMOUNT_KEYS)) is not None:
        data.unpaid_amount = _to_float(value)
    if (
        data.unpaid_amount is None
        and (
            value := _find_context_scalar(
                payload, _GENERIC_AMOUNT_KEYS, _UNPAID_CONTEXT_HINTS
            )
        )
        is not None
    ):
        data.unpaid_amount = _to_float(value)
    if (
        value := _find_scalar(payload, BILLING_MONTH_KEYS, allow_list_items=True)
    ) is not None:
        data.billing_month = _to_text(value)
    if (value := _find_scalar(payload, ACCOUNT_NAME_KEYS)) is not None:
        data.account_name = _to_text(value)
    if (value := _find_scalar(payload, ADDRESS_KEYS)) is not None:
        data.address = _to_text(value)


def _iter_scalars(
    value: Any, path: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], str, Any]]:
    """深度遍历所有标量，产出 (路径, 键名, 值)。"""
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = (*path, key_text)
            if isinstance(child, (Mapping, list, tuple)):
                yield from _iter_scalars(child, child_path)
            else:
                yield child_path, key_text, child
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            child_path = (*path, f"[{index}]")
            if isinstance(child, (Mapping, list, tuple)):
                yield from _iter_scalars(child, child_path)
            else:
                yield child_path, "", child


def _find_scalar(
    payload: Any, aliases: frozenset[str], *, allow_list_items: bool = False
) -> Any:
    """查找字段名匹配的最浅层标量，匹配不到时返回 None。"""
    matches: list[tuple[int, tuple[str, ...], Any]] = []
    for path, key, value in _iter_scalars(payload):
        if not key or not _has_value(value):
            continue
        if not allow_list_items and any(part.startswith("[") for part in path[:-1]):
            # 汇总字段只从对象层级读取，避免把单条账单的金额当成总额
            continue
        if _normalize(key) in aliases:
            matches.append((len(path), path, value))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0])
    return matches[0][2]


def _find_context_scalar(
    payload: Any, keys: frozenset[str], contexts: tuple[str, ...], max_depth: int = 3
) -> Any:
    """在欠费相关父节点下查找通用字段名（如 arrearage.count）。"""
    matches: list[tuple[int, tuple[str, ...], Any]] = []
    for path, key, value in _iter_scalars(payload):
        if len(path) > max_depth or not key or not _has_value(value):
            continue
        if any(part.startswith("[") for part in path[:-1]):
            # 只采信汇总字段，忽略账单数组内部的同名字段
            continue
        if _normalize(key) not in keys:
            continue
        parent = _normalize(".".join(path[:-1]))
        if any(context in parent for context in contexts):
            matches.append((len(path), path, value))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0])
    return matches[0][2]


def _iter_lists(
    value: Any, path: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], list[Any]]]:
    """深度遍历所有数组，产出 (路径, 数组)。"""
    if isinstance(value, list):
        yield path, value
        for index, child in enumerate(value):
            if isinstance(child, (Mapping, list)):
                yield from _iter_lists(child, (*path, f"[{index}]"))
    elif isinstance(value, Mapping):
        for key, child in value.items():
            child_path = (*path, str(key))
            if isinstance(child, (Mapping, list)):
                yield from _iter_lists(child, child_path)


def _extract_bills(response: Any) -> list[UnpaidBill]:
    """从账单数组中提取未缴费记录。

    仅在路径包含欠费相关关键字，或数组键名为 rows/list/bills 等通用容器且
    元素确实具有账单特征时才采信，避免把缴费历史误判为欠费。
    """
    bills: list[UnpaidBill] = []
    seen: set[tuple[Any, ...]] = set()

    for path, items in _iter_lists(response):
        if not items or not all(isinstance(item, Mapping) for item in items):
            continue

        context = _normalize(".".join(path))
        hinted = any(hint in context for hint in _UNPAID_CONTEXT_HINTS)
        generic = not path or (path and _normalize(path[-1]) in _GENERIC_LIST_KEYS)
        explicit_unpaid = any(
            (status := _to_text(_get_field(item, BILL_STATUS_KEYS)))
            and _is_unpaid_status(status)
            for item in items
        )
        if (
            not hinted
            and not explicit_unpaid
            and not (generic and _looks_like_bill_list(items))
        ):
            continue

        for item in items:
            bill = _parse_bill(item)
            if bill is None:
                continue
            key = (bill.period, bill.amount, bill.due_date, bill.description)
            if key in seen:
                continue
            seen.add(key)
            bills.append(bill)

    return bills


def _parse_bill(item: Mapping[str, Any]) -> UnpaidBill | None:
    """把一条账单记录转换为 UnpaidBill，已缴记录返回 None。"""
    status = _to_text(_get_field(item, BILL_STATUS_KEYS))
    if status and not _is_unpaid_status(status) and _is_paid_status(status):
        return None

    amount = _to_float(_get_field(item, BILL_AMOUNT_KEYS))
    period = _to_text(_get_field(item, BILL_PERIOD_KEYS))
    due_date = _to_text(_get_field(item, BILL_DUE_KEYS))
    description = _to_text(_get_field(item, BILL_DESCRIPTION_KEYS))

    if amount is None and period is None and due_date is None and description is None:
        return None
    return UnpaidBill(
        period=period,
        amount=amount,
        due_date=due_date,
        description=description,
    )


def _looks_like_bill_list(items: list[Mapping[str, Any]]) -> bool:
    """判断数组元素是否像账单记录。"""
    if not items:
        return False
    if not all(_has_field(item, BILL_AMOUNT_KEYS) for item in items):
        return False
    return any(
        _has_field(item, BILL_PERIOD_KEYS) or _has_field(item, BILL_STATUS_KEYS)
        for item in items
    )


def _is_paid_status(status: str) -> bool:
    """判断账单状态是否表示已缴费。"""
    lowered = status.lower()
    return any(hint in lowered for hint in _PAID_HINTS)


def _is_unpaid_status(status: str) -> bool:
    """判断账单状态是否明确表示未缴费。"""
    lowered = status.lower()
    return any(hint in lowered for hint in _UNPAID_HINTS)


def _apply_bill_fallbacks(data: WaterBillData) -> None:
    """在接口未提供汇总字段时，从账单明细推导欠费笔数和金额。"""
    if not data.unpaid_bills:
        return
    if data.unpaid_count is None:
        data.unpaid_count = len(data.unpaid_bills)
    if data.unpaid_amount is None:
        amounts = [bill.amount for bill in data.unpaid_bills if bill.amount is not None]
        if amounts:
            data.unpaid_amount = round(sum(amounts), 2)


def _get_field(item: Mapping[str, Any], aliases: frozenset[str]) -> Any:
    """按字段名别名从字典中取值。"""
    for key, value in item.items():
        if _normalize(str(key)) in aliases and _has_value(value):
            return value
    return None


def _has_field(item: Mapping[str, Any], aliases: frozenset[str]) -> bool:
    """判断字典是否包含指定别名之一的字段（不要求值非空）。"""
    return any(_normalize(str(key)) in aliases for key in item)


def _has_value(value: Any) -> bool:
    """判断值是否可用于解析。"""
    return value is not None and value != ""


def _normalize(text: str) -> str:
    """归一化字段名：去空格、下划线、连字符并转小写。"""
    return re.sub(r"[\s_\-./\\]", "", text).lower()


def _clean_text(text: str) -> str:
    """压缩 HTML 文本中的空白。"""
    return _CLEAN_RE.sub(" ", text).strip()


def _to_text(value: Any) -> str | None:
    """把值安全转换为字符串。"""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _to_float(value: Any) -> float | None:
    """把接口值安全转换为浮点数，兼容货币符号、千分位和中文单位。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None
    if text in {"无", "暂无", "没有", "--", "-", "/"}:
        return 0.0
    text = text.replace(",", "").replace("，", "")
    text = re.sub(r"\s+", "", text)
    match = _NUMBER_RE.search(text)
    if not match:
        return None
    try:
        number = float(match.group())
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _to_int(value: Any) -> int | None:
    """把接口值安全转换为整数。"""
    number = _to_float(value)
    if number is None:
        return None
    return int(number)


def _label_value(
    texts: list[str],
    labels: tuple[str, ...],
    converter: Any,
) -> Any:
    """在 HTML 文本列表中按标签查找数值。"""
    for label in labels:
        for text in texts:
            if label in text:
                value = converter(text)
                if value is not None:
                    return value
    return None


def _describe_shape(value: Any, depth: int = 0) -> Any:
    """生成响应结构的简短描述，便于排查字段变化。"""
    if depth > 3:
        return "..."
    if isinstance(value, Mapping):
        return {
            str(key): _describe_shape(child, depth + 1)
            for key, child in list(value.items())[:20]
        }
    if isinstance(value, list):
        return [_describe_shape(value[0], depth + 1)] if value else []
    return type(value).__name__
