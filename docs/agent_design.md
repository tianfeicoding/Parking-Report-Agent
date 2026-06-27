# Agent Design: 停车报告规划智能体

## 1. 设计目标

本项目的 Agent 设计目标不是让 LLM 自由生成整份报告，而是让 LLM 在确定性事实基础上做报告规划。

核心原则：

- 确定性代码负责计算事实
- Agent 负责判断哪些事实值得进入报告
- Agent 输出结构化 `ReportPlan`
- 所有观察和建议必须能追溯到已有 facts
- Word 报告和图表由 deterministic renderer 生成
- Word 版式应由用户上传模板决定，Agent 只决定填入哪些内容

一句话概括：

```text
Agent does not compute facts. Agent decides what facts matter for the report.
```

## 2. Agents

### 2.1 总体设计

v1 使用单个智能体：

```text
ReportPlannerAgent
```

系统不是多智能体架构，而是：

```text
deterministic workflow
  + single report-planning agent
  + deterministic renderers
```

`ReportPlannerAgent` 嵌入在 `ReportGenerationWorkflow` 中。它不直接读取原始 CSV，也不直接生成 Word 文件。

### 2.2 为什么不用多智能体

本任务的核心是生成一份停车明细分析报告，不需要复杂角色协作。

多智能体会增加：

- agent 间协调成本
- 日志和追踪复杂度
- 失败处理复杂度
- 测试复杂度
- 不必要的 LLM 调用次数

v1 使用单 Agent 更符合 take-home 的范围控制，也更容易保证硬指标和报告质量。

未来如果需要支持更复杂模板或审校流程，可以扩展多个 Agent。

### 2.3 ReportPlannerAgent

职责：

- 读取确定性 `ReportFacts`
- 读取模板中的章节和占位说明
- 读取可选领域上下文
- 选择报告中应展示的重点图表
- 选择 2-3 条补充观察
- 生成 2-4 条结论与建议
- 输出结构化 `ReportPlan`

不负责：

- 解析 CSV
- 计算六个硬指标
- 重新计算金额或比例
- 直接绘制图表
- 直接生成 DOCX
- 决定 Word 视觉样式或重建模板版式
- 更新 job 状态

输入：

- `MetricsFacts`
- `PaymentProfile`
- `DurationProfile`
- `AnomalyCandidates`
- `TemplateInstructions`
- `DomainContextPack`
- `ReportRequirements`

输出：

- `ReportPlan`

调用位置：

```text
worker claims job
  -> ReportGenerationWorkflow starts
  -> ParkingCsvLoader cleans data
  -> MetricsComputer computes hard metrics
  -> PaymentProfiler builds payment profile
  -> ParkingDurationProfiler builds duration profile
  -> DomainContextLoader prepares context
  -> TemplateInstructionExtractor extracts template instructions
  -> AnomalyDetector creates candidate insights
  -> ReportPlannerAgent creates ReportPlan
  -> ReportPlanValidator validates output
  -> ChartRenderer renders selected charts
  -> DocxRenderer writes final report
  -> job marked completed
```

## 3. 工具分类

本系统的工具分为三类：

1. Workflow 强制执行工具
2. Agent 决策能力
3. 渲染与校验工具

### 3.1 Workflow 强制执行工具

这些工具不由 Agent 判断是否调用。每个 job 都必须执行。

#### ParkingCsvLoader

作用：

- 读取用户上传的 CSV
- 处理 UTF-8 BOM
- 标准化列名
- 校验必需字段
- 解析金额字段为 Decimal
- 解析时间字段为 datetime
- 输出清洗后的 `CleanedParkingData`

输入：

- `data_file_path`

输出：

- `CleanedParkingData`

失败情况：

- 缺少必需列
- 金额字段无法解析
- 时间字段无法解析
- CSV 编码或格式错误

#### MetricsComputer

作用：

计算六个硬指标：

