"""候选经营关注点检测。

本文件基于确定性 facts 生成结构化候选洞察。它只负责提出候选，
不决定最终报告写哪些内容。
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.data.models import CleanedParkingData
from app.metrics.parking_metrics import ParkingMetrics
from app.profiling.duration_profiler import DurationProfile
from app.profiling.payment_profiler import PaymentProfile


@dataclass(frozen=True)
class AnomalyCandidate:
    id: str
    topic: str
    severity: str
    title: str
    description: str
    evidence: dict[str, str | int]
    source_fact_ids: list[str]


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    """计算百分比，统一保留 1 位小数。"""
    if denominator == 0:
        return Decimal("0.0")
    return (numerator / denominator * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def detect_anomaly_candidates(
    data: CleanedParkingData,
    metrics: ParkingMetrics,
    payment_profile: PaymentProfile,
    duration_profile: DurationProfile,
) -> list[AnomalyCandidate]:
    """生成零实收、抵扣敞口、长时停车和渠道集中等候选关注点。"""
    candidates: list[AnomalyCandidate] = []

    zero_collected_with_receivable = sum(
        1 for row in data.rows if row.receivable > 0 and row.collected == 0
    )
    if zero_collected_with_receivable:
        candidates.append(
            AnomalyCandidate(
                id="zero_collected_review",
                topic="revenue_collection",
                severity="high" if zero_collected_with_receivable >= 100 else "medium",
                title="存在应收大于 0 但实收为 0 的交易",
                description="这类记录需要结合优惠、积分或人工放行规则复核，避免误判或遗漏收入风险。",
                evidence={"count": zero_collected_with_receivable},
                source_fact_ids=["anomalies.zero_collected_with_receivable"],
            )
        )

    deduction_ratio = _ratio(metrics.total_actual_deductions, metrics.total_receivable)
    if deduction_ratio >= Decimal("20.0"):
        candidates.append(
            AnomalyCandidate(
                id="discount_exposure_high",
                topic="discount_and_deduction_exposure",
                severity="high" if deduction_ratio >= Decimal("40.0") else "medium",
                title="实际抵扣额占比较高",
                description="抵扣、优惠或会员权益对实收金额影响明显，建议关注核销规则和权益成本。",
                evidence={
                    "actual_deductions": str(metrics.total_actual_deductions),
                    "receivable": str(metrics.total_receivable),
                    "deduction_ratio_pct": str(deduction_ratio),
                },
                source_fact_ids=[
                    "metrics.total_actual_deductions",
                    "metrics.total_receivable",
                ],
            )
        )

    if duration_profile.over_12h_count:
        candidates.append(
            AnomalyCandidate(
                id="long_stay_outlier",
                topic="parking_duration",
                severity="medium",
                title="存在超过 12 小时的长时停车记录",
                description="长时停车可能影响车位周转，也可能提示入出场记录或计费规则需要复核。",
                evidence={
                    "over_12h_count": duration_profile.over_12h_count,
                    "max_hours": str(duration_profile.max_hours),
                },
                source_fact_ids=["duration.over_12h_count", "duration.max_hours"],
            )
        )

    dominant_channel = payment_profile.dominant_payment_channel
    if dominant_channel and dominant_channel.count_pct >= Decimal("80.0"):
        candidates.append(
            AnomalyCandidate(
                id="payment_channel_concentration",
                topic="payment_channel_mix",
                severity="low",
                title="支付渠道集中度较高",
                description="渠道集中说明主通道稳定，但也应关注备用通道、现场设备和异常场景承接能力。",
                evidence={
                    "channel": dominant_channel.name,
                    "count": dominant_channel.count,
                    "count_pct": str(dominant_channel.count_pct),
                },
                source_fact_ids=["payment_profile.dominant_payment_channel"],
            )
        )

    return candidates
