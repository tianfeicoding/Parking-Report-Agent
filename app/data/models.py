"""停车交易清洗后数据模型。

本文件定义 CSV 经过格式清洗和类型转换后的内部结构，
后续指标计算和 profile 分析都只依赖这些确定性模型。
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class ParkingRow:
    receivable: Decimal
    collected: Decimal
    free_amount: Decimal
    stored_card_deduction: Decimal
    deduction_amount: Decimal
    deduction_hours: Decimal
    actual_deduction: Decimal
    payment_method: str
    payment_channel: str
    charged_at: datetime
    entered_at: datetime


@dataclass(frozen=True)
class CleanedParkingData:
    rows: list[ParkingRow]
    source_path: str
