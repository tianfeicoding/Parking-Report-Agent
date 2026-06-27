"""支付方式与渠道 profile。

本文件基于清洗后的停车交易数据，生成支付方式和支付渠道的笔数、
占比与金额分布，供 Agent 后续判断报告重点。
"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from app.data.models import CleanedParkingData


@dataclass(frozen=True)
class DistributionItem:
    name: str
    count: int
    count_pct: Decimal
    receivable_amount: Decimal
    collected_amount: Decimal
    actual_deduction_amount: Decimal


@dataclass(frozen=True)
class PaymentProfile:
    payment_methods: list[DistributionItem]
    payment_channels: list[DistributionItem]
    dominant_payment_method: DistributionItem | None
    dominant_payment_channel: DistributionItem | None


def _pct(count: int, total: int) -> Decimal:
    """计算笔数占比，统一保留 1 位小数。"""
    if total == 0:
        return Decimal("0.0")
    return (Decimal(count) / Decimal(total) * Decimal("100")).quantize(Decimal("0.1"))


def _build_distribution(data: CleanedParkingData, field_name: str) -> list[DistributionItem]:
    """按指定字段聚合笔数和金额，生成降序分布列表。"""
    total_count = len(data.rows)
    buckets: dict[str, dict[str, Decimal | int]] = defaultdict(
        lambda: {
            "count": 0,
            "receivable_amount": Decimal("0"),
            "collected_amount": Decimal("0"),
            "actual_deduction_amount": Decimal("0"),
        }
    )

    for row in data.rows:
        name = getattr(row, field_name) or "未填写"
        buckets[name]["count"] += 1
        buckets[name]["receivable_amount"] += row.receivable
        buckets[name]["collected_amount"] += row.collected
        buckets[name]["actual_deduction_amount"] += row.actual_deduction

    items = [
        DistributionItem(
            name=name,
            count=int(values["count"]),
            count_pct=_pct(int(values["count"]), total_count),
            receivable_amount=values["receivable_amount"],
            collected_amount=values["collected_amount"],
            actual_deduction_amount=values["actual_deduction_amount"],
        )
        for name, values in buckets.items()
    ]
    return sorted(items, key=lambda item: (-item.count, item.name))


def build_payment_profile(data: CleanedParkingData) -> PaymentProfile:
    """生成支付方式和支付渠道 profile。"""
    payment_methods = _build_distribution(data, "payment_method")
    payment_channels = _build_distribution(data, "payment_channel")

    return PaymentProfile(
        payment_methods=payment_methods,
        payment_channels=payment_channels,
        dominant_payment_method=payment_methods[0] if payment_methods else None,
        dominant_payment_channel=payment_channels[0] if payment_channels else None,
    )
