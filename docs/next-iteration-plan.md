# KubeMin-Agent 持续推进计划（2026-02-28）

## 1. 目标

基于当前仓库实现状态，明确后续可持续推进的工作包，形成可执行、可验收、可追踪的迭代计划。

## 2. 当前状态快照（As-Is）

### 2.1 已落地能力

- Control Plane 主链路已可用：`ControlPlaneRuntime -> Scheduler -> SubAgent -> Validator -> Audit`。
- 多任务编排已支持：`sequential` / `parallel` / `depends_on`。
- 在线评估与执行轨迹已接入：`reasoning_step` + `evaluation`。
- 三个默认子 Agent（`general`/`k8s`/`workflow`）及最小工具集已注册。
- 动态上下文预算（替代固定历史窗口）已在 control 与 legacy 链路收敛。

### 2.2 关键缺口

1. **M4 通道接入未完成（P0）**
- `channels/` 仅有 `base.py` 与 `manager.py`，缺少 Telegram 等 IM 实现。
- `gateway` 文档注释写有 `cron + heartbeat`，但运行任务仅启动 runtime/bus/channels。

2. **M5 长运行编排未闭环（P0）**
- `CronService` 与 `HeartbeatService` 已存在，但未接入 `gateway` 主循环。
- `SubagentManager` 已实现，但仅在 `AgentLoop` 初始化，未进入实际调度路径。

3. **上下文工程 M3-M5 仍待建设（P1）**
- 工具输出仍以硬截断为主（`browser.py` / `content_audit.py`），未实现语义摘要层。
- 跨 Agent 上下文传递对象（如 `control/agent_context.py`）尚不存在。
- 记忆检索虽有接口，但 control 主链路未注入查询驱动记忆。

4. **稳定性与测试基线仍有缺口（P0）**
- 当前 `pytest -q` 结果：`122 passed, 2 failed`，失败集中在 `tests/test_memory_chroma.py`（ONNX/Chroma 运行环境兼容）。
- 覆盖率总计约 `73%`，`channels/`、`subagent`、`browser/content_audit`、`standalone` 覆盖偏低。
- 测试存在若干 RuntimeWarning（AsyncMock 未 await），影响 CI 噪音与可信度。

5. **文档一致性风险（P0）**
- 设计文档已将 Cron/Heartbeat 打通列为下一步，但代码链路尚未实现。
- 部分 Agent 架构文档的“规划中”项与代码现状存在偏差，需要同步校准。

## 3. 优先级排序

| 优先级 | 主题 | 原因 |
|---|---|---|
| P0 | 稳定性基线（测试可通过 + CI） | 当前主分支无法全绿，影响后续迭代可信度 |
| P0 | 通道与长期运行闭环（M4/M5） | 已有模块但未打通，业务价值最高 |
| P1 | 上下文工程 M3-M5 | 直接影响复杂任务质量与成本 |
| P1 | 文档一致性治理 | 项目采用 Docs-First，必须保证文档即真相 |
| P2 | GameAudit 与 Control Plane 深度整合 | 非主链路刚需，可在主链路稳定后推进 |

## 4. 分阶段实施计划

### 阶段 A（第 1 周，P0）：稳定性收敛

**目标**：恢复主分支“可回归、可验证”。

**任务包**：
- A1. 修复 Chroma 后端测试稳定性
  - 为 `ChromaDBBackend` 增加测试友好策略（可注入 embedding function / 失败回退），避免 ONNX 临时目录依赖导致 CI 波动。
- A2. 清理测试 RuntimeWarning
  - 对 `kill/terminate/write` 等调用增加同步/异步兼容封装或修正测试 mock 约定。
- A3. 建立 CI 基线
  - 增加最小 CI：`ruff + mypy + pytest`。

**验收**：
- `pytest` 全绿（0 fail）。
- 无新的高优先级 RuntimeWarning。
- CI 工作流可在 PR 上自动执行。

### 阶段 B（第 2-3 周，P0）：M4/M5 主链路打通

**目标**：补全“可运行中控”的缺口。

**任务包**：
- B1. 实现 TelegramChannel（至少文本收发 + allowlist）
  - 新增 `kubemin_agent/channels/telegram.py` 与单测。
- B2. 接入 Cron/Heartbeat 到 gateway
  - `gateway` 启动时并行运行：runtime、bus outbound、channel manager、cron service、heartbeat service。
  - Cron/Heartbeat 回调统一走 `ControlPlaneRuntime.handle_message()`。
- B3. 增加 Cron CLI 管理命令
  - `cron add/list/remove`，并支持 `every/cron/at`。

**验收**：
- Telegram 能触发消息入队并回包。
- 定时任务可新增/执行/删除。
- Heartbeat 文件触发可进入统一控制面并生成响应。

### 阶段 C（第 4-5 周，P1）：上下文工程 M3-M5 落地

**目标**：提高复杂任务质量与上下文效率。

**任务包**：
- C1. 工具结果语义摘要层
  - 新增 `agent/tools/summarizer.py`，在 `browser_action` 与 `audit_content` 大输出路径接入。
- C2. 跨 Agent 上下文对象
  - 新增 `control/agent_context.py`（`ContextEnvelope`），由 `Scheduler` 在依赖任务间传递结构化发现。
- C3. 查询驱动记忆注入
  - 由任务描述驱动 memory recall，再进入上下文预算组装；同时补齐 `file/jsonl/chroma` 后端一致性测试。

**验收**：
- 大输出场景上下文长度下降，关键错误召回不下降。
- `depends_on` 链路中重复工具调用明显减少。
- 记忆命中率与任务可执行性提升（通过离线样例对比）。

### 阶段 D（第 6 周，P1）：文档与发布基线

**目标**：确保 Docs-First 与发布可维护性。

**任务包**：
- D1. 同步更新 `docs/design-and-implementation-plan.md` 的状态段（新增 2026-02-28 快照）。
- D2. 对齐 `docs/arch-*.md` 功能状态，消除“规划中/已实现”偏差。
- D3. 产出运行手册与故障排查手册（M6 要求）。

**验收**：
- 文档状态与代码一致。
- 新成员可按手册完成本地启动、故障定位、回归执行。

## 5. 建议的立即启动项（本周）

1. 先完成阶段 A（测试与 CI），确保主干稳定。
2. 紧接阶段 B 打通 gateway + cron/heartbeat（当前业务收益最大）。
3. 稳定后进入阶段 C 的上下文工程优化。

## 6. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| Chroma/ONNX 环境差异导致 CI 波动 | 回归不可重复 | 引入可注入 embedding / 测试回退机制 |
| 通道接入引入并发复杂度 | 网关稳定性下降 | 增加集成测试与退出流程（stop/cancel）验证 |
| 上下文摘要过度压缩 | 任务质量下降 | 引入关键字段白名单 + A/B 对比评估 |
| 文档滞后 | 决策依据失真 | 每阶段交付强制包含文档更新 checklist |

## 7. 变更日志

| 日期 | 变更 |
|---|---|
| 2026-02-28 | 新增持续推进计划，基于代码与测试现状形成阶段性路线图 |
