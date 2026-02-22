# KubeMin-Agent（CLI）生产级 Agent：技术架构与实现路径（2026 主线 Job）

> 目标：在 **KubeMin-Cli 可控信息域** 内构建一个 **生产级只读诊断 Agent（CLI）**，以「可观测、可复盘、可评估、可治理、可演进」为工程标准；并在实现过程中系统理解大模型（LLM）的能力边界、工具调用机制、RAG、评估与推理系统工程。

---

## 0. 范围与非目标

### 0.1 Scope（第一阶段：Read-Only）
- CLI 形式：`kubemin-agent`
- 数据域：**仅通过 KubeMin-Cli / KubeMin API** 获取信息（避免直连 K8s / Prom / Loki 等外部系统）
- 核心证据源（v1）：Pods 资源摘要 / Logs / Prometheus 指标
- 输出：结构化诊断报告（JSON + Human-friendly）
- 约束：**不做任何集群变更**（只读），不做自动修复执行

### 0.2 Non-Goals（v1 明确不做）
- 不进行写操作（patch/deploy/scale/restart）与自动修复
- 不做多 Agent 群体协作（multi-agent）与长程记忆（long-term memory）
- 不依赖用户交互式确认流程（仅在 CLI 提示用户补充参数或选择 pod）

---

## 1. 北极星用例（North Star Use Cases）

1) **应用不稳定/频繁重启**：定位 CrashLoopBackOff / OOMKilled / 探测失败 / 依赖异常  
2) **性能退化**：CPU/Memory 飙升、throttling、延迟上升、错误率上升  
3) **发布后故障**：从事件、日志与指标还原故障链路并给出可执行建议  
4) **审计与复盘**：每一次诊断都可回放 run_id，包含工具调用与证据链

---

## 2. 企业级目标（SLO/SLI 与工程质量门禁）

### 2.1 质量属性（Quality Attributes）
- **可靠性**：失败可解释、失败可分类、重试可控、输出稳定
- **安全性**：只读权限、工具 allowlist、敏感信息脱敏、最小暴露
- **可观测性**：每次运行可追踪（trace_id/run_id），工具调用与 LLM 调用均可审计
- **可评估性**：离线 case 回归 + 指标体系；上线前质量门禁
- **成本可控**：token 预算、日志截断、指标限窗、缓存与分级模型路由
- **可演进性**：接口/Schema 版本化，prompt 版本化，工具可插拔

### 2.2 建议 SLO（可按实际调整）
- CLI 单次诊断（v1）P95 < 12s（不含用户网络极端情况）
- 失败率 < 2%（不含权限与输入错误）
- 结构化输出校验通过率 > 99%（Pydantic/JSON Schema）

---

## 3. 总体架构（Enterprise Architecture）

### 3.1 分层架构（强约束）
```
┌─────────────────────────────┐
│ CLI (Typer/Rich)            │  输入/参数/格式化输出
└──────────────┬──────────────┘
               │
┌──────────────▼──────────────┐
│ Orchestrator (State Machine) │  plan→execute→verify→report
│ - budget / retry / timeout   │  token与工具预算、失败治理
│ - run_store / replay         │  可复盘（证据链）
└──────────────┬──────────────┘
               │
┌──────────────▼──────────────┐
│ Tool Runtime (Allowlist)     │  仅允许工具集合
│ - kubemin: pods/logs/prom    │  统一经KubeMin-Cli域
│ - telemetry + rate limit     │  超时/限流/断路器
└──────────────┬──────────────┘
               │
┌──────────────▼──────────────┐
│ Model Gateway (LLM)          │  模型路由/缓存/回退
│ - schema-enforced outputs    │  JSON schema + repair
│ - prompt versioning          │  prompts/v1,v2…
└──────────────┬──────────────┘
               │
┌──────────────▼──────────────┐
│ Evaluation & Governance      │  case回归/质量门禁/ADR
│ - offline eval + metrics     │  命中率/证据率/误报率
│ - release checklist          │  企业级上线清单
└─────────────────────────────┘
```

### 3.2 核心原则（生产级分水岭）
- **证据链优先**：结论必须引用工具输出；无证据 → `unknown`/低置信度
- **固定状态机**：v1 不做“自由发挥多步推理”，用强约束流程降低漂移
- **工具输出结构化**：工具负责把“事实”变成结构化 JSON；LLM负责组织解释与建议
- **预算与限流**：工具调用次数、日志行数、指标时间窗、token 使用都必须可控

