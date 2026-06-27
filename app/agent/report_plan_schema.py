"""Agent 报告计划 schema。

本文件定义 ReportPlannerAgent 的结构化输出。后续 DOCX 渲染器只消费
这个可校验的 ReportPlan，而不直接消费 LLM 自由文本。
"""

from pydantic import BaseModel, Field


class ChartPlan(BaseModel):
    chart_id: str
    title: str
    reason: str
    source_fact_ids: list[str] = Field(default_factory=list)


class Observation(BaseModel):
    id: str
    title: str
    text: str
    business_implication: str
    source_fact_ids: list[str] = Field(default_factory=list)
    source_context_ids: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    id: str
    text: str
    source_fact_ids: list[str] = Field(default_factory=list)
    source_observation_ids: list[str] = Field(default_factory=list)


class ReportPlan(BaseModel):
    selected_charts: list[ChartPlan]
    payment_section_summary: str
    duration_section_summary: str
    observations: list[Observation]
    recommendations: list[Recommendation]
    fallback_used: bool = False
    planner_mode: str = "openai"
