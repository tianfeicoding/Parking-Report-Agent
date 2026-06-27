"""报告规划 Agent。

本文件提供 ReportPlannerAgent 的统一入口。v1 支持 mock planner 和 OpenAI
Agents SDK planner；真实 LLM planner 通过 OPENAI_API_KEY 与 OPENAI_BASE_URL
配置，后者可填写第三方 OpenAI-compatible 中转站 URL。
"""

import json
from dataclasses import asdict
from typing import Any

from sqlalchemy.orm import Session

from app.agent.llm_logging import run_with_llm_logging
from app.agent.prompts import build_report_planner_prompt
from app.agent.report_plan_schema import ChartPlan, Observation, Recommendation, ReportPlan
from app.agent.report_plan_validator import validate_report_plan
from app.config.settings import get_settings
from app.metrics.parking_metrics import ParkingMetrics
from app.observability.events import log_event
from app.profiling.anomaly_detector import AnomalyCandidate
from app.profiling.domain_context_loader import DomainContextPack
from app.profiling.duration_profiler import DurationProfile
from app.profiling.payment_profiler import PaymentProfile
from app.report.template_instructions import TemplateInstructions


def build_available_fact_ids(anomaly_candidates: list[AnomalyCandidate]) -> set[str]:
    """生成 Agent 可引用的 fact id 白名单。"""
    fact_ids = {
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
    }
    for candidate in anomaly_candidates:
        fact_ids.update(candidate.source_fact_ids)
    return fact_ids


def build_available_context_ids(domain_context: DomainContextPack) -> set[str]:
    """生成 Agent 可引用的 context id 白名单。"""
    ids = {f"domain.business_priorities.{index}" for index, _ in enumerate(domain_context.business_priorities)}
    ids.update(f"domain.known_policies.{index}" for index, _ in enumerate(domain_context.known_policies))
    ids.update(f"domain.report_preferences.{index}" for index, _ in enumerate(domain_context.report_preferences))
    ids.update(f"domain.risk_rules.{index}" for index, _ in enumerate(domain_context.risk_rules))
    return ids


def build_planner_payload(
    metrics: ParkingMetrics,
    payment_profile: PaymentProfile,
    duration_profile: DurationProfile,
    domain_context: DomainContextPack,
    template_instructions: TemplateInstructions,
    anomaly_candidates: list[AnomalyCandidate],
) -> dict[str, Any]:
    """把确定性 facts 打包成 Agent prompt 的输入 JSON。"""
    return {
        "requirements": {
            "observations": "2-3 items",
            "recommendations": "2-4 items",
            "charts": "at least 1 chart",
            "audience": "停车业务管理者",
        },
        "available_fact_ids": sorted(build_available_fact_ids(anomaly_candidates)),
        "available_context_ids": sorted(build_available_context_ids(domain_context)),
        "metrics": _metrics_to_dict(metrics),
        "payment_profile": asdict(payment_profile),
        "duration_profile": asdict(duration_profile),
        "domain_context": asdict(domain_context),
        "template_instructions": asdict(template_instructions),
        "anomaly_candidates": [asdict(candidate) for candidate in anomaly_candidates],
    }