- 总交易笔数
- 应收总金额
- 实收总金额
- 实际抵扣总额
- 实收率
- 主要支付方式

输入：

- `CleanedParkingData`

输出：

- `MetricsFacts`

说明：

这些值必须由确定性代码计算，不能由 LLM 生成或修改。

#### PaymentProfiler

作用：

分析支付方式和支付渠道结构：

- 支付方式笔数、占比、金额分布
- 支付渠道笔数、占比、金额分布
- 主导支付方式
- 主导支付渠道
- 现金、支付宝、微信、会员积分、优惠券等结构

输入：

- `CleanedParkingData`

输出：

- `PaymentProfile`

#### ParkingDurationProfiler

作用：

分析停车时长和时间分布：

- 根据 `收费时间 - 进车时间` 计算停车时长
- 平均时长、中位数、最大值
- 0-2h、2-4h、4-6h 等时长分布
- 入场小时分布
- 收费小时分布
- 超长停车记录数量

输入：

- `CleanedParkingData`

输出：

- `DurationProfile`

#### TemplateInstructionExtractor

作用：

从 Word 模板中提取报告结构和占位说明：

- 章节标题
- 占位文本
- 图表要求
- 补充观察/建议的写作要求
- 关键指标表格结构信号

输入：

- `template_file_path`

输出：

- `TemplateInstructions`

说明：

模板说明作为 Agent 的输入信号，但硬性要求仍由代码配置保证。
模板样式和占位替换不由 Agent 执行，后续由 deterministic `DocxRenderer` 基于原 `.docx` 完成。

#### DomainContextLoader

作用：

处理可选用户领域知识：

- 读取 `.docx / .txt / .md` 领域资料
- 合并 free-text instruction
- 抽取业务关注点、术语、政策说明、报告偏好
- 生成 `DomainContextPack`

输入：

- `domain_context_files`
- `free_text_instruction`

输出：

- `DomainContextPack`

说明：

如果用户未上传领域知识，则使用内置停车经营分析准则。

#### AnomalyDetector

作用：

生成候选经营关注点，而不是最终结论。

候选项包括：

- 应收金额大于 0 但实收金额为 0 的记录
- 抵扣/优惠/免费金额占比较高
- 超长停车
- 支付方式或渠道过度集中
- 收费高峰时段集中
- 可能影响收入或运营效率的异常模式

输入：

- `CleanedParkingData`
- `MetricsFacts`
- `PaymentProfile`
- `DurationProfile`
- `DomainContextPack`

输出：

- `AnomalyCandidates`

说明：

`AnomalyDetector` 只产生候选事实，是否写入报告由 Agent 判断。

### 3.2 Agent 决策能力

这些能力由 `ReportPlannerAgent` 完成。它们不重新计算数据，只在结构化 facts 上做取舍和表达。

#### ChartPlanSelector

作用：

决定报告应展示哪些图表。

候选图表：

- `payment_method_distribution`
- `payment_channel_distribution`
- `parking_duration_distribution`
- `entry_hour_distribution`
- `charge_hour_distribution`

输入：

- `PaymentProfile`
- `DurationProfile`
- `AnomalyCandidates`
- `TemplateInstructions`

输出：

- `selected_charts`

选择规则：

- 至少选择一张图表
- 优先满足模板明确要求
- 优先选择能支撑补充观察的图表
- 避免选择没有业务解释价值的图表

#### SectionSummaryWriter

作用：

生成章节摘要，包括：

- 支付方式与渠道章节摘要
- 停车时长分析章节摘要

输入：

- `MetricsFacts`
- `PaymentProfile`
- `DurationProfile`
- `TemplateInstructions`

输出：

- `payment_section_summary`
- `duration_section_summary`

要求：

- 使用管理者能直接理解的语言
- 引用的数据必须来自 facts
- 不写无依据的原因判断

#### ObservationSelector

作用：

从 `AnomalyCandidates` 和 profile facts 中选择 2-3 条补充观察。

