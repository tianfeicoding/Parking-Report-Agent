"""候选关注点检测测试。

本文件验证 anomaly detector 只生成结构化候选事实，不生成最终报告结论。
"""

from app.data.parking_csv_loader import load_parking_csv
from app.metrics.parking_metrics import compute_parking_metrics
from app.profiling.anomaly_detector import detect_anomaly_candidates
from app.profiling.duration_profiler import build_duration_profile
from app.profiling.payment_profiler import build_payment_profile

CSV_HEADER = (
    "应收金额,实收金额(元),免费金额(元),充值卡扣费(元),抵扣金额(元),"
    "抵扣时长(小时),实际抵扣额(元),支付方式,支付渠道,收费时间,进车时间\n"
)


def test_detect_anomaly_candidates(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text(
        CSV_HEADER
        + "100,0,0,0.00,100,0,100,会员积分,线上支付,2026-04-30 23:00:00,2026-04-30 08:00:00\n"
        + "100,0,0,0.00,100,0,100,优惠券,线上支付,2026-04-30 12:00:00,2026-04-30 10:00:00\n"
        + "100,100,0,0.00,0,0,0,微信,线上支付,2026-04-30 11:00:00,2026-04-30 09:00:00\n",
        encoding="utf-8-sig",
    )
    data = load_parking_csv(path)
    metrics = compute_parking_metrics(data)
    payment_profile = build_payment_profile(data)
    duration_profile = build_duration_profile(data)

    candidates = detect_anomaly_candidates(data, metrics, payment_profile, duration_profile)
    candidate_ids = {candidate.id for candidate in candidates}

    assert "zero_collected_review" in candidate_ids
    assert "discount_exposure_high" in candidate_ids
    assert "long_stay_outlier" in candidate_ids
    assert "payment_channel_concentration" in candidate_ids
    for candidate in candidates:
        assert candidate.source_fact_ids
        assert candidate.evidence
