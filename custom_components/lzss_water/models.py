"""兴泸水务集成数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class UnpaidBill:
    """一笔未缴费账单。"""

    period: str | None = None
    amount: float | None = None
    due_date: str | None = None
    description: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """返回忽略空值的字典，用于实体属性或诊断。"""
        return {
            key: value
            for key, value in {
                "period": self.period,
                "amount": self.amount,
                "due_date": self.due_date,
                "description": self.description,
            }.items()
            if value is not None
        }


@dataclass(slots=True)
class WaterBillData:
    """一次查询得到的完整水费数据。

    所有字段允许为 None：上游接口返回的字段会随账号、地区或接口版本变化，
    None 表示本次响应中未提供该字段，传感器会显示为 unknown，而不是伪造 0。
    """

    balance: float | None = None
    unpaid_count: int | None = None
    unpaid_amount: float | None = None
    billing_month: str | None = None
    account_name: str | None = None
    address: str | None = None
    unpaid_bills: list[UnpaidBill] = field(default_factory=list)
    raw: Any = field(default=None, repr=False, compare=False)

    @property
    def has_unpaid(self) -> bool | None:
        """根据欠费笔数或欠费金额判断是否存在欠费，无法判断时返回 None。"""
        if self.unpaid_count is not None and self.unpaid_count > 0:
            return True
        if self.unpaid_amount is not None and self.unpaid_amount > 0:
            return True
        if self.unpaid_count is not None or self.unpaid_amount is not None:
            return False
        if self.unpaid_bills:
            return True
        return None

    def as_dict(self) -> dict[str, Any]:
        """返回用于诊断的可序列化字典。"""
        result: dict[str, Any] = {
            key: value
            for key, value in {
                "balance": self.balance,
                "unpaid_count": self.unpaid_count,
                "unpaid_amount": self.unpaid_amount,
                "billing_month": self.billing_month,
                "account_name": self.account_name,
                "address": self.address,
            }.items()
            if value is not None
        }
        if self.unpaid_bills:
            result["unpaid_bills"] = [bill.as_dict() for bill in self.unpaid_bills]
        if self.raw is not None:
            result["raw"] = self.raw
        return result