def create_report_plan(
    *,
    db: Session,
    job_id: str,
    metrics: ParkingMetrics,
    payment_profile: PaymentProfile,
    duration_profile: DurationProfile,
    domain_context: DomainContextPack,
    template_instructions: TemplateInstructions,
    anomaly_candidates: list[AnomalyCandidate],
) -> ReportPlan:
    """根据配置选择 OpenAI 或 mock planner，并返回已校验的 ReportPlan。"""
    settings = get_settings()
    payload = build_planner_payload(
        metrics,
        payment_profile,
        duration_profile,
        domain_context,
        template_instructions,
        anomaly_candidates,
    )
    fact_ids = build_available_fact_ids(anomaly_candidates)
    context_ids = build_available_context_ids(domain_context)

    use_openai = settings.llm_mode == "openai" or (
        settings.llm_mode == "auto" and bool(settings.openai_api_key)
    )

    try:
        if use_openai:
            plan = _create_openai_report_plan(db, job_id, payload)
        else:
            plan = create_mock_report_plan(payload)
    except Exception as exc:
        log_event("report_planner_fallback_used", job_id, db, reason=str(exc))
        plan = create_mock_report_plan(payload, fallback_used=True)

    validation = validate_report_plan(plan, fact_ids, context_ids)
    if validation.valid:
        log_event(
            "report_plan_created",
            job_id,
            db,
            planner_mode=plan.planner_mode,
            fallback_used=plan.fallback_used,
            selected_chart_ids=[chart.chart_id for chart in plan.selected_charts],
            selected_observation_ids=[observation.id for observation in plan.observations],
        )
        return plan

    log_event("agent_output_validation_failed", job_id, db, errors=validation.errors)
    if use_openai:
        try:
            repaired = _repair_openai_report_plan(db, job_id, payload, validation.errors)
            repaired_validation = validate_report_plan(repaired, fact_ids, context_ids)
            if repaired_validation.valid:
                return repaired
        except Exception as exc:
            log_event("agent_output_repair_failed", job_id, db, error=str(exc))

    fallback_plan = create_mock_report_plan(payload, fallback_used=True)
    fallback_validation = validate_report_plan(fallback_plan, fact_ids, context_ids)
    if not fallback_validation.valid:
        raise ValueError(f"Fallback ReportPlan is invalid: {fallback_validation.errors}")
    return fallback_plan


def create_mock_report_plan(payload: dict[str, Any], fallback_used: bool = False) -> ReportPlan:
    """生成 deterministic mock ReportPlan，供无 key、本地测试和 fallback 使用。"""
    anomaly_ids = {candidate["id"] for candidate in payload["anomaly_candidates"]}

    observations = [
        Observation(
            id="discount_exposure_high",
            title="抵扣和优惠敞口较高",
            text="实际抵扣总额占应收金额比例较高，说明优惠、积分或抵扣类交易对实收金额影响明显。",
            business_implication="建议关注优惠核销规则、会员权益成本和相关审批口径。",
            source_fact_ids=["metrics.total_actual_deductions", "metrics.total_receivable"],
        ),
        Observation(
            id="long_stay_outlier",
            title="存在长时停车记录",
            text="数据中存在超过 12 小时的长时停车记录，最长停车时长明显高于常规短停场景。",
            business_implication="建议抽样复核长时停车车辆，区分真实长停和入出场记录异常。",
            source_fact_ids=["duration.over_12h_count", "duration.max_hours"],
        ),
    ]

    if "zero_collected_review" in anomaly_ids:
        observations.append(
            Observation(
                id="zero_collected_review",
                title="零实收交易需要复核",
                text="存在应收金额大于 0 但实收金额为 0 的记录，需要结合优惠、积分或人工放行规则判断。",
                business_implication="建议建立零实收交易抽样复核，避免正常核销和异常收入损失混在一起。",
                source_fact_ids=["anomalies.zero_collected_with_receivable"],
            )
        )

    recommendations = [
        Recommendation(
            id="review_discount_policy",
            text="按会员积分、优惠券和其他抵扣来源拆分复核，确认优惠核销规则和成本承担方式。",
            source_fact_ids=["metrics.total_actual_deductions", "metrics.total_receivable"],
            source_observation_ids=["discount_exposure_high"],
        ),
        Recommendation(
            id="review_long_stay_records",
            text="对超过 12 小时的长时停车记录做抽样检查，确认是否为真实长停或入出场记录异常。",
            source_fact_ids=["duration.over_12h_count", "duration.max_hours"],
            source_observation_ids=["long_stay_outlier"],
        ),
    ]

    if "zero_collected_review" in anomaly_ids:
        recommendations.append(
            Recommendation(
                id="audit_zero_collected",
                text="建立应收大于 0 且实收为 0 的交易清单，结合优惠核销规则定期复核。",
                source_fact_ids=["anomalies.zero_collected_with_receivable"],
                source_observation_ids=["zero_collected_review"],
            )
        )

    return ReportPlan(
        selected_charts=[
            ChartPlan(
                chart_id="payment_method_distribution",
                title="支付方式分布",
                reason="支付方式结构直接支持收入和优惠敞口分析。",
                source_fact_ids=["payment_profile.dominant_payment_method"],
            ),
            ChartPlan(
                chart_id="parking_duration_distribution",
                title="停车时长分布",
                reason="停车时长分布可支撑长时停车和车位周转分析。",
                source_fact_ids=["duration.over_12h_count", "duration.max_hours"],
            ),
        ],
        payment_section_summary="本周期支付方式以主要线上方式和权益/优惠类方式为核心，需结合实收率和抵扣情况观察收入结构。",
        duration_section_summary="停车时长以短时停车为主，但存在超过 12 小时的长时停车记录，建议后续复核。",
        observations=observations[:3],
        recommendations=recommendations[:4],
        fallback_used=fallback_used,
        planner_mode="mock" if not fallback_used else "fallback",
    )


