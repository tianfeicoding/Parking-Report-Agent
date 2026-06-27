"""停车报告硬指标计算。

本文件只基于清洗后的 CSV 数据计算六个评分用硬指标，
这些值不允许由 LLM 生成或覆盖。
"""

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.data.models import CleanedParkingData


@dataclass(frozen=True)
class TopPaymentMethod:
    method: str
    count: int


@dataclass(frozen=True)
class ParkingMetrics:
    total_transactions: int
    total_receivable: Decimal
    total_collected: Decimal
    total_actual_deductions: Decimal
    collection_rate_pct: Decimal
    top_payment_method: TopPaymentMethod | None


def compute_parking_metrics(data: CleanedParkingData) -> ParkingMetrics:
    """计算报告必须展示的六个硬指标。"""
    total_transactions = len(data.rows)
    total_receivable = sum((row.receivable for row in data.rows), Decimal("0"))
    total_collected = sum((row.collected for row in data.rows), Decimal("0"))
    total_actual_deductions = sum((row.actual_deduction for row in data.rows), Decimal("0"))

    if total_receivable == 0:
        collection_rate_pct = Decimal("0.0")
    else:
        collection_rate_pct = (total_collected / total_receivable * Decimal("100")).quantize(
            Decimal("0.1"),
            rounding=ROUND_HALF_UP,
        )

    payment_counts = Counter(row.payment_method for row in data.rows)
    if payment_counts:
        method, count = payment_counts.most_common(1)[0]
        top_payment_method = TopPaymentMethod(method=method, count=count)
    else:
        top_payment_method = None

    return ParkingMetrics(
        total_transactions=total_transactions,
        total_receivable=total_receivable,
        total_collected=total_collected,
        total_actual_deductions=total_actual_deductions,
        collection_rate_pct=collection_rate_pct,
        top_payment_method=top_payment_method,
    )
