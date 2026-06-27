# Tasks: 停车明细分析报告智能生成系统

## 使用方式

- 每完成一个 task，并通过对应验证后，将 `[ ]` 改为 `[x]`
- 不要只因为代码写完就标记完成；必须满足 Done Criteria
- 每个 Phase 结束后运行相关测试或手动验证
- 关键 Phase 完成后执行 code review
- Review 发现的问题应作为新 task 补充到对应 Phase

## Phase 1: Project Setup

- [x] 初始化 FastAPI 后端目录结构
- [x] 初始化 React + TypeScript 前端目录结构
- [x] 添加 `requirements.txt`
- [x] 添加 `Dockerfile`
- [x] 添加 `docker-compose.yml`
- [x] 添加 PostgreSQL 服务配置
- [x] 添加 `.env.example`
- [x] 添加 `.gitignore`
- [x] 实现 `/health` API

Done Criteria:

- `docker compose up --build` 可以启动基础服务
- API `/health` 返回成功
- `.env` 不会被提交
- 项目目录与 `docs/plan.md` 基本一致

Verification:

```bash
docker compose up --build
curl http://localhost:8000/health
```

Review Gate:

- [ ] Phase 1 review：检查项目结构、Docker、环境变量和基础启动方式

## Phase 2: Database, Job API, and Storage

- [x] 定义 `Job` 数据模型
- [x] 定义 `JobEvent` 数据模型
- [x] 定义 `LLMCallLog` 数据模型
- [x] 实现数据库 session 管理
- [x] 实现本地 `StorageService`
- [x] 实现上传文件保存
- [x] 实现 `POST /jobs`
- [x] 实现 `GET /jobs/{job_id}`
- [x] 实现 `GET /jobs/{job_id}/download`
- [x] 对未完成、失败、不存在的 job 返回正确错误

Done Criteria:

- 上传模板和 CSV 后返回 `job_id`
- job 状态可查询
- completed job 可以下载 `.docx`
- pending/running/failed job 不允许下载成功报告
- 上传文件保存到 job 专属路径

Verification:

```bash
pytest tests/test_jobs_api.py
```

Review Gate:

- [ ] Phase 2 review：检查 API 行为、文件路径安全、job 状态和下载边界

## Phase 3: Worker and Report Workflow

- [x] 实现 Python DB-backed worker 入口
- [x] 实现 pending job claim 逻辑
- [x] 使用数据库事务避免重复 claim
- [x] 实现 `ReportGenerationWorkflow` 框架
- [x] 实现 job `running` 状态更新
- [x] 实现 job `completed` 状态更新
- [x] 实现 job `failed` 状态更新
- [x] 记录 workflow 关键生命周期事件

Done Criteria:

- worker 可以扫描并处理 pending job
- 成功任务变为 `completed`
- 异常任务变为 `failed`
- 错误信息写入 job
- 同一个 job 不会被重复处理

Verification:

```bash
pytest tests/test_jobs_api.py
```

Review Gate:

- [ ] Phase 3 review：检查 worker claim、状态流转、失败处理和幂等边界

## Phase 4: CSV Cleaning and Deterministic Metrics

- [x] 定义 `CleanedParkingData` / `ParkingRow`
- [x] 实现 `ParkingCsvLoader`
- [x] 支持 `utf-8-sig`
- [x] 标准化 CSV 列名
- [x] 校验必需列
- [x] 将金额字段解析为 Decimal
- [x] 将时间字段解析为 datetime
- [x] 实现 `MetricsComputer`
- [x] 计算总交易笔数
- [x] 计算应收总金额
- [x] 计算实收总金额
- [x] 计算实际抵扣总额
- [x] 计算实收率
- [x] 计算主要支付方式
- [x] 添加 CSV loader 单元测试
- [x] 添加 metrics 单元测试

Done Criteria:

- 样例 `data.csv` 可以成功解析
- 六个硬指标计算正确
- 缺列时抛出清晰错误
- 非法金额或非法时间会导致 validation failure
- 硬指标不依赖 LLM

Verification:

```bash
pytest tests/test_parking_csv_loader.py tests/test_metrics.py
```

Review Gate:

- [ ] Phase 4 review：重点检查 Decimal、时间解析、硬指标定义和边界测试

## Phase 5: Data Profiling and Candidate Insights

- [x] 实现 `PaymentProfiler`
- [x] 输出支付方式笔数、占比、金额分布
- [x] 输出支付渠道笔数、占比、金额分布
- [x] 实现 `ParkingDurationProfiler`
- [x] 计算停车时长
- [x] 输出平均值、中位数、最大值
- [x] 输出 2 小时时长分布
- [x] 输出入场小时分布
- [x] 输出收费小时分布
- [x] 实现 `DomainContextLoader`
- [x] 支持 free-text instructions
- [x] 支持默认停车经营分析准则
- [x] 实现 `TemplateInstructionExtractor`
- [x] 提取模板章节和占位说明
- [x] 实现 `AnomalyDetector`
- [x] 生成零实收、抵扣敞口、超长停车、渠道集中等候选关注点
- [x] 添加 profile 和 anomaly 测试