---

## 4. CLI 产品形态

### 4.1 命令与参数（v1）
- `kubemin-agent inspect --app <appId> -n <namespace> "<query>"`
- `kubemin-agent inspect --pod <podName> -n <namespace> "<query>"`
- `kubemin-agent replay --run <run_id>`
- `kubemin-agent eval --suite minimal`
- 输出控制：`--json` / `--format human|json` / `--out <file>`

### 4.2 配置（~/.kubemin-agent/config.yaml）
- KubeMin API endpoint、token、默认 namespace
- 默认预算：最大工具调用次数、日志行数、prom 时间窗与 step
- 数据脱敏策略开关（例如隐藏邮箱/手机号/密钥片段）

---

## 5. 工具系统（Tools）与 KubeMin-Cli 集成

> 强制要求：**所有数据读取通过 KubeMin-Cli 的 API 代理层**，确保权限、审计与结构治理。

### 5.1 工具清单（v1）
#### Tool A：GetPodsSummary（按 appId / selector）
**Input**
```json
{ "appId":"string", "namespace":"string", "selector":"string? "}
```
**Output（示例字段）**
- pods[].name / phase / ready / restarts / ageSeconds / node
- containers[].state / reason / lastExitCode / lastFinishedAt
- events[]（Warning/Normal 聚合：reason,count,lastTimestamp,message摘要）

#### Tool B：GetPodLogs（截断）
**Input**
```json
{ "namespace":"string", "pod":"string", "container":"string?", "tailLines":200, "sinceSeconds":1800 }
```
**Output**
- lines[]：尽量结构化（ts/level/msg），不可则 raw
- truncated: bool（必须）

#### Tool C：PromQuery（Instant 或 Range）
**Input**
```json
{ "expr":"string", "start":"RFC3339?", "end":"RFC3339?", "stepSeconds":30? }
```
**Output**
- series[]：metric labels + values[]
- partial: bool（例如超时/截断）

### 5.2 KubeMin API 建议（只读端点）
建议在 KubeMin-Cli/Server 增补或复用如下 read-only endpoints：
- `GET /api/v1/observability/pods?namespace=&appId=`
- `GET /api/v1/observability/pods/{pod}/logs?container=&tailLines=&sinceSeconds=`
- `GET /api/v1/observability/prom/query?expr=...`（或 range）

**企业级要求**
- RBAC：按 tenant/namespace/appId 授权
- 审计：记录每次查询的 run_id、用户、资源范围
- 速率限制：避免 CLI 扫爆 API/Prom
- 输出规范：响应字段稳定、版本化

---

## 6. Orchestrator：固定状态机（v1）

### 6.1 状态机定义
1) **Plan**
- 输入：用户 query + appId/namespace
- 输出：严格 JSON plan（工具调用清单、预算、时间窗、优先级）

2) **Execute**
- 严格按 plan 调用工具（allowlist）
- 每次调用：timeout/retry（指数退避）/ error classify
- 所有原始结果写入 run_store

3) **Verify**
- 规则引擎优先（强信号）：CrashLoopBackOff、OOMKilled、ImagePullBackOff、Pending（资源不足）等
- LLM 负责把证据组织为解释与建议；禁止新造事实

4) **Report**
- 输出结构化报告（JSON schema）
- human 输出生成（摘要、重点、建议命令）

### 6.2 预算策略（Budget）
- 最大工具调用次数：默认 6
- 日志：默认 200 行 / 30 分钟；必要时允许二次拉取但必须计入预算
- Prom：默认 30 分钟窗口，step 30s；必要时扩窗需用户显式 `--window`

---

## 7. 报告 Schema（企业级结构化输出）

### 7.1 Report JSON（建议 v1）
```json
{
  "runId":"uuid",
  "input":{"query":"string","appId":"string","namespace":"string"},
  "summary":{"severity":"S0|S1|S2|S3","headline":"string","topFindings":["string"]},
  "issues":[
    {
      "id":"ISSUE-1",
      "title":"string",
      "severity":"S0|S1|S2|S3",
      "hypothesis":"string",
      "evidence":[{"source":"pods|events|logs|prom","ref":"string","value":"string"}],
      "recommendations":[
        {"action":"string","commands":["string"],"confidence":0.0}
      ]
    }
  ],
  "metrics":[{"name":"string","expr":"string","highlights":["string"]}],
  "toolCalls":[{"tool":"string","ok":true,"latencyMs":1234,"errorType":"string?"}],
  "limits":{"logTruncated":true,"promPartial":false},
  "meta":{"promptVersion":"v1","model":"string","tokenUsage":{"input":0,"output":0}}
}
```

