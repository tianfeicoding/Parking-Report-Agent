# Park Agent

Park Agent 是一个停车明细分析报告生成系统。用户上传停车交易 CSV 和 Word
报告模板后，后台任务会清洗数据、确定性计算指标、调用 Agent 规划报告内容，
最后生成保留原模板样式的 `.docx` 报告。

## 核心能力

- 上传停车明细 CSV 和 `.docx` 报告模板
- 可选上传 `.txt`、`.md`、`.docx` 领域知识文件
- 确定性计算交易笔数、应收、实收、抵扣和实收率
- 分析支付方式、支付渠道、停车时长和异常候选项
- Agent 根据事实、模板说明和领域上下文选择观察、建议及图表
- 生成中文图表并填充到原始 Word 模板
- 异步执行 `pending -> running -> completed/failed` 任务
- 记录任务生命周期和 LLM 调用的结构化日志
- LLM 不可用时自动回退到 deterministic mock planner

## 技术栈

- API：Python 3.12、FastAPI、SQLAlchemy
- Agent：OpenAI Agents SDK、结构化 `ReportPlan`
- 数据库：PostgreSQL 16
- Worker：Python 数据库轮询 worker，使用行锁领取任务
- 文档：python-docx、Matplotlib、Noto CJK
- 前端：React、TypeScript、Vite
- 本地运行：Docker Compose

## 架构与职责

```text
React UI / REST API
        |
        v
PostgreSQL Job Queue
        |
        v
Python Worker
  |- CSV validation and cleaning
  |- deterministic metrics and profiles
  |- anomaly candidates
  |- template/domain context extraction
  |- ReportPlannerAgent
  |- ReportPlan validation and fallback
  |- Chinese chart rendering
  `- template-aware DOCX rendering
```

确定性代码负责计算所有硬指标，LLM 不重新计算或修改数值。Agent 只负责判断：

- 哪些事实值得出现在报告中
- 应选择哪些图表
- 如何形成有依据的观察
- 应提出哪些谨慎、可执行的建议

Agent 输出必须符合结构化 schema，并通过 `source_fact_ids` 和
`source_context_ids` 校验。校验失败时系统会尝试修复；调用失败或修复失败时
回退到 mock planner，保证任务仍可生成报告。

详细设计见：

- [需求规格](docs/spec.md)
- [技术方案](docs/plan.md)
- [Agent 设计](docs/agent_design.md)
- [任务清单](docs/tasks.md)

## 快速启动

### 1. 环境要求

- Docker Desktop
- Docker Compose v2

### 2. 启动服务

```bash
docker compose up --build
```

`.env` 是可选文件。不创建 `.env` 时，系统使用默认配置并进入 mock 模式，
因此克隆仓库后可以直接使用上述单条命令启动。

需要调用 OpenAI 或第三方 OpenAI-compatible API 时，再创建本地配置：

```bash
cp .env.example .env
# 编辑 .env 后重启 API 和 worker
docker compose up -d --build api worker
```

首次构建需要下载 Python 依赖和 Noto CJK 中文字体，耗时会相对较长。启动后访问：

- 前端：http://localhost:3000
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

后台启动：

```bash
docker compose up -d --build
docker compose ps
```

停止服务：

```bash
docker compose down
```

如需同时清除数据库和报告存储卷：

```bash
docker compose down -v
```

## LLM 配置

配置文件为项目根目录下的 `.env`。不要提交该文件或真实 API key。

### Mock 模式

适合检查完整工作流、API、前端和文档生成，不会调用外部 LLM：

```dotenv
OPENAI_API_KEY=
LLM_MODE=mock
```

### OpenAI 模式

```dotenv
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
OPENAI_AGENT_API=responses
LLM_MODE=openai
```

### 第三方 OpenAI-compatible 中转站

```dotenv
OPENAI_API_KEY=your_relay_api_key
OPENAI_BASE_URL=https://your-relay.example.com/v1
OPENAI_MODEL=gpt-4.1-mini
OPENAI_AGENT_API=chat_completions
LLM_MODE=openai
```

`OPENAI_BASE_URL` 通常必须包含 `/v1`。具体模型名和 API 类型以中转站支持情况为准。

`LLM_MODE` 支持：

| 值 | 行为 |
| --- | --- |
| `mock` | 始终使用本地 mock planner |
| `openai` | 强制调用配置的 OpenAI-compatible API，失败后记录并 fallback |
| `auto` | 存在 key 时调用 LLM，否则使用 mock |

修改 `.env` 后需要重建或重启 API 和 worker：

```bash
docker compose up -d --build api worker
```

## 使用方式

### 前端

打开 http://localhost:3000，上传：

1. Word 报告模板 `.docx`
2. 停车明细 `.csv`
3. 可选领域知识文件
4. 可选本次报告说明

提交后页面会轮询任务状态；任务完成后可直接下载报告。

### REST API

创建任务：

```bash
curl -X POST http://localhost:8000/jobs \
  -F "template_file=@/path/to/template.docx" \
  -F "data_file=@/path/to/data.csv" \
  -F "instructions=重点关注实收率和长时停车"
