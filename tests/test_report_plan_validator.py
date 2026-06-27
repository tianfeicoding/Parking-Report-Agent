"""ReportPlan validator 和 mock planner 测试。

本文件验证 Agent 输出必须有合法 source_fact_ids、数量约束和至少一张图表。
"""

from decimal import Decimal

from app.agent.report_plan_schema import ChartPlan, Observation, Recommendation, ReportPlan
from app.agent.report_plan_validator import validate_report_plan
from app.agent.report_planner import create_mock_report_plan


AVAILABLE_FACT_IDS = {
    "metrics.total_transactions",
    "metrics.total_receivable",
    "metrics.total_collected",
    "metrics.total_actual_deductions",
    "metrics.collection_rate_pct",
    "metrics.top_payment_method",
    "payment_profile.dominant_payment_method",
    "payment_profile.dominant_payment_channel",
    "duration.average_hours",
    "duration.median_hours",
    "duration.max_hours",
    "duration.over_12h_count",
    "anomalies.zero_collected_with_receivable",
}


def valid_plan() -> ReportPlan:
    return ReportPlan(
        selected_charts=[
            ChartPlan(
                chart_id="payment_method_distribution",
                title="支付方式分布",
                reason="支撑支付结构分析",
                source_fact_ids=["payment_profile.dominant_payment_method"],
            )
        ],
        payment_section_summary="支付结构摘要",
        duration_section_summary="停车时长摘要",
        observations=[
            Observation(
                id="obs_1",
                title="观察 1",
                text="观察内容",
                business_implication="经营含义",
                source_fact_ids=["metrics.total_receivable"],
            ),
            Observation(
                id="obs_2",
                title="观察 2",
                text="观察内容",
                business_implication="经营含义",
                source_fact_ids=["duration.over_12h_count"],
            ),
        ],
        recommendations=[
            Recommendation(
                id="rec_1",
                text="建议 1",
                source_fact_ids=["metrics.total_receivable"],
                source_observation_ids=["obs_1"],
            ),
            Recommendation(
                id="rec_2",
                text="建议 2",
                source_fact_ids=["duration.over_12h_count"],
                source_observation_ids=["obs_2"],
            ),
        ],
    )


def test_validate_report_plan_accepts_valid_plan():
    result = validate_report_plan(valid_plan(), AVAILABLE_FACT_IDS)

    assert result.valid
    assert result.errors == []


def test_validate_report_plan_rejects_unknown_fact_id():
    plan = valid_plan()
    plan.observations[0].source_fact_ids = ["missing.fact"]

    result = validate_report_plan(plan, AVAILABLE_FACT_IDS)

    assert not result.valid
    assert "missing.fact" in result.errors[0]


def test_validate_report_plan_rejects_wrong_observation_count():
    plan = valid_plan()
    plan.observations = plan.observations[:1]

    result = validate_report_plan(plan, AVAILABLE_FACT_IDS)

    assert not result.valid
    assert any("2-3 observations" in error for error in result.errors)


def test_mock_report_plan_is_valid():
    payload = {
        "anomaly_candidates": [
            {"id": "zero_collected_review"},
            {"id": "discount_exposure_high"},
            {"id": "long_stay_outlier"},
        ]
    }

    plan = create_mock_report_plan(payload)
    result = validate_report_plan(plan, AVAILABLE_FACT_IDS)

    assert result.valid
    assert plan.planner_mode == "mock"
    assert len(plan.observations) == 3
    assert len(plan.recommendations) == 3