输入：

- `AnomalyCandidates`
- `MetricsFacts`
- `PaymentProfile`
- `DurationProfile`
- `DomainContextPack`

输出：

- `observations`

每条 observation 必须包含：

- `title`
- `text`
- `business_implication`
- `source_fact_ids`
- 可选 `source_context_ids`

选择原则：

- 优先选择对停车业务管理者有行动价值的观察
- 避免多条观察重复表达同一个问题
- 对可能风险使用谨慎措辞
- 如果领域上下文说明某类现象是正常政策，应避免直接判定为异常

#### RecommendationWriter

作用：

基于选中的 observations 生成 2-4 条可执行建议。

输入：

- `observations`
- `DomainContextPack`
- `ReportRequirements`

输出：

- `recommendations`

每条 recommendation 必须：

- 面向停车业务管理者
- 和至少一个 observation 或 fact 有关
- 避免空泛建议
- 避免超出数据支持范围

### 3.3 渲染与校验工具

这些工具在 Agent 输出后执行。

#### ReportPlanValidator

作用：

校验 Agent 输出是否可用。

检查内容：

- JSON schema 是否合法
- 是否包含必需章节
- 是否至少选择一张图表
- observations 是否为 2-3 条
- recommendations 是否为 2-4 条
- 所有 `source_fact_ids` 是否存在
- 所有 `source_context_ids` 是否存在或可为空
- 是否包含未授权数值
- 是否试图覆盖六个硬指标

输入：

- `ReportPlan`
- `AvailableFactIds`
- `AvailableContextIds`

输出：

- valid / invalid
- validation errors

失败处理：

- 第一次失败：使用修复 prompt 重试
- 第二次失败：使用 deterministic fallback plan

#### ChartRenderer

作用：

根据 `ReportPlan.selected_charts` 生成图表 PNG。

输入：

- `selected_charts`
- `PaymentProfile`
- `DurationProfile`

输出：

- chart image paths

说明：

图表由 deterministic code 生成，不由 LLM 生成图片。

#### DocxRenderer

作用：

基于用户上传的 Word 模板生成最终报告。

输入：

- `template_file_path`
- `MetricsFacts`
- `ReportPlan`
- chart image paths

输出：

- `.docx` report path

说明：

硬指标由 `MetricsFacts` 直接写入，不能使用 Agent 改写后的值。
DocxRenderer 应打开原始模板并做占位替换，而不是从空白文档重建报告。它负责：

- 保留模板标题、章节、表格、颜色、边框和页面设置
- 将关键指标写入模板“填写值”列，并从成品中删除“示例预期值”说明列
- 将 Agent 生成的章节摘要、观察和建议填入对应占位段落
- 在图表占位处插入真实图表
- 移除未替换的主要占位说明

如果模板结构无法识别，DocxRenderer 可以回退到标准报告渲染，但需要记录 fallback 事件。

## 4. 工具编排方式

本项目不采用 Agent 自由决定是否调用所有工具的方式。

原因：

- 六个硬指标必须稳定正确
- 数据清洗和 profile 是必要步骤
- 让 LLM 决定是否计算指标会降低可靠性
- 评审重点是确定性计算与 LLM 推理的边界

因此系统采用固定 workflow 编排：

```text
1. API 创建 job
2. Worker claim pending job
3. ParkingCsvLoader 清洗 CSV
4. MetricsComputer 计算六个硬指标
5. PaymentProfiler 生成支付 profile
6. ParkingDurationProfiler 生成时长 profile
7. DomainContextLoader 处理领域上下文
8. TemplateInstructionExtractor 提取模板说明
9. AnomalyDetector 生成候选关注点
10. ReportPlannerAgent 基于 facts 生成 ReportPlan
11. ReportPlanValidator 校验 ReportPlan
12. ChartRenderer 生成图表
13. DocxRenderer 基于原模板替换占位并生成 Word 报告
14. Worker 标记 job completed
```

