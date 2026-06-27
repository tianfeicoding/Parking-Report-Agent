"""停车 CSV 清洗和校验。

本文件负责读取用户上传的停车交易 CSV，校验必需列，
并把金额、时间等字段转换成后续计算可安全使用的类型。
"""

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.data.models import CleanedParkingData, ParkingRow

REQUIRED_COLUMNS = {
    "应收金额",
    "实收金额(元)",
    "免费金额(元)",
    "充值卡扣费(元)",
    "抵扣金额(元)",
    "抵扣时长(小时)",
    "实际抵扣额(元)",
    "支付方式",
    "支付渠道",
    "收费时间",
    "进车时间",
}

MONEY_COLUMNS = {
    "应收金额",
    "实收金额(元)",
    "免费金额(元)",
    "充值卡扣费(元)",
    "抵扣金额(元)",
    "抵扣时长(小时)",
    "实际抵扣额(元)",
}

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class DataValidationError(ValueError):
    pass


def _parse_decimal(value: str | None, column: str, row_number: int) -> Decimal:
    """将金额/数值字段解析为 Decimal，保证硬指标计算不受 float 精度影响。"""
    text = (value or "").strip()
    if text == "":
        text = "0"

    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise DataValidationError(f"Row {row_number}: column {column} is not a valid number") from exc


def _parse_datetime(value: str | None, column: str, row_number: int) -> datetime:
    """按停车系统导出的固定格式解析时间字段。"""
    text = (value or "").strip()
    if not text:
        raise DataValidationError(f"Row {row_number}: column {column} is required")

    try:
        return datetime.strptime(text, DATETIME_FORMAT)
    except ValueError as exc:
        raise DataValidationError(
            f"Row {row_number}: column {column} must match {DATETIME_FORMAT}"
        ) from exc


def _normalize_row(raw_row: dict[str, str], row_number: int) -> ParkingRow:
    """把一行原始 CSV 字符串转换为强类型 ParkingRow。"""
    return ParkingRow(
        receivable=_parse_decimal(raw_row.get("应收金额"), "应收金额", row_number),
        collected=_parse_decimal(raw_row.get("实收金额(元)"), "实收金额(元)", row_number),
        free_amount=_parse_decimal(raw_row.get("免费金额(元)"), "免费金额(元)", row_number),
        stored_card_deduction=_parse_decimal(raw_row.get("充值卡扣费(元)"), "充值卡扣费(元)", row_number),
        deduction_amount=_parse_decimal(raw_row.get("抵扣金额(元)"), "抵扣金额(元)", row_number),
        deduction_hours=_parse_decimal(raw_row.get("抵扣时长(小时)"), "抵扣时长(小时)", row_number),
        actual_deduction=_parse_decimal(raw_row.get("实际抵扣额(元)"), "实际抵扣额(元)", row_number),
        payment_method=(raw_row.get("支付方式") or "").strip(),
        payment_channel=(raw_row.get("支付渠道") or "").strip(),
        charged_at=_parse_datetime(raw_row.get("收费时间"), "收费时间", row_number),
        entered_at=_parse_datetime(raw_row.get("进车时间"), "进车时间", row_number),
    )


def load_parking_csv(path: str | Path) -> CleanedParkingData:
    """读取并清洗停车 CSV；缺列或字段非法时抛出 DataValidationError。"""
    csv_path = Path(path)
    rows: list[ParkingRow] = []

    with csv_path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise DataValidationError("CSV has no header row")

        normalized_headers = [header.strip() for header in reader.fieldnames]
        missing_columns = REQUIRED_COLUMNS - set(normalized_headers)
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise DataValidationError(f"CSV is missing required columns: {missing}")

        reader.fieldnames = normalized_headers
        for row_number, raw_row in enumerate(reader, start=2):
            normalized_row = {key.strip(): value for key, value in raw_row.items() if key is not None}
            rows.append(_normalize_row(normalized_row, row_number))

    return CleanedParkingData(rows=rows, source_path=str(csv_path))
