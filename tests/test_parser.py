"""解析器单元测试（不依赖 Home Assistant）。"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
import unittest
from pathlib import Path

COMPONENT_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "lzss_water"

# 用命名空间包加载被测模块，避免执行 __init__.py（它会导入 Home Assistant）。
if "lzss_water" not in sys.modules:
    package = types.ModuleType("lzss_water")
    package.__path__ = [str(COMPONENT_DIR)]
    sys.modules["lzss_water"] = package

parser = importlib.import_module("lzss_water.parser")
exceptions = importlib.import_module("lzss_water.exceptions")


class ParseResponseTests(unittest.TestCase):
    """JSON 响应解析测试。"""

    def test_nested_english_fields(self) -> None:
        data = parser.parse_response(
            {
                "code": 10000,
                "data": {
                    "userNo": "12345678",
                    "userName": "张三",
                    "balance": "\u00a512.34",
                    "arrearageCount": "2",
                    "arrearageAmount": "56.70",
                    "billMonth": "2026-10",
                    "address": "江阳区某某路 1 号",
                },
            }
        )
        self.assertEqual(data.balance, 12.34)
        self.assertEqual(data.unpaid_count, 2)
        self.assertEqual(data.unpaid_amount, 56.7)
        self.assertEqual(data.billing_month, "2026-10")
        self.assertEqual(data.account_name, "张三")
        self.assertEqual(data.address, "江阳区某某路 1 号")
        self.assertTrue(data.has_unpaid)

    def test_chinese_fields(self) -> None:
        data = parser.parse_response(
            {
                "code": "00000",
                "data": {
                    "余额": "1,234.56 元",
                    "未缴费笔数": "3 笔",
                    "未缴费金额": "88.80 元",
                },
            }
        )
        self.assertEqual(data.balance, 1234.56)
        self.assertEqual(data.unpaid_count, 3)
        self.assertEqual(data.unpaid_amount, 88.8)

    def test_unpaid_amount_does_not_populate_balance(self) -> None:
        data = parser.parse_response({"code": 200, "data": {"unpaidAmount": "15.00"}})
        self.assertIsNone(data.balance)
        self.assertEqual(data.unpaid_amount, 15.0)
        self.assertTrue(data.has_unpaid)

    def test_generic_fields_under_unpaid_context(self) -> None:
        data = parser.parse_response(
            {
                "code": 10000,
                "data": {
                    "arrearage": {"count": 2, "amount": "56.70"},
                },
            }
        )
        self.assertEqual(data.unpaid_count, 2)
        self.assertEqual(data.unpaid_amount, 56.7)

    def test_bill_list_fallback(self) -> None:
        data = parser.parse_response(
            {
                "code": 200,
                "data": {
                    "list": [
                        {"month": "2026-09", "amount": "10.00"},
                        {"month": "2026-10", "amount": 20.5},
                    ]
                },
            }
        )
        self.assertEqual(data.unpaid_count, 2)
        self.assertEqual(data.unpaid_amount, 30.5)
        self.assertEqual(len(data.unpaid_bills), 2)

    def test_paid_bills_are_ignored(self) -> None:
        data = parser.parse_response(
            {
                "code": 200,
                "data": {
                    "欠费列表": [
                        {"账期": "2026-09", "金额": 10, "状态": "已缴"},
                        {"账期": "2026-10", "金额": 20, "状态": "未缴"},
                    ]
                },
            }
        )
        self.assertEqual(data.unpaid_count, 1)
        self.assertEqual(data.unpaid_amount, 20)
        self.assertEqual(data.unpaid_bills[0].period, "2026-10")

    def test_not_settled_status_is_unpaid(self) -> None:
        data = parser.parse_response(
            {
                "code": 200,
                "data": {
                    "欠费列表": [
                        {"账期": "2026-10", "金额": 20, "状态": "未结清"},
                    ]
                },
            }
        )
        self.assertEqual(data.unpaid_count, 1)
        self.assertEqual(data.unpaid_amount, 20)

    def test_bill_level_amount_is_not_used_as_summary(self) -> None:
        data = parser.parse_response(
            {
                "code": 200,
                "data": {
                    "欠费列表": [
                        {"账期": "2026-09", "欠费金额": 10},
                        {"账期": "2026-10", "欠费金额": 20},
                    ]
                },
            }
        )
        self.assertEqual(data.unpaid_count, 2)
        self.assertEqual(data.unpaid_amount, 30)

    def test_payment_history_is_not_treated_as_unpaid(self) -> None:
        data = parser.parse_response(
            {
                "code": 200,
                "data": {
                    "paymentHistory": [
                        {"month": "2026-09", "amount": "10.00"},
                        {"month": "2026-10", "amount": "20.00"},
                    ]
                },
            }
        )
        self.assertIsNone(data.unpaid_count)
        self.assertIsNone(data.unpaid_amount)
        self.assertFalse(data.unpaid_bills)

    def test_root_bill_list(self) -> None:
        data = parser.parse_response(
            [
                {"month": "2026-09", "amount": "10.00"},
                {"month": "2026-10", "amount": "20.00"},
            ]
        )
        self.assertEqual(data.unpaid_count, 2)
        self.assertEqual(data.unpaid_amount, 30.0)

    def test_empty_payload(self) -> None:
        with self.assertLogs("lzss_water.parser", level="WARNING"):
            data = parser.parse_response({"code": 200, "data": {}})
        self.assertIsNone(data.balance)
        self.assertIsNone(data.unpaid_count)
        self.assertIsNone(data.unpaid_amount)
        self.assertIsNone(data.has_unpaid)

    def test_auth_error(self) -> None:
        with self.assertRaises(exceptions.LzssWaterAuthError):
            parser.parse_response(
                {"code": 10001, "description": "token过期，请重新授权"}
            )

    def test_business_error(self) -> None:
        with self.assertRaises(exceptions.LzssWaterApiError) as context:
            parser.parse_response({"code": 500, "description": "系统繁忙"})
        self.assertEqual(context.exception.code, 500)

    def test_negative_and_comma_amounts(self) -> None:
        data = parser.parse_response(
            {"code": 200, "data": {"balance": "-1,234.50", "欠费金额": "0.00元"}}
        )
        self.assertEqual(data.balance, -1234.5)
        self.assertEqual(data.unpaid_amount, 0)
        self.assertFalse(data.has_unpaid)


class ParseHtmlTests(unittest.TestCase):
    """旧版 HTML 响应兼容测试。"""

    @unittest.skipUnless(
        importlib.util.find_spec("bs4") is not None, "需要 beautifulsoup4"
    )
    def test_parse_legacy_listview(self) -> None:
        data = parser.parse_html(
            """
            <html><body><ul id="listview">
              <li>账户余额：123.45 元</li>
              <li>未缴费笔数：2 笔</li>
              <li>未缴费金额：56.70 元</li>
            </ul></body></html>
            """
        )
        self.assertEqual(data.balance, 123.45)
        self.assertEqual(data.unpaid_count, 2)
        self.assertEqual(data.unpaid_amount, 56.7)


if __name__ == "__main__":
    unittest.main()