Agent 在第 10 步发生作用。

Agent 负责：

- 从候选关注点中选择报告重点
- 选择图表
- 决定章节叙述重点
- 生成补充观察
- 生成结论建议

Agent 不负责：

- 是否执行数据清洗
- 是否计算硬指标
- 是否生成至少一张图
- 是否保存报告
- 是否更新 job 状态
- Word 模板样式如何保留
- 占位符在 DOCX 中如何替换

## 5. 工具是否暴露给 OpenAI Agents SDK

v1 中，数据清洗和统计工具不作为 OpenAI function tools 暴露给 LLM，而是由 workflow 预先执行。

`ReportPlannerAgent` 看到的是工具执行后的结构化结果。

这样做的原因是保证 deterministic computation 的稳定性。

未来如果需要支持未知模板或交互式追问，可以把以下查询工具暴露给 Agent SDK：

- `get_metric(metric_name)`
- `get_payment_profile()`
- `get_duration_profile()`
- `list_anomaly_candidates()`
- `get_template_instructions()`

v1 暂不需要这些自由 tool calling 能力。

## 6. Grounding

### 6.1 设计原则

本系统不让 LLM 直接读取原始 CSV 并自行计算关键数字。

所有硬指标、分布统计、停车时长、异常候选都由确定性 Python 代码计算。LLM 只接收经过验证的结构化事实，并基于这些事实做内容取舍和语言组织。

### 6.2 确定性事实来源

Agent 的输入包括：

- `metrics`：六个硬指标
- `payment_profile`：支付方式和支付渠道分布
- `duration_profile`：停车时长、入场时间、收费时间分布
- `anomaly_candidates`：由代码触发的异常/关注点候选
- `template_instructions`：从模板中提取的章节说明
- `domain_context_pack`：用户上传领域知识归一化后的上下文

### 6.3 LLM 不能做的事

LLM 不允许：

- 重新计算六个硬指标
- 修改确定性代码计算出的数值
- 引用输入 facts 中不存在的数字
- 声称存在没有数据支持的问题
- 把“可能风险”写成确定违规
- 输出不符合 schema 的自由文本报告

### 6.4 结构化输出

Agent 必须输出 `ReportPlan`，而不是直接输出 Word 文档。

`ReportPlan` 包含：

- `selected_charts`
- `payment_section_summary`
- `duration_section_summary`
- `observations`
- `recommendations`

每条观察和建议必须带：

- `source_fact_ids`
- 可选 `source_context_ids`

示例：

```json
{
  "title": "抵扣和优惠敞口较高",
  "text": "实际抵扣总额为 48,285.0 元，占应收金额约 45.6%，建议复核优惠核销规则。",
  "business_implication": "优惠和抵扣类交易对实收金额影响明显，需要关注核销成本和政策执行。",
  "source_fact_ids": [
    "metrics.total_actual_deductions",
    "metrics.total_receivable"
  ]
}
```

### 6.5 输出校验

`ReportPlanValidator` 会检查：

- 是否包含必需章节
- 观察是否为 2-3 条
- 建议是否为 2-4 条
- 是否至少选择一张图表
- 所有 `source_fact_ids` 是否存在
- 是否试图覆盖六个硬指标
- 数值引用是否来自 `ReportFacts`
- JSON schema 是否合法

如果校验失败：

1. 记录 `agent_output_validation_failed`
2. 使用修复 prompt 重试一次
3. 仍失败则使用 deterministic fallback plan
4. job 不返回未经校验的 agent 输出

## 7. Instrumentation

### 7.1 设计目标

系统需要记录两类结构化日志：

1. 用户请求和 job 生命周期日志
2. LLM / Agent 调用日志

所有日志以 JSON 格式输出到 stdout，并可选写入 PostgreSQL，方便 Docker logs、本地调试和后续接入日志系统。

### 7.2 Job 生命周期日志

