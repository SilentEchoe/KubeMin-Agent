# KubeMin-Agent P0+P1 重构实施文档

## 1. 目标

本次重构以 ControlPlane 主链路为核心，完成以下目标：

- 文档与实现一致：配置口径、架构状态、模块清单一致。
- 工具安全与正确性提升：修复高风险行为与执行语义漏洞。
- 工程基线可回归：`ruff` 与 `pytest` 全绿，最小 CI 可运行。
- 执行链路收敛：彻底移除 legacy AgentLoop，仅保留 ControlPlaneRuntime。
- 结构可维护：对 Scheduler 做内部解耦，保持外部行为兼容。

## 2. 执行顺序（唯一实施顺序）

1. 基线提交（快照当前工作区）
2. 新增本实施文档（当前步骤）
3. P0-1 文档与配置一致性修复
4. P0-2 工具正确性修复（Browser/KubeMinCli/Kubectl）
5. P0-3 Shell 安全边界收紧
6. P0-4 Chroma 稳定性与测试修复
7. P0-5 CI 与 Lint 债务清理
8. P1-1 移除 legacy 执行链路
9. P1-2 Scheduler 内部解耦重构
10. 收尾文档同步与变更日志更新

禁止跳步执行；每步完成后必须提交一个独立 commit。

## 3. 每步验收标准

### 3.1 P0-1 文档与配置一致性

- 所有用户向文档中的配置文件路径统一为 `~/.kubemin-agent/config.json`。
- 架构文档中的“规划中/已实现”状态与代码一致。
- 设计文档中的失效模块引用（如不存在的工具模块）被修正。

### 3.2 P0-2 工具正确性

- `BrowserTool` 去除死代码分支，返回路径一致且可审计。
- `KubeMinCliTool` 执行命令前强制归一化为 `kubemin-cli ...`。
- `KubectlTool` 支持多词只读子命令识别（如 `config view`）。
- 对应单测补齐并通过。

### 3.3 P0-3 Shell 安全边界

- 默认 allowlist 收紧，移除高风险解释器/包管理/构建入口。
- 保留并验证 `off/best_effort/strict` 沙箱语义不回退。
- 相关 shell 工具测试通过。

### 3.4 P0-4 Chroma 稳定性

- `ChromaDBBackend` 增加可测试 embedding 注入点（默认行为不变）。
- `tests/test_memory_chroma.py` 稳定通过，不依赖 ONNX 临时目录行为。

### 3.5 P0-5 CI + Lint

- 新增最小 CI 工作流：至少包含 `ruff check` 与 `pytest`。
- `ruff check kubemin_agent tests` 结果为 0 问题。

### 3.6 P1-1 移除 legacy 执行链路

- 删除 `agent/loop.py`、`agent/context.py`、`agent/subagent.py`。
- CLI/Gateway 不再包含 legacy fallback 分支，仅走 ControlPlaneRuntime。
- 删除或修正 legacy 相关配置项/显示项与测试。

### 3.7 P1-2 Scheduler 解耦

- 新增内部模块：`IntentPlanner`、`PlanExecutor`、`ExecutionReporter`。
- `Scheduler` 作为 façade 保持现有对外接口与调用语义。
- 原有审计、校验、评估链路行为保持兼容。
- 调度回归测试通过。

### 3.8 收尾文档同步

- `docs/arch-*.md` 与 `docs/design-and-implementation-plan.md` 反映重构后真实状态。
- 各文档补充本次变更日志条目。

## 4. 提交与回滚策略

- 每个子任务一个 commit，不合并。
- commit 必须可独立回滚，不跨多个主题。
- 若某步引入回归，必须在该步内修复后再进入下一步。
- 回滚优先使用 `git revert <commit>`，禁止破坏性重置共享历史。

## 5. Commit 映射

1. `chore(baseline): snapshot pre-refactor workspace state`
2. `docs(refactor): add implementation roadmap for p0-p1`
3. `docs: align config and architecture docs with current implementation`
4. `fix(tools): harden browser/kubemin-cli/kubectl execution semantics`
5. `refactor(shell): tighten default allowlist and keep sandbox semantics`
6. `fix(memory): stabilize chroma backend tests via deterministic embedding path`
7. `chore(ci): add quality gates and clear ruff violations`
8. `refactor(runtime): remove legacy agentloop path and converge on control plane`
9. `refactor(scheduler): split planner executor reporter while preserving contracts`
10. `docs: sync architecture docs after p0-p1 refactor rollout`

## 6. 最终总验收

在第 10 步提交前，必须满足：

- `ruff check kubemin_agent tests` 通过。
- `pytest -q` 通过。
- CLI 冒烟：`agent`、`status`、`gateway` 可完成启动级校验（不要求外部通道可用）。