### 7.2 Severity 建议
- S0：无问题/信息不足
- S1：影响可用性（崩溃/无法启动/严重错误率）
- S2：影响性能/稳定性（频繁重启、资源接近上限）
- S3：轻微风险/建议优化

---

## 8. 模型网关（Model Gateway）与 Prompt 工程

### 8.1 强制 Schema（必须）
- 所有 LLM 输出必须通过 Pydantic/JSON Schema 校验
- 校验失败：自动 repair 一次（提示“仅修复 JSON 格式，不改语义”）
- 仍失败：降级输出（仅规则引擎报告 + 标记 `llmFailed=true`）

### 8.2 Prompt 版本化（企业级要求）
- prompts/v1：固定状态机 + 输出 schema
- prompts/v2：加入 RAG 引用、更多指标模板
- 每次发布必须记录：promptVersion、模型、参数、变更说明（ADR）

### 8.3 成本与稳定性建议
- 温度：偏低（0~0.3）以提升一致性
- 采用“先计划后执行”的两段调用，减少上下文噪音
- 日志与 Prom 先做摘要再喂给 LLM（必要时由规则/模板摘要）

---

## 9. 评估体系（Evals）：企业级上线门禁

### 9.1 指标（v1 必须）
- **Issue 命中率**：是否识别正确类别（CrashLoop/OOM/ImagePull）
- **证据充分率**：每个结论是否有证据引用（evidence coverage）
- **误报率**：Running 正常却输出严重故障的比例
- **成本**：平均工具调用次数、平均 token、平均时延

### 9.2 最小回归用例（5 条）
- CrashLoopBackOff（panic/config缺失）
- OOMKilled（exit 137 + memory near limit）
- ImagePullBackOff（unauthorized/not found）
- High CPU（cpu usage high，可能 throttling）
- Error burst（日志 5xx 激增 + 指标错误率上升）

### 9.3 Eval Runner 设计
- 用 mock tool 输出（稳定可复现）
- 输出评分报告：pass/fail + 失败原因（证据缺失/分类错误/格式错误）

---

## 10. 安全与治理（Enterprise Security & Governance）

### 10.1 访问控制
- CLI 使用 KubeMin token（短期 token 或 OAuth）
- KubeMin 侧 RBAC：按 tenant/namespace/appId 约束
- 工具 allowlist：只允许 3 个只读工具（v1）

### 10.2 数据保护
- run_store 默认本地存储：仅存诊断必要信息
- 敏感信息脱敏：
  - logs：疑似 token/secret 的内容用正则遮罩
  - headers：不记录 Authorization
- 可配置 retention：默认保留 7 天或 200 runs

### 10.3 审计与合规
- 记录每次 run 的资源范围：namespace/appId/pod
- 工具调用日志：时间、参数摘要（脱敏）、结果摘要、错误类型

---

## 11. 运行与可观测性（Observability）

### 11.1 Telemetry（v1 推荐）
- 每次运行：run_id、start/end、总耗时、工具耗时、LLM耗时
- 关键指标：
  - tool_call_latency_ms{tool}
  - tool_call_error_total{tool,errorType}
  - llm_tokens{input,output}
  - report_schema_validation_failed_total

### 11.2 可复盘（Replay）
- `replay --run <id>` 从 run_store 读取原始证据与最终报告
- 用于：排查“为什么模型这么说”、回归对比、审计

---

## 12. 代码结构与实现建议（Python 起步，企业级工程化）

### 12.1 推荐技术栈
- CLI：Typer + Rich
- Schema：Pydantic
- HTTP：httpx（带 timeout/retry）
- 配置：pydantic-settings / yaml
- 日志：structlog 或标准 logging + json formatter
- 测试：pytest
- 可观测：OpenTelemetry（可选 v2）

