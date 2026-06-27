"""ReportPlannerAgent prompt 构造。

本文件把确定性 facts、模板说明和领域上下文压缩成 LLM 可读的输入，
并明确要求 LLM 返回符合 ReportPlan schema 的 JSON。
"""

import json
from typing import Any


SYSTEM_PROMPT = """你是停车场经营分析报告规划智能体。

规则：
1. 不要重新计算硬指标，不要修改输入 facts 中的数值。
2. 只能引用提供的 source_fact_ids 和 source_context_ids。
3. 补充观察必须 2-3 条，建议必须 2-4 条。
4. 至少选择一张图表。
5. 输出必须是合法 JSON，不要输出 Markdown。
6. 对风险使用谨慎措辞，例如“建议复核”，不要无依据判定违规。
"""


def build_report_planner_prompt(payload: dict[str, Any]) -> str:
    """构造报告规划 prompt，要求模型返回 ReportPlan JSON。"""
    return (
        SYSTEM_PROMPT
        + "\n\n请基于以下 JSON 输入生成 ReportPlan JSON：\n"
        + json.dumps(payload, ensure_ascii=False, default=str, indent=2)
    )
