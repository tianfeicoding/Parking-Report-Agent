"""停车硬指标测试。

本文件验证六个评分用硬指标完全由确定性代码计算。
"""

from decimal import Decimal

from app.data.parking_csv_loader import load_parking_csv
from app.metrics.parking_metrics import compute_parking_metrics

CSV_HEADER = (
    "应收金额,实收金额(元),免费金额(元),充值卡扣费(元),抵扣金额(元),"
    "抵扣时长(小时),实际抵扣额(元),支付方式,支付渠道,收费时间,进车时间\n"
)


def test_compute_parking_metrics(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text(
        CSV_HEADER
        + "30,30,0,0.00,0,0,0,微信,线上支付,2026-04-30 10:00:00,2026-04-30 08:00:00\n"
        + "45,0,0,0.00,45,0,45,会员积分,线上支付,2026-04-30 11:00:00,2026-04-30 09:00:00\n"
        + "25,20,0,0.00,5,1,5,微信,出口贴码,2026-04-30 12:00:00,2026-04-30 10:00:00\n",
        encoding="utf-8-sig",
    )

    metrics = compute_parking_metrics(load_parking_csv(path))

    assert metrics.total_transactions == 3
    assert metrics.total_receivable == Decimal("100")
    assert metrics.total_collected == Decimal("50")
    assert metrics.total_actual_deductions == Decimal("50")
    assert metrics.collection_rate_pct == Decimal("50.0")
    assert metrics.top_payment_method is not None
    assert metrics.top_payment_method.method == "微信"
    assert metrics.top_payment_method.count == 2


def test_compute_parking_metrics_handles_zero_receivable(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text(
        CSV_HEADER
        + "0,0,0,0.00,0,0,0,微信,线上支付,2026-04-30 10:00:00,2026-04-30 08:00:00\n",
        encoding="utf-8-sig",
    )

    metrics = compute_parking_metrics(load_parking_csv(path))

    assert metrics.collection_rate_pct == Decimal("0.0")
