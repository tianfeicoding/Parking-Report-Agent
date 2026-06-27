"""停车 CSV loader 测试。

本文件验证上传数据清洗阶段能正确处理 BOM、必需列、金额和时间字段。
"""

from decimal import Decimal

import pytest

from app.data.parking_csv_loader import DataValidationError, load_parking_csv

CSV_HEADER = (
    "应收金额,实收金额(元),免费金额(元),充值卡扣费(元),抵扣金额(元),"
    "抵扣时长(小时),实际抵扣额(元),支付方式,支付渠道,收费时间,进车时间\n"
)


def write_csv(tmp_path, content: str):
    path = tmp_path / "data.csv"
    path.write_text(content, encoding="utf-8-sig")
    return path


def test_load_parking_csv_parses_rows_with_bom(tmp_path):
    path = write_csv(
        tmp_path,
        CSV_HEADER
        + "30,25,0,0.00,5,1,5,微信,线上支付,2026-04-30 10:00:00,2026-04-30 08:00:00\n",
    )

    data = load_parking_csv(path)

    assert len(data.rows) == 1
    row = data.rows[0]
    assert row.receivable == Decimal("30")
    assert row.collected == Decimal("25")
    assert row.actual_deduction == Decimal("5")
    assert row.payment_method == "微信"
    assert row.charged_at.year == 2026


def test_load_parking_csv_rejects_missing_required_columns(tmp_path):
    path = write_csv(tmp_path, "应收金额,实收金额(元)\n30,30\n")

    with pytest.raises(DataValidationError, match="missing required columns"):
        load_parking_csv(path)


def test_load_parking_csv_rejects_invalid_decimal(tmp_path):
    path = write_csv(
        tmp_path,
        CSV_HEADER
        + "not-a-number,25,0,0.00,5,1,5,微信,线上支付,2026-04-30 10:00:00,2026-04-30 08:00:00\n",
    )

    with pytest.raises(DataValidationError, match="not a valid number"):
        load_parking_csv(path)


def test_load_parking_csv_rejects_invalid_datetime(tmp_path):
    path = write_csv(
        tmp_path,
        CSV_HEADER + "30,25,0,0.00,5,1,5,微信,线上支付,bad-time,2026-04-30 08:00:00\n",
    )

    with pytest.raises(DataValidationError, match="must match"):
        load_parking_csv(path)