Done Criteria:

- workflow 能产出完整 `ReportFacts`
- 候选关注点是结构化 facts，不是最终结论
- 没有领域文件时可使用默认规则
- 模板说明可作为 Agent 输入

Verification:

```bash
pytest tests/test_profiles.py tests/test_anomaly_detector.py
```

Review Gate:

- [ ] Phase 5 review：检查 profile 是否准确、候选洞察是否有事实依据

## Phase 6: Agent Planning, Grounding, and Validation

- [x] 定义 `ReportPlan` Pydantic schema
- [x] 定义 `ChartPlan`
- [x] 定义 `Observation`
- [x] 定义 `Recommendation`
- [x] 实现 `ReportPlannerAgent`
- [x] 实现 OpenAI Agents SDK 调用
- [x] 实现 prompt 构造
- [x] 实现 `MockReportPlanner`
- [x] 实现 `ReportPlanValidator`
- [x] 校验 `source_fact_ids`
- [x] 校验 observation 数量为 2-3 条
- [x] 校验 recommendation 数量为 2-4 条
- [x] 校验至少选择一张图表
- [x] 防止 Agent 覆盖硬指标
- [x] 实现 LLM 调用失败 fallback
- [x] 实现 Agent 输出校验失败后重试一次
- [x] 添加 validator 测试

Done Criteria:

- 真实 LLM 模式可以生成结构化 `ReportPlan`
- mock 模式不依赖 API key
- 无效 `source_fact_ids` 会被拒绝
- Agent 不计算或修改六个硬指标
- fallback 行为可追踪

Verification:

```bash
pytest tests/test_report_plan_validator.py
LLM_MODE=mock pytest
```

Review Gate:

- [ ] Phase 6 review：重点检查 Agent grounding、prompt、schema、validator 和 fallback

## Phase 7: Chart and DOCX Rendering

- [x] 实现 `ChartRenderer`
- [x] 生成支付方式分布图
- [x] 生成支付渠道分布图
- [x] 生成停车时长分布图
- [x] 生成入场时间分布图
- [x] 生成收费时间分布图
- [x] 实现 `DocxRenderer`
- [x] 写入报告信息
- [x] 写入六个硬指标
- [x] 插入至少一张真实图表
- [x] 写入支付方式与渠道摘要
- [x] 写入停车时长分析摘要
- [x] 写入补充观察
- [x] 写入结论与建议
- [x] 移除或替换模板占位说明
- [x] 输出 `.docx`

Done Criteria:

- 生成的 Word 文件可以打开
- 报告包含六个硬指标
- 报告包含至少一张真实图表
- 报告不保留未替换的主要占位符
- 图表来自实际数据

Verification:

```bash
LLM_MODE=mock pytest
```

Manual Check:

- [ ] 打开生成的 `.docx`，确认章节、指标、图表、观察和建议可读

Review Gate:

- [ ] Phase 7 review：检查报告完整性、图表真实性、模板占位替换和输出质量

## Phase 8: Observability and Logs

- [x] 实现 JSON lifecycle logger
- [x] 记录 `job_created`
- [x] 记录 `file_saved`
- [x] 记录 `job_claimed_by_worker`
- [x] 记录 `data_validation_started`
- [x] 记录 `data_validation_completed`
- [x] 记录 `metrics_computed`
- [x] 记录 `profiles_computed`
- [x] 记录 `agent_planning_started`
- [x] 记录 `agent_planning_completed`
- [x] 记录 `chart_rendering_started`
- [x] 记录 `docx_generation_started`
- [x] 记录 `job_completed`
- [x] 记录 `job_failed`
- [x] 实现 LLM prompt/response/model/latency logging
- [x] 确保日志不记录 API key
- [x] 确保日志不输出完整原始 CSV
- [x] 生成 sample job log
- [x] 生成 sample LLM log

Done Criteria:

- Docker logs 中可以看到结构化 JSON
- 每次 LLM 调用可追踪 prompt、response、model、latency
- 失败 job 能定位失败步骤
- 日志不包含密钥

Verification:

```bash
docker compose logs api
docker compose logs worker
```

Review Gate:

- [ ] Phase 8 review：检查日志完整性、可调试性和敏感信息泄漏风险

## Phase 9: Frontend

- [x] 实现上传表单
- [x] 支持上传 `.docx` 模板
- [x] 支持上传 `.csv` 数据
- [x] 支持可选领域文件
- [x] 支持可选处理说明
- [x] 提交后显示 `job_id`
- [x] 显示 job 状态
- [x] 支持刷新后查询状态
- [x] completed 后显示下载链接
- [x] failed 后显示错误信息