```

可重复添加领域知识文件：

```bash
curl -X POST http://localhost:8000/jobs \
  -F "template_file=@/path/to/template.docx" \
  -F "data_file=@/path/to/data.csv" \
  -F "domain_context_files=@/path/to/policy.md" \
  -F "domain_context_files=@/path/to/operations.docx"
```

响应示例：

```json
{
  "job_id": "job_0123456789abcdef",
  "status": "pending"
}
```

查询状态：

```bash
curl http://localhost:8000/jobs/{job_id}
```

下载报告：

```bash
curl -L http://localhost:8000/jobs/{job_id}/download \
  -o parking_detail_analysis_report.docx
```

## CSV 输入要求

CSV 使用 UTF-8 或 UTF-8 BOM 编码，并包含以下列：

```text
应收金额
实收金额(元)
免费金额(元)
充值卡扣费(元)
抵扣金额(元)
抵扣时长(小时)
实际抵扣额(元)
支付方式
支付渠道
收费时间
进车时间
```

时间格式必须为：

```text
YYYY-MM-DD HH:MM:SS
```

金额使用 `Decimal` 解析，空金额按 `0` 处理；必需列缺失、金额非法或时间格式错误会使
任务进入 `failed` 状态，并在状态接口返回错误信息。

## 模板与领域知识

当前版本针对提供的停车报告模板做了模板保真适配：

- 保留页面设置、标题、章节和表格样式
- 填写数据周期、生成时间和关键指标
- 删除仅供参考的“示例预期值”列
- 替换支付、时长、观察、建议和图表占位内容
- 图表标题、分类名称和坐标轴使用中文

模板解析会把标题、章节、包含 `【` 或 `[` 的占位文本及模板全文提供给 Agent。
当前渲染器仍通过已知表头和占位语句定位填充位置，不是通用的任意 Word 模板引擎，
也暂未按字体颜色单独识别红色提示。无法识别模板结构时会记录原因，并回退到标准报告。

领域知识支持 `.txt`、`.md` 和 `.docx`。文件内容会作为本次任务上下文，不要求用户遵循
固定 JSON 格式；v1 直接提取文字，不包含向量检索或复杂 RAG。

## 日志与调试

查看所有服务日志：

```bash
docker compose logs -f
```

分别查看 API 或 worker：

```bash
docker compose logs -f api
docker compose logs -f worker
```

日志以 JSON 输出，主要事件包括：

- `job_created`
- `job_claimed_by_worker`
- `agent_planning_started`
- `llm_call_started`
- `llm_call_completed` / `llm_call_failed`
- `report_planner_fallback_used`
- `template_rendering_fallback_used`
- `job_completed` / `job_failed`

任务事件同时写入 `job_events` 表。LLM 的模型、prompt、response、延迟、状态和错误写入
`llm_call_logs` 表，便于事后复盘 Agent 行为。日志会经过基础脱敏处理，但生产环境仍应
根据企业数据分类策略进一步限制日志内容和保留周期。

出现 `fallback=True` 时，优先检查：

1. `OPENAI_BASE_URL` 是否包含 `/v1`
2. 中转站是否支持配置的模型
3. `OPENAI_AGENT_API` 是否应使用 `chat_completions`
4. worker 日志中的 `llm_call_failed` 和 `report_planner_fallback_used`

## 测试

运行完整后端测试：

```bash
docker compose run --rm api pytest -q
```

当前测试覆盖：

- CSV 校验和清洗
- 硬指标、支付和时长 profile
- Agent 输出校验及 fallback
- 中文图表和模板感知 DOCX 渲染
- API 级 `submit -> status -> download` 流程

## 设计取舍

- 使用轻量数据库轮询 worker，而非 Temporal：take-home 范围内更容易运行和评审，同时保留清晰的任务生命周期边界。
- 使用 PostgreSQL 存储任务与日志，文件使用 Docker volume：本地交付简单；生产环境可替换为 S3 和正式任务编排系统。
- LLM 只做报告规划，硬指标由代码计算：降低幻觉和数值漂移风险。
- 领域知识直接提取文本，不做 RAG：先保证 grounding 和可调试性，后续可接入 Qdrant。
- 模板渲染优先适配当前报告结构：保留原模板视觉效果；通用模板位置建模属于后续扩展。

## 安全说明

- `.env` 已加入 `.gitignore`
- API key 只能放在本地 `.env` 或部署平台 Secret 中
- 不要把真实 key 写入 README、代码、示例日志或前端环境变量
- 上传文件和生成报告存储在 Docker volume 中，不应提交到 Git
- 面向生产环境时还需要增加认证、授权、文件大小限制、恶意文档扫描和数据保留策略
