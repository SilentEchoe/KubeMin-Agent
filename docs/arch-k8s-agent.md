# K8sAgent 架构文档

## 设计理念

KubeMin 生态以 Kubernetes 为核心, 需要一个专职的 Agent 来处理集群查询和诊断任务。K8sAgent 定位为 **只读诊断专家** -- 只观察、不修改, 确保安全性的同时提供全面的集群可见性。

选择只读策略的原因:
- Agent 的 LLM 推理不可预测, 赋予写权限风险过高
- 诊断场景占日常运维 80% 以上的需求
- 变更操作通过 WorkflowAgent 的 YAML 编排更可控

## 架构

```
K8sAgent (extends BaseAgent)
  |
  +-- system_prompt: 只读约束 + K8s 专业知识
  +-- ToolRegistry
       +-- KubectlTool     (规划中: kubectl get/describe/logs)
       +-- KubeMinAPITool  (规划中: KubeMin 平台 API)
```

调度路径:

```
用户消息 -> Scheduler (LLM 意图分析) -> K8sAgent -> 工具调用 -> 结果返回
```

## 功能清单

| 功能 | 状态 | 说明 |
|------|------|------|
| 中控调度接入 | 已实现 | 通过 ControlPlaneRuntime 注册到 AgentRegistry, 由 Scheduler 路由 |
| 执行轨迹摘要 | 已实现 | 在工具调用前后产出 `reasoning_step` 结构化执行摘要 |
| 在线质量评估 | 已实现 | Scheduler 执行后写入 `evaluation` 审计事件 |
| 跨任务上下文继承 | 已实现 | 支持接收 Scheduler 下发的 `ContextEnvelope`，复用依赖任务发现 |
| 查询驱动记忆注入 | 已实现 | 按当前任务 query 召回 MemoryStore 并注入上下文 |
| 集群资源查询 | 规划中 | 查询 Pod/Deployment/Service 等资源状态 |
| 容器日志查看 | 规划中 | 按 Pod/Container 查看日志 |
| 故障诊断 | 规划中 | 分析 Pod 状态异常、重启原因等 |
| K8s 概念解答 | 已实现 | 通过 system prompt 提供 K8s 知识问答 |

## 安全约束

- **只读操作**: 仅允许 get, describe, logs 命令
- **命名空间隔离**: 只能操作配置允许的命名空间
- **禁止变更**: 严禁 apply, delete, patch, edit, scale 操作
- **敏感信息过滤**: 不暴露 Secret 内容和凭证

## 工具集

| 工具 | 状态 | 用途 |
|------|------|------|
| KubectlTool | 已实现 | 只读 kubectl 命令, 白名单子命令, 命名空间隔离, Secret 过滤 |
| KubeMinAPITool | 规划中 | 查询 KubeMin 平台资源 |

## 技术取舍

| 决策 | 理由 | 备选方案 |
|------|------|----------|
| 只读策略 | LLM 推理不可预测, 写操作风险过高 | 白名单写操作 (放弃: 安全审计成本高) |
| kubectl 命令而非 K8s API | 用户更熟悉 kubectl 输出格式, 易于理解 | client-go (放弃: Python 项目, 增加 FFI 复杂度) |
| 命名空间隔离 | 最小权限原则 | 全集群访问 (放弃: 安全风险) |
| 结构化轨迹而非完整思维链 | 保持可审计与安全边界 | 记录完整 CoT (放弃: 泄露风险) |

## 变更日志

| 日期 | 变更 | 原因 |
|------|------|------|
| 2026-02-28 | 支持 `ContextEnvelope` 跨任务上下文继承与查询驱动记忆注入 | 提升多阶段诊断任务的信息复用能力 |
| 2026-02-27 | 接入在线评估与 `reasoning_step` 结构化轨迹 | 提升诊断执行过程可观测性 |
| 2026-02-26 | 实现 KubectlTool (只读白名单 + 命名空间隔离 + Secret 过滤) | MVP 工具集 |
| 2026-02-26 | 接入中控运行时, 默认经 Scheduler 调度 | 落地 Agent Control Plane 主链路 |
| 2025-02 | 初始设计, 定义只读约束和 system prompt | 项目初始化 |