Done Criteria:

- 用户可以从页面完成上传、查看状态和下载
- UI 简洁，不追求复杂样式
- 页面刷新后仍可通过 job id 查询状态

Verification:

- [x] 浏览器手动测试 upload -> status -> download

Review Gate:

- [ ] Phase 9 review：检查前端主流程、错误状态和最小可用性

## Phase 10: API-Level Test and Test Suite

- [x] 实现 `tests/test_jobs_api.py`
- [x] 测试 `POST /jobs`
- [x] 测试 `GET /jobs/{job_id}`
- [x] 测试 `GET /jobs/{job_id}/download`
- [x] mock 报告生成过程
- [x] 测试不依赖真实 OpenAI API
- [x] 补齐核心单元测试
- [x] 确保 `pytest` 通过

Done Criteria:

- API-level test 覆盖 submit -> status -> download
- 测试可以在无 API key 环境运行
- 核心 deterministic 逻辑有测试

Verification:

```bash
pytest
```

Review Gate:

- [ ] Phase 10 review：检查测试是否覆盖作业要求和关键失败路径

## Phase 11: Template Fidelity Fix

- [x] 将 `DocxRenderer` 改为优先打开用户上传的原 `.docx` 模板
- [x] 保留模板页面设置、标题样式、蓝色章节样式和基础字体
- [x] 识别关键指标三列表格：`指标 / 填写值 / 示例预期值`
- [x] 替换关键指标表格第二列“填写值”，并删除第三列“示例预期值”
- [x] 替换报告信息中的数据周期和生成时间占位
- [x] 替换支付方式与渠道占位段落为 Agent 摘要
- [x] 在图表占位段落位置插入真实图表并移除占位说明
- [x] 替换停车时长分析占位段落为数据摘要
- [x] 替换补充观察占位段落为 2-3 条 observations
- [x] 替换结论与建议占位段落为 2-4 条 recommendations
- [x] 清理未替换的主要占位符，例如 `[ 笔数 ]`、`【占位图`、`【智能体生成`
- [x] 保留或统一中文 East Asia 字体，避免 Word 中文 fallback
- [x] 增加模板保真相关测试：成品仅保留两列、示例预期值被删除、填写值列被替换
- [x] 增加 fallback 日志：模板无法识别时记录原因并回退到标准渲染
- [x] 用真实模板手动打开检查：版式应接近原模板，而不是空白文档式报告

Done Criteria:

- 生成报告视觉结构与用户上传模板基本一致
- 当前停车报告模板可为三列，但生成的成品报告只保留“指标”和“填写值”两列
- 红色占位内容被实际数据或 Agent 内容替换
- 至少一张真实图表插入到模板图表占位附近
- 自动测试覆盖模板表格替换
- 手动打开 `.docx` 后确认模板标题、章节和表格样式基本保留

Verification:

```bash
pytest tests/test_renderers.py
```

Manual Check:

- [x] 打开新生成的 `.docx`，对照原模板确认版式保真

Review Gate:

- [ ] Phase 11 review：检查模板替换准确性、样式保留、fallback 行为和测试覆盖

## Phase 12: Delivery

- [x] 补全 `README.md`
- [x] 说明 mock 模式和真实 OpenAI 模式
- [x] 说明 `.env.example` 使用方式
- [x] 说明 Docker Compose 启动方式
- [x] 说明 API 使用方式
- [x] 说明设计取舍
- [ ] 生成 sample report
- [x] 添加脱敏 sample logs
- [ ] 添加 GPLv3 `LICENSE`
- [x] 检查 `.gitignore`
- [x] 检查 GitHub 仓库不包含 `.env` 或 API key

Done Criteria:

- 面试官可以按 README 运行项目
- 仓库包含 sample generated report
- 仓库包含脱敏 sample logs
- 仓库不包含密钥

Verification:

```bash
pytest
docker compose up --build
```

Review Gate:

- [ ] Final review：面试交付前完整 code review，重点检查需求遗漏、bug、测试、日志、安全和 README

## Code Review Checklist

每次 review 优先检查：

- [ ] 是否满足 `docs/spec.md`
- [ ] 是否符合 `docs/plan.md`
- [ ] 是否符合 `docs/agent_design.md`
- [ ] 六个硬指标是否由 deterministic code 计算
- [ ] Agent 是否只基于 facts 做报告规划
- [ ] `source_fact_ids` 是否可校验
- [ ] LLM prompt/response/model/latency 是否记录
- [ ] 上传文件和输出文件路径是否安全
- [ ] `.env` 和 API key 是否未泄漏
- [ ] API-level test 是否覆盖 submit -> status -> download
- [ ] README 是否足够让面试官运行
