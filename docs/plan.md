# Plan: 停车明细分析报告智能生成系统技术方案

## 1. 目标

本方案用于落地 `spec.md` 中定义的停车报告生成系统。

技术设计目标：

- 用简单可靠的架构完成 upload -> async generation -> status -> download
- 保证六个硬指标由确定性代码计算
- 使用 Agent 做报告内容取舍，而不是让 LLM 直接计算事实
- 记录 job 生命周期和 LLM 调用日志
- 提供一键运行、可测试、可演示的面试作业交付物

## 2. 技术栈

### 2.1 使用的技术

- Backend API：FastAPI
- Database：PostgreSQL
- ORM / schema：SQLAlchemy 或 SQLModel + Pydantic
- Async execution：Python DB-backed worker
- Agent framework：OpenAI Agents SDK
- LLM provider：OpenAI API，支持可选 `OPENAI_BASE_URL`
- CSV/data processing：Python csv / pandas + Decimal
- Chart rendering：matplotlib
- DOCX generation：python-docx
- Frontend：React + TypeScript
- Packaging：Docker Compose
- Testing：pytest + FastAPI TestClient / httpx
- Logging：JSON structured logs to stdout，可选写入 PostgreSQL

### 2.2 暂不使用的技术

- Temporal：v1 不接入。当前任务只需要轻量异步生成，使用 DB-backed worker 更符合 take-home 范围。workflow 会拆成 activity-like steps，未来可迁移到 Temporal。
- Qdrant：v1 不做长期知识库或 RAG 检索。领域上下文先通过上传文件和 free-text instruction 进入本次 job。
- S3：v1 使用本地 Docker volume。文件访问通过 `StorageService` 抽象，未来可替换为 S3。
- Valkey / Redis：v1 不引入额外队列或缓存，job 状态以 PostgreSQL 为准。
- Kubernetes：交付以 Docker Compose 为准。

## 3. 系统架构

```text
React UI
  -> FastAPI API
  -> PostgreSQL jobs / logs
  -> Python Worker
  -> ReportGenerationWorkflow
      -> ParkingCsvLoader
      -> MetricsComputer
      -> PaymentProfiler
      -> ParkingDurationProfiler
      -> DomainContextLoader
      -> TemplateInstructionExtractor
      -> AnomalyDetector
      -> ReportPlannerAgent
      -> ReportPlanValidator
      -> ChartRenderer
      -> TemplateAwareDocxRenderer
  -> generated .docx
```

API 和 worker 是两个独立进程：

- `api` 负责接收上传、创建 job、查询状态、下载文件
- `worker` 负责扫描 pending jobs 并执行报告生成
- `db` 作为状态中心，保存 job、事件日志和 LLM 调用日志
- `frontend` 提供最小上传和状态页面

## 4. 项目目录

```text
park-agent/
  app/
    api/
      __init__.py
      jobs.py
    agent/
      __init__.py
      report_planner.py
      report_plan_schema.py
      report_plan_validator.py
      llm_logging.py
      prompts.py
    config/
      __init__.py
      settings.py
      domain_rules.py
    data/
      __init__.py
      parking_csv_loader.py
      models.py
    db/
      __init__.py
      models.py
      session.py
      migrations/
    observability/
      __init__.py
      events.py
    profiling/
      __init__.py
      payment_profiler.py
      duration_profiler.py
      anomaly_detector.py
    report/
      __init__.py
      chart_renderer.py
      docx_renderer.py
      template_instructions.py
    storage/
      __init__.py
      local_storage.py
      storage_service.py
    workflows/
      __init__.py
      report_generation.py
    main.py
    worker.py
  frontend/
    src/
    package.json
  tests/
    test_jobs_api.py
    test_metrics.py
    test_parking_csv_loader.py
    test_report_plan_validator.py
  docs/
    spec.md
    plan.md
    agent_design.md
    tasks.md
  samples/
    generated_report.docx
    sample_job_log.jsonl
    sample_llm_log.jsonl
  Dockerfile
  docker-compose.yml
  requirements.txt
  .env.example
  .gitignore
  README.md
  LICENSE
```