def _create_openai_report_plan(db: Session, job_id: str, payload: dict[str, Any]) -> ReportPlan:
    """调用 OpenAI Agents SDK 生成 ReportPlan；OPENAI_BASE_URL 支持第三方中转。"""
    settings = get_settings()
    prompt = build_report_planner_prompt(payload)

    def call_model():
        return _run_agents_sdk_report_planner(settings, prompt)

    plan = run_with_llm_logging(
        db=db,
        job_id=job_id,
        agent_name="ReportPlannerAgent",
        model=settings.openai_model,
        prompt=prompt,
        call=call_model,
        response_to_text=_report_plan_to_log_text,
    )
    return plan.model_copy(update={"planner_mode": "openai", "fallback_used": False})


def _repair_openai_report_plan(
    db: Session,
    job_id: str,
    payload: dict[str, Any],
    errors: list[str],
) -> ReportPlan:
    """当 Agent 输出校验失败时，追加错误信息让模型修复一次。"""
    repair_payload = {**payload, "validation_errors_to_fix": errors}
    settings = get_settings()
    prompt = build_report_planner_prompt(repair_payload)

    def call_model():
        return _run_agents_sdk_report_planner(settings, prompt)

    plan = run_with_llm_logging(
        db=db,
        job_id=job_id,
        agent_name="ReportPlannerAgentRepair",
        model=settings.openai_model,
        prompt=prompt,
        call=call_model,
        response_to_text=_report_plan_to_log_text,
    )
    return plan.model_copy(update={"planner_mode": "openai", "fallback_used": False})


def _run_agents_sdk_report_planner(settings: Any, prompt: str) -> ReportPlan:
    """配置 OpenAI Agents SDK 并执行一次结构化 ReportPlannerAgent。"""
    from agents import Agent, ModelSettings, Runner, set_default_openai_api, set_default_openai_client
    from agents import set_tracing_disabled
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    set_default_openai_client(client, use_for_tracing=False)
    set_default_openai_api(settings.openai_agent_api)
    set_tracing_disabled(True)

    agent = Agent(
        name="ReportPlannerAgent",
        instructions=(
            "你是停车数据报告规划 Agent。你只能基于输入里的 facts/context 做判断，"
            "不能重新计算或改写硬指标。输出必须符合 ReportPlan schema。"
        ),
        model=settings.openai_model,
        model_settings=ModelSettings(temperature=0.2),
        output_type=ReportPlan,
    )
    result = Runner.run_sync(agent, prompt)
    final_output = result.final_output
    if isinstance(final_output, ReportPlan):
        return final_output
    if isinstance(final_output, str):
        return _parse_report_plan_json(final_output, planner_mode="openai")
    return ReportPlan.model_validate(final_output)


def _report_plan_to_log_text(plan: ReportPlan) -> str:
    """把结构化 ReportPlan 转成可写入 LLM 日志的 JSON 文本。"""
    return plan.model_dump_json(ensure_ascii=False)


def _parse_report_plan_json(text: str, planner_mode: str) -> ReportPlan:
    """从模型返回文本中解析 ReportPlan JSON。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    data = json.loads(stripped)
    data["planner_mode"] = planner_mode
    return ReportPlan.model_validate(data)


def _metrics_to_dict(metrics: ParkingMetrics) -> dict[str, Any]:
    """把 ParkingMetrics 转成 prompt 可序列化字典。"""
    return {
        "total_transactions": metrics.total_transactions,
        "total_receivable": str(metrics.total_receivable),
        "total_collected": str(metrics.total_collected),
        "total_actual_deductions": str(metrics.total_actual_deductions),
        "collection_rate_pct": str(metrics.collection_rate_pct),
        "top_payment_method": asdict(metrics.top_payment_method) if metrics.top_payment_method else None,
    }
