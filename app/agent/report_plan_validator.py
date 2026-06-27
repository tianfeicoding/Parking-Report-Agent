"""ReportPlan 校验器。

本文件负责检查 Agent 输出是否满足 grounding 要求，
包括图表数量、观察/建议数量、source_fact_ids 合法性等。
"""

from dataclasses import dataclass

from app.agent.report_plan_schema import ReportPlan


@dataclass(frozen=True)
class ReportPlanValidationResult:
    valid: bool
    errors: list[str]


def validate_report_plan(
    plan: ReportPlan,
    available_fact_ids: set[str],
    available_context_ids: set[str] | None = None,
) -> ReportPlanValidationResult:
    """校验 ReportPlan 是否可安全进入渲染阶段。"""
    available_context_ids = available_context_ids or set()
    errors: list[str] = []

    if not plan.selected_charts:
        errors.append("ReportPlan must select at least one chart")

    if not 2 <= len(plan.observations) <= 3:
        errors.append("ReportPlan must include 2-3 observations")

    if not 2 <= len(plan.recommendations) <= 4:
        errors.append("ReportPlan must include 2-4 recommendations")

    for chart in plan.selected_charts:
        _validate_fact_ids(f"chart:{chart.chart_id}", chart.source_fact_ids, available_fact_ids, errors)

    observation_ids = {observation.id for observation in plan.observations}
    for observation in plan.observations:
        _validate_fact_ids(
            f"observation:{observation.id}",
            observation.source_fact_ids,
            available_fact_ids,
            errors,
        )
        for context_id in observation.source_context_ids:
            if context_id not in available_context_ids:
                errors.append(f"observation:{observation.id} references unknown context id {context_id}")

    for recommendation in plan.recommendations:
        _validate_fact_ids(
            f"recommendation:{recommendation.id}",
            recommendation.source_fact_ids,
            available_fact_ids,
            errors,
        )
        for observation_id in recommendation.source_observation_ids:
            if observation_id not in observation_ids:
                errors.append(
                    f"recommendation:{recommendation.id} references unknown observation id {observation_id}"
                )

    return ReportPlanValidationResult(valid=not errors, errors=errors)


def _validate_fact_ids(
    owner: str,
    source_fact_ids: list[str],
    available_fact_ids: set[str],
    errors: list[str],
) -> None:
    """校验某个输出节点引用的 fact id 是否存在。"""
    if not source_fact_ids:
        errors.append(f"{owner} must include at least one source_fact_id")
        return

    for fact_id in source_fact_ids:
        if fact_id not in available_fact_ids:
            errors.append(f"{owner} references unknown fact id {fact_id}")