目录职责：

- `app/api`：REST API
- `app/worker.py`：后台 worker 入口
- `app/workflows`：报告生成主流程
- `app/data`：CSV 清洗、字段校验、数据模型
- `app/profiling`：支付、停车时长、异常候选分析
- `app/agent`：Agent、prompt、结构化输出和校验
- `app/report`：图表和 Word 文档生成
- `app/observability`：结构化日志
- `app/storage`：上传文件和输出文件存储抽象
- `tests`：API 和核心逻辑测试
- `docs`：规格、技术计划、Agent 设计和任务拆分

## 5. API 设计

### 5.1 创建任务

```http
POST /jobs
Content-Type: multipart/form-data
```

输入：

- `template_file`: `.docx`
- `data_file`: `.csv`
- `domain_context_files`: 可选，多文件
- `instructions`: 可选文本

响应：

```json
{
  "job_id": "job_01HXYZ",
  "status": "pending"
}
```

行为：

- 保存上传文件
- 创建 job row
- 记录 `job_created`
- 立即返回，不等待生成完成

### 5.2 查询状态

```http
GET /jobs/{job_id}
```

响应：

```json
{
  "job_id": "job_01HXYZ",
  "status": "completed",
  "created_at": "2026-06-26T10:00:00Z",
  "started_at": "2026-06-26T10:00:03Z",
  "completed_at": "2026-06-26T10:00:18Z",
  "download_url": "/jobs/job_01HXYZ/download"
}
```

### 5.3 下载报告

```http
GET /jobs/{job_id}/download
```

行为：

- job 必须为 `completed`
- 输出文件必须存在
- 返回 `.docx`
- 对 `pending / running / failed / unknown` job 返回对应错误

## 6. 数据模型

### 6.1 Job

保存异步任务状态：

- `id`
- `status`: `pending / running / completed / failed`
- `template_path`
- `data_path`
- `domain_context_paths`
- `instructions`
- `output_path`
- `error_message`
- `created_at`
- `started_at`
- `completed_at`

### 6.2 JobEvent

保存 job 生命周期日志：

- `id`
- `job_id`
- `event`
- `payload`
- `created_at`

### 6.3 LLMCallLog

保存 LLM 调用日志：

- `id`
- `job_id`
- `agent_name`
- `model`
- `prompt`
- `response`
- `latency_ms`
- `usage`
- `status`
- `error_message`
- `created_at`

### 6.4 ReportFacts

工作流内部结构，不一定落库：

- `metrics`
- `payment_profile`
- `duration_profile`
- `anomaly_candidates`
- `template_instructions`
- `domain_context_pack`

### 6.5 ReportPlan

Agent 输出结构：

- `selected_charts`
- `payment_section_summary`
- `duration_section_summary`
- `observations`
- `recommendations`

每条 observation 和 recommendation 应包含 `source_fact_ids`。

## 7. Workflow 设计

报告生成流程：

```text
1. Worker claim pending job
2. Mark job as running
3. Save job_started event
4. ParkingCsvLoader cleans and validates CSV
5. MetricsComputer computes six hard metrics
6. PaymentProfiler builds payment profile
7. ParkingDurationProfiler builds duration profile
8. DomainContextLoader builds domain context pack
9. TemplateInstructionExtractor extracts template instructions
10. AnomalyDetector creates candidate insights
11. ReportPlannerAgent creates ReportPlan
12. ReportPlanValidator validates ReportPlan
13. ChartRenderer renders selected charts
14. TemplateAwareDocxRenderer fills original DOCX template
15. Mark job as completed
```

失败处理：

```text
Any step raises exception
  -> log job_failed
  -> save error_message
  -> mark job as failed
```

## 8. Worker 设计

worker 是一个 Python 后台进程，不依赖 Celery 或 Temporal。

行为：

```text
loop:
  claim one pending job
  if no job:
    sleep
  else:
    run ReportGenerationWorkflow
```