每个用户请求都会生成 `job_id`。系统在关键节点记录事件：

- `job_created`
- `file_saved`
- `job_claimed_by_worker`
- `data_validation_started`
- `data_validation_completed`
- `metrics_computed`
- `profiles_computed`
- `agent_planning_started`
- `agent_planning_completed`
- `chart_rendering_started`
- `docx_generation_started`
- `job_completed`
- `job_failed`

示例：

```json
{
  "event": "job_created",
  "job_id": "job_123",
  "timestamp": "2026-06-26T10:12:00Z",
  "template_filename": "停车明细分析报告_模板.docx",
  "data_filename": "data.csv",
  "data_file_size": 307905,
  "template_file_size": 42342
}
```

### 7.3 LLM 调用日志

每次 LLM 调用必须记录：

- `job_id`
- `agent_name`
- `model`
- `prompt`
- `response`
- `latency_ms`
- `usage`
- `status`
- `error`，如果失败

示例：

```json
{
  "event": "llm_call_completed",
  "job_id": "job_123",
  "agent_name": "ReportPlannerAgent",
  "model": "gpt-4.1-mini",
  "latency_ms": 1830,
  "prompt": "...",
  "response": "...",
  "usage": {
    "input_tokens": 1580,
    "output_tokens": 620
  }
}
```

### 7.4 Agent 决策日志

除了原始 prompt/response，还会记录 Agent 的结构化决策结果：

- 选择了哪些图表
- 选择了哪些补充观察
- 每条观察引用了哪些 `source_fact_ids`
- 哪些候选洞察被放弃
- 是否使用了 fallback

示例：

```json
{
  "event": "report_plan_created",
  "job_id": "job_123",
  "agent_name": "ReportPlannerAgent",
  "selected_chart_ids": [
    "payment_method_distribution",
    "parking_duration_distribution"
  ],
  "selected_observation_ids": [
    "discount_exposure_high",
    "zero_collected_review"
  ],
  "fallback_used": false
}
```

### 7.5 日志安全

日志不记录：

- API key
- 用户上传文件全文
- 完整原始 CSV 内容
- 本地绝对敏感路径

日志可以记录：

- 文件名
- 文件大小
- 文件 hash
- job id
- prompt
- response
- 结构化 facts 摘要

## 8. 失败处理与 fallback

### 8.1 LLM 调用失败

如果 LLM 调用失败：

1. 记录 `llm_call_failed`
2. 保存错误信息
3. 使用 `MockReportPlanner` 或 deterministic fallback plan
4. 继续生成报告，除非 fallback 也失败

### 8.2 Agent 输出校验失败

如果 Agent 输出不符合 schema 或引用不存在的事实：

1. 记录 `agent_output_validation_failed`
2. 使用修复 prompt 重试一次
3. 再次失败则 fallback

### 8.3 Fallback plan

Fallback plan 基于 deterministic facts 生成保底内容：

- 默认选择支付方式分布图
- 根据 metrics 和 profile 生成保守观察
- 建议使用谨慎、通用、可执行的表达

Fallback 不用于展示 LLM 智能性，只用于保证系统可运行和测试稳定。

## 9. 未来扩展

v1 不实现以下 Agent，但保留扩展方向：

### DomainContextAgent

用于把上传的非结构化领域文档整理成 `DomainContextPack`。

v1 可以先用简单文本抽取和规则归一化；如果领域资料复杂，再引入该 Agent。

### ReportReviewAgent

用于检查报告草稿是否：

- 遗漏关键要求
- 引用无依据数字
- 语气过度确定
- 缺少图表或建议

v1 使用 `ReportPlanValidator` 做结构化校验，不额外引入审校 Agent。

### TemplatePlanningAgent

用于支持更自由的未知模板结构：

- 解析模板章节意图
- 将数据能力映射到模板需求
- 生成模板填充计划

v1 只支持当前模板和相似结构模板，不承诺任意 DOCX 模板理解。
