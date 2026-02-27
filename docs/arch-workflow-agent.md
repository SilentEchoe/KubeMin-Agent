# WorkflowAgent 架构文档

## 设计理念

KubeMin 的核心能力是通过 Workflow YAML 编排应用部署。WorkflowAgent 将 **自然语言转化为可执行的 Workflow 定义**, 降低用户编写 YAML 的门槛, 同时确保生成内容的正确性。

设计原则:
- 生成的 YAML 严格遵循 KubeMin Workflow 规范
- 自动处理步骤依赖关系
- 内置资源限额和健康检查的最佳实践

## 架构

```
WorkflowAgent (extends BaseAgent)
  |
  +-- system_prompt: KubeMin Workflow 规范专家
  +-- ToolRegistry
       +-- WorkflowCRUDTool    (规划中: 创建/读取/更新 Workflow)
       +-- WorkflowValidateTool(规划中: YAML 校验)
```

调度路径:

```
用户消息 -> Scheduler -> WorkflowAgent -> 生成/优化 YAML -> Validator 校验 -> 返回
```

## 功能清单

| 功能 | 状态 | 说明 |
|------|------|------|
| 中控调度接入 | 已实现 | 通过 ControlPlaneRuntime 注册到 AgentRegistry, 由 Scheduler 调度 |
| 执行轨迹摘要 | 已实现 | 在工具调用前后产出 `reasoning_step` 结构化执行摘要 |
| 在线质量评估 | 已实现 | Scheduler 执行后写入 `evaluation` 审计事件 |
| 自然语言生成 Workflow YAML | 已实现 | 通过 LLM 将用户描述转为 YAML |
| 步骤依赖优化 | 已实现 | 自动分析和优化步骤执行顺序 |
| YAML 校验 | 规划中 | 结构性校验 Workflow 配置 |
| 执行状态监控 | 规划中 | 查看 Workflow 执行进度 |
| 失败根因分析 | 规划中 | 分析 Workflow 执行失败原因 |
| Trait 配置 (Scaling/Ingress) | 已实现 | system prompt 中包含 Trait 配置指导 |

## 安全约束

- 生成的 YAML 必须通过 Validator 校验
- 资源限额 (CPU/Memory) 不得超过平台配置上限
- 不直接执行 apply, 只生成 YAML 供用户审核

## 工具集

| 工具 | 状态 | 用途 |
|------|------|------|
| ReadFileTool | 已实现 | 读取现有 Workflow YAML 文件 |
| WriteFileTool | 已实现 | 写出生成的 Workflow YAML |
| YAMLValidatorTool | 已实现 | YAML 语法 + KubeMin 结构校验 (apiVersion/kind/metadata/spec/components) |

## 技术取舍

| 决策 | 理由 | 备选方案 |
|------|------|----------|
| LLM 生成而非模板填充 | 模板难以覆盖所有场景, LLM 更灵活 | 参数化模板 (放弃: 扩展性差) |
| 只生成不执行 | 用户审核后再 apply 更安全 | 自动 apply (放弃: 误操作风险) |
| system prompt 内置规范 | 规范变化频率低, 免去额外文件加载 | 运行时加载规范文件 (放弃: 增加复杂度) |
| 结构化轨迹而非完整思维链 | 提升调试可观测性且避免泄露完整推理 | 记录完整 CoT (放弃: 风险高) |

## 变更日志

| 日期 | 变更 | 原因 |
|------|------|------|
| 2026-02-27 | 接入在线评估与 `reasoning_step` 结构化轨迹 | 提升 YAML 生成任务质量评估能力 |
| 2026-02-26 | 实现 ReadFileTool + WriteFileTool + YAMLValidatorTool | MVP 工具集 |
| 2026-02-26 | 接入中控运行时, 默认经 Scheduler 调度 | 落地 Agent Control Plane 主链路 |
| 2025-02 | 初始设计, 定义 YAML 生成和 Trait 配置能力 | 项目初始化 |