claim job 时需要避免重复执行：

- 使用数据库事务
- 只 claim `status = pending` 的 job
- claim 后立刻更新为 `running`

v1 不实现自动 retry，但保留 retry 需要的字段和边界。

## 9. Agent 设计概览

v1 使用单个 Agent：

```text
ReportPlannerAgent
```

Agent 输入：

- 确定性指标
- 支付 profile
- 停车时长 profile
- 异常候选
- 模板说明
- 领域上下文

Agent 输出：

- 图表选择
- 支付方式与渠道摘要
- 停车时长摘要
- 2-3 条补充观察
- 2-4 条建议

Agent 不负责：

- 计算硬指标
- 修改硬指标
- 读取原始 CSV
- 直接生成 DOCX
- 直接绘制图表

Agent 输出必须通过 `ReportPlanValidator`。

更详细的工具编排、grounding 和 instrumentation 写在 `docs/agent_design.md`。

## 10. 数据清洗与指标计算

### 10.1 CSV 清洗

处理规则：

- 使用 `utf-8-sig` 读取
- 去除列名首尾空白
- 校验必需列
- 金额字段转 Decimal
- 时间字段按 `%Y-%m-%d %H:%M:%S` 解析
- 支付方式、支付渠道转字符串并去除首尾空白

格式错误时：

- 抛出 `DataValidationError`
- job 标记为 `failed`
- 日志记录失败原因

### 10.2 硬指标

六个硬指标全部由确定性代码计算：

- 总交易笔数：行数
- 应收总金额：`sum(应收金额)`
- 实收总金额：`sum(实收金额(元))`
- 实际抵扣总额：`sum(实际抵扣额(元))`
- 实收率：`实收总金额 / 应收总金额 * 100`
- 主要支付方式：交易笔数最高的 `支付方式`

金额计算使用 Decimal，避免 float 精度问题。

## 11. 报告生成

### 11.1 图表

`ChartRenderer` 根据 `ReportPlan.selected_charts` 生成 PNG。

候选图表：

- 支付方式分布图
- 支付渠道分布图
- 停车时长分布图
- 入场时间分布图
- 收费时间分布图

至少生成一张图表。

### 11.2 Word 文档

`DocxRenderer` 使用 `python-docx` 打开用户上传的 `.docx` 模板，并在原模板上替换占位内容。默认策略是 template-aware rendering，而不是从空白文档重新生成。

写入内容：

- 报告信息
- 六个硬指标
- 图表
- 支付方式与渠道摘要
- 停车时长摘要
- 补充观察
- 结论与建议

硬指标从 `MetricsFacts` 写入，不使用 Agent 改写后的数值。

模板保真策略：

- 保留原模板的页面设置、标题样式、章节样式和表格样式
- 对关键指标表格，替换第二列“填写值”，并删除仅用于指导生成的第三列“示例预期值”
- 对支付方式、停车时长、补充观察、结论建议等占位段落，在原占位段落位置替换文本
- 对图表占位段落，在该段落位置插入真实图表，删除或清空占位说明
- 尽量保留模板原有 run 样式，例如红色斜体占位被替换后可继承所在段落样式，必要时统一设置中文 East Asia 字体

模板结构识别：

- 通过段落文本匹配章节标题，例如 `一、关键指标`、`二、支付方式与渠道`
- 通过表格表头匹配关键指标表格，例如 `指标 / 填写值 / 示例预期值`
- 通过占位文本匹配需要替换的段落，例如包含 `【叙述`、`【占位图`、`【智能体生成`、`【依据上述分析`

fallback 策略：

- 如果模板无法打开或结构无法识别，记录 `template_rendering_fallback_used`
- fallback 到标准空白文档渲染，保证 job 仍可产出报告
- fallback 原因写入结构化日志，便于调试模板适配问题

## 12. Observability

### 12.1 Job 生命周期日志

关键事件：

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

日志输出为 JSON 到 stdout，可选写入 `job_events` 表。

### 12.2 LLM 调用日志

每次 LLM 调用记录：

