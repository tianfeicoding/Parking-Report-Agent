"""停车时长与时间分布 profile。

本文件根据进车时间和收费时间计算停车时长、时长分布、
入场小时分布和收费小时分布。
"""

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from statistics import median

from app.data.models import CleanedParkingData


@dataclass(frozen=True)
class HourBucket:
    hour: int
    count: int


@dataclass(frozen=True)
class DurationBucket:
    label: str
    count: int


@dataclass(frozen=True)
class DurationProfile:
    average_hours: Decimal
    median_hours: Decimal
    max_hours: Decimal
    duration_buckets_2h: list[DurationBucket]
    entry_hour_distribution: list[HourBucket]
    charge_hour_distribution: list[HourBucket]
    over_12h_count: int
    negative_duration_count: int


def _to_decimal_hours(seconds: float) -> Decimal:
    """把秒数转换为小时 Decimal，统一保留 2 位小数。"""
    return (Decimal(str(seconds)) / Decimal("3600")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _build_duration_buckets(duration_hours: list[Decimal]) -> list[DurationBucket]:
    """按 2 小时区间生成停车时长分布。"""
    labels = ["0-2", "2-4", "4-6", "6-8", "8-10", "10-12", "12+"]
    counts = Counter({label: 0 for label in labels})
    counts["negative"] = 0

    for hours in duration_hours:
        if hours < 0:
            counts["negative"] += 1
        elif hours >= Decimal("12"):
            counts["12+"] += 1
        else:
            lower = int(hours // Decimal("2")) * 2
            counts[f"{lower}-{lower + 2}"] += 1

    ordered_labels = labels + (["negative"] if counts["negative"] else [])
    return [DurationBucket(label=label, count=counts[label]) for label in ordered_labels]


def _build_hour_distribution(hours: list[int]) -> list[HourBucket]:
    """按小时聚合入场或收费记录数量。"""
    counts = Counter(hours)
    return [HourBucket(hour=hour, count=counts.get(hour, 0)) for hour in range(24)]


def build_duration_profile(data: CleanedParkingData) -> DurationProfile:
    """生成停车时长、入场小时和收费小时 profile。"""
    duration_hours = [
        _to_decimal_hours((row.charged_at - row.entered_at).total_seconds())
        for row in data.rows
    ]

    non_empty = duration_hours or [Decimal("0.00")]
    average_hours = (sum(non_empty, Decimal("0.00")) / Decimal(len(non_empty))).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    median_hours = Decimal(str(median(non_empty))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    max_hours = max(non_empty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return DurationProfile(
        average_hours=average_hours,
        median_hours=median_hours,
        max_hours=max_hours,
        duration_buckets_2h=_build_duration_buckets(duration_hours),
        entry_hour_distribution=_build_hour_distribution([row.entered_at.hour for row in data.rows]),
        charge_hour_distribution=_build_hour_distribution([row.charged_at.hour for row in data.rows]),
        over_12h_count=sum(1 for hours in duration_hours if hours >= Decimal("12")),
        negative_duration_count=sum(1 for hours in duration_hours if hours < 0),
    )