### 12.2 目录结构（建议）
```
kubemin_agent/
  cli.py
  config.py
  runtime/orchestrator.py
  runtime/run_store.py
  runtime/budget.py
  runtime/errors.py
  tools/base.py
  tools/kubemin_api.py
  tools/prom.py
  model/gateway.py
  model/prompts.py
  model/schemas.py
  eval/runner.py
  eval/scoring.py
```

---

## 13. 分阶段实现路径（详细任务清单）

> 交付策略：每个阶段都必须“可运行、可回放、可评估”。  
> 每个阶段的产出至少包含：代码 + 文档（ADR/变更说明）+ 回归用例更新。

### Phase 0（第 0 周）：准备与边界固化
**目标**：把“生产级约束”在第一天写进骨架，避免后期返工。

任务：
1. 定义 CLI 命令与配置文件格式
2. 定义 tool allowlist 与输入输出 schema
3. 定义 report JSON schema（版本化：v1）
4. 定义 run_store 格式与目录（含脱敏策略）
5. 定义最小 eval suite（5 条）与评分指标

交付物：
- `README.md` + `docs/architecture.md`（可合并入本文件）
- `cases_minimal.yaml`
- `report_schema_v1.json`

---

### Phase 1（Week 1）：MVP（Pods + Logs + 报告闭环）
**目标**：不依赖 Prom 也能诊断 60% 常见故障；做到可复盘。

任务与实现：
1) **run_store**
- 实现：`runs/<run_id>/input.json`、`toolcalls/*.json`、`report.json`
- 要点：脱敏；控制体积；保留原始响应摘要

2) **Tools：GetPodsSummary / GetPodLogs**
- 实现：通过 KubeMin API 访问（httpx，统一 timeout=3~5s）
- 要点：日志截断；错误分类（auth/timeout/notfound）

3) **Orchestrator：固定 plan→execute→report**
- v1 plan 可以是“模板计划”（先不调用 LLM 生成 plan）
- report 采用“规则引擎 + LLM 解释”组合

4) **JSON schema 校验与 repair**
- Pydantic 校验 report；失败则重试一次修复格式

5) **Human 输出**
- 摘要：top findings、严重度
- 表格：pods 状态、重启次数、关键事件
- 建议：可复制命令（经 KubeMin 代理或提示 kubectl）

交付门禁：
- 5 条 minimal suite 至少通过 3 条
- schema 校验通过率 > 95%

---

### Phase 2（Week 2）：Prometheus 接入 + 指标模板
**目标**：把“性能与容量类问题”纳入证据链。

任务与实现：
1) PromQuery 工具（Instant → Range）
- 实现：KubeMin Prom proxy；固定默认窗口（30m）
- 限制：窗口、step、最大 series 数量

2) 指标模板（强烈建议从模板开始）
- CPU：`rate(container_cpu_usage_seconds_total{...}[5m])`
- Memory：`container_memory_working_set_bytes{...}`
- Restart：从 pods summary 已有
- 错误率（如有）：`sum(rate(http_requests_total{code=~"5.."}[5m]))`

3) 报告增强：metrics[] + highlights
- 把指标转成自然语言摘要（峰值、趋势、异常点）

交付门禁：
- minimal suite 通过率 ≥ 80%
- 平均工具调用次数 ≤ 6
- 平均 token/报告 ≤ 设定预算（例如 8k）

---

### Phase 3（Week 3–4）：证据链与 RAG（可选但推荐）
**目标**：建议不再“泛泛而谈”，而是引用你自己的 runbook/故障库。

任务与实现：
1) 知识库构建（本地优先）
- 输入：KubeMin 文档、故障处理手册、SOP
- 方案：向量检索（FAISS/Chroma）或 BM25（小规模足够）
- 输出：检索到的片段必须带引用 id

2) 报告中加入 citations
- recommendations 中加入 “依据：runbook#xxx”

交付门禁：
- 建议的可执行性评分提升（人工抽检）
- 引用覆盖率：至少 50% 的建议能引用内部知识

---

### Phase 4（Week 5–6）：可靠性工程（像中间件一样做 Agent）
**目标**：把失败治理做扎实，才能真正“企业级”。

任务与实现：
1) 工具层可靠性
- timeout、retry、限流、断路器（简单实现即可）
- 错误分类：UserError/AuthError/Timeout/UpstreamError/SchemaError

2) 并发控制
- 同一 run 内 tool calls 并发上限（例如 2）
- 避免 Prom 与 Logs 同时大量请求