- `job_id`
- `agent_name`
- `model`
- `prompt`
- `response`
- `latency_ms`
- `usage`
- `status`
- `error_message`

日志不得包含 API key。

## 13. 测试方案

### 13.1 API-level test

至少实现一个测试：

```text
submit -> status -> download
```

测试中 mock 报告生成过程，不依赖真实 OpenAI API。

### 13.2 单元测试

建议覆盖：

- CSV loader 缺列、BOM、金额解析、时间解析
- 六个硬指标计算
- 支付方式 profile
- 停车时长 profile
- ReportPlanValidator
- 模板占位替换和关键指标成品两列表格

## 14. 运行与交付

### 14.1 Docker Compose

服务：

- `api`
- `worker`
- `db`
- `frontend`

命令：

```bash
cp .env.example .env
docker compose up --build
```

### 14.2 LLM 模式

支持：

- `LLM_MODE=auto`
- `LLM_MODE=openai`
- `LLM_MODE=mock`

行为：

- 有 `OPENAI_API_KEY` 时使用真实 OpenAI Agent
- 无 key 时可 fallback 到 mock planner
- mock 模式只用于本地 smoke test 和 CI，不用于展示真实 LLM 智能性

### 14.3 GitHub 交付内容

- 源代码
- `README.md`
- `.env.example`
- `Dockerfile`
- `docker-compose.yml`
- `docs/`
- `samples/generated_report.docx`
- `samples/sample_job_log.jsonl`
- `samples/sample_llm_log.jsonl`
- GPLv3 `LICENSE`

## 15. 边界功能与扩展点

这些功能属于重要边界，但 v1 不完整实现。它们是技术设计和未来演进策略，不是当前必须验收的功能。

### 15.1 Retry

v1：

- 不自动重试整个 job
- Agent 输出校验失败时最多可重试一次 LLM 修复
- job 失败后保存错误状态和错误信息

预留：

- `attempt_count`
- `max_attempts`
- `last_error`
- `next_run_at`
- 幂等 output path

未来：

- DB worker 可增加 retry/backoff
- 或迁移到 Temporal retry policy

### 15.2 Idempotency

v1：

- 每个 job 使用唯一 `job_id`
- 输出文件路径由 `job_id` 决定
- worker 只 claim `pending` job，避免重复执行

未来：

- 可根据上传文件 hash + instructions 生成 idempotency key
- 支持用户重复提交时返回已有 job

### 15.3 Concurrency

v1：

- 单 worker 或少量 worker
- 使用数据库事务 claim job

未来：

- 多 worker 并发处理
- job-level locking
- per-user rate limit

### 15.4 Cancellation

v1：

- 不提供取消任务接口

未来：

- 增加 `cancel_requested`
- worker 在步骤间检查取消状态
- Temporal 版本可使用 workflow cancellation

### 15.5 File retention

v1：

- 文件保存在本地 volume
- 不做自动清理

未来：

- 增加 retention policy
- 定期清理过期 uploads / outputs
- 生产环境迁移到 S3 lifecycle policy

### 15.6 Access control

v1：

- 不实现认证/授权
- 下载通过 `job_id` 访问

未来：

- 用户账户
- job ownership
- signed download URL
- audit trail

### 15.7 Domain knowledge / RAG

v1：

- 可选上传领域文件和 free-text instruction
- 归一化为本次 job 的 `DomainContextPack`

未来：

- 长期企业知识库
- Qdrant 向量检索
- 多模态领域资料

### 15.8 Storage abstraction

v1：

- 本地文件存储

未来：

- S3-compatible storage
- 天翼云对象存储
- 文件加密

### 15.9 Workflow engine

v1：

- Python DB-backed worker

未来：

- 将 `ReportGenerationWorkflow` 拆成 Temporal workflow 和 activities
- 使用 Temporal retry、timeout、durable execution

### 15.10 Observability integrations

v1：

- JSON logs to stdout
- 可选数据库日志表

未来：

- OpenTelemetry
- Sentry
- structured log aggregation
- tracing dashboard