3) 缓存与复用
- 相同参数工具调用可缓存（run 内缓存 + 可选磁盘缓存）

交付门禁：
- 在模拟网络抖动下仍可输出降级报告
- 失败可解释（errorType + next action）

---

### Phase 5（Week 7–8）：计划生成与验证（Plan→Execute→Verify 完整形态）
**目标**：引入 LLM 生成 plan，但仍保持可控。

任务与实现：
1) LLM 生成 plan（严格 JSON）
- plan 字段：pod 选择策略、日志窗口、prom expr 模板选择
- plan 必须可校验，否则回退默认计划

2) Verify 阶段增强
- 规则校验：结论与证据一致性（简单一致性检查）
- 对“高风险结论”要求更多证据或降低 confidence

交付门禁：
- 同一输入重复运行结果一致性提升（低温度 + plan 固化）
- 误报率下降

---

### Phase 6（Week 9–10）：评估体系规模化（企业级核心资产）
**目标**：把质量变成数字，把发布变成门禁。

任务与实现：
1) case 扩展到 50–100
- 覆盖：探测失败、DNS、依赖超时、权限、资源不足、节点压力
2) 自动评分 + 人工抽检结合
3) 回归门禁：不达标禁止发布

交付门禁：
- 关键类别命中率 ≥ 90%（按你设定）
- 证据覆盖率 ≥ 95%

---

### Phase 7（Week 11–12）：发布与运维形态
**目标**：CLI 可在团队内分发与升级，具备可观测与成本控制。

任务与实现：
1) 打包分发
- pipx / homebrew / 单文件二进制（pex/pyinstaller）任选
2) 版本策略与变更日志
- semver；prompt/schema/tool 变更必须写变更说明
3) 可观测与审计对接
- 输出 trace_id；KubeMin 侧审计可串联 run_id

交付门禁：
- 发布 checklist 完整通过（见附录）

---

## 14. 后续演进（6–12 个月路线）

### 14.1 从只读到可控写操作（需要强治理）
- 引入 “Plan → Human Approve → Execute Change”
- 写操作必须：
  - 变更预览（diff）
  - 双人审批（可选）
  - 完整审计
  - 回滚策略

### 14.2 从 CLI 到平台化
- 将 orchestrator 与 tools 抽成服务
- CLI 变薄，服务端统一治理与缓存
- 与 KubeMin 工作流引擎结合：诊断→生成修复 workflow（但需审批）

---

## 15. 企业级发布清单（Release Checklist）

### 15.1 安全
- [ ] 工具 allowlist 生效，默认拒绝未知工具
- [ ] RBAC 校验通过（无权资源不可读）
- [ ] 日志脱敏策略开启且测试覆盖
- [ ] 不记录敏感 header/token

### 15.2 可靠性
- [ ] 所有工具有 timeout/retry
- [ ] 降级策略存在：LLM 失败可输出规则报告
- [ ] run_store 可回放

### 15.3 评估
- [ ] minimal suite 100% 通过
- [ ] 扩展 suite 达到门禁指标
- [ ] schema 校验失败率 < 1%

### 15.4 可观测与成本
- [ ] 输出 token/耗时/工具调用统计
- [ ] 默认预算限制生效（logs/prom/tool calls）
- [ ] 缓存策略验证有效

---

## 16. 附录：推荐 ADR 模板（用于企业级决策记录）

**ADR-xxx：选择 CLI 作为 v1 形态**  
- Context：需要快速评估与回归  
- Decision：CLI + run_store + eval harness  
- Consequences：易迭代，后续可演进到服务端

**ADR-yyy：只通过 KubeMin 域访问 K8s/Prom/Logs**  
- Context：权限/审计/治理  
- Decision：所有数据经 KubeMin API  
- Consequences：需要增补 read-only endpoints，但长期收益巨大

---

## 17. 你可以立刻执行的落地顺序（建议）

1) Phase 0：schema + run_store + eval suite（一天内）
2) Phase 1：pods+logs 闭环（3~5 天）
3) Phase 2：prom 接入（2~3 天）
4) Phase 3+：再逐步加 RAG、可靠性与规模化评估

---

**文档版本**：v1（2026-01-30）  
**适用对象**：KubeMin-Cli 团队内部生产级 Agent 项目  
