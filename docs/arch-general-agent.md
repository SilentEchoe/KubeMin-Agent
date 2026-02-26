# GeneralAgent 架构文档

## 设计理念

多 Agent 系统需要一个 **兜底 Agent** 处理不属于任何专业 Agent 领域的任务。GeneralAgent 是 Scheduler 的 fallback 选项 -- 当意图分析无法匹配到 K8sAgent/WorkflowAgent 等专职 Agent 时, 由 GeneralAgent 承接。

设计原则:
- 通用能力: 文件操作、Shell 命令、Web 搜索、知识问答
- 安全边界: 文件操作限定在 workspace 内, Shell 命令避免破坏性操作
- 可扩展: 新的通用工具优先注册到 GeneralAgent

## 架构

```
GeneralAgent (extends BaseAgent)
  |
  +-- system_prompt: 通用助手 + 安全约束
  +-- ToolRegistry
       +-- FilesystemTool  (规划中: 文件读写)
       +-- ShellTool       (规划中: 安全 Shell 执行)
       +-- WebSearchTool   (规划中: 网络搜索)
```

调度路径:

```
用户消息 -> Scheduler -> (无专职 Agent 匹配) -> GeneralAgent -> 工具调用 -> 结果返回
```

## 功能清单

| 功能 | 状态 | 说明 |
|------|------|------|
| 中控调度接入 | 已实现 | 通过 ControlPlaneRuntime 注册到 AgentRegistry, 由 Scheduler 调度 |
| 文件读写 | 已实现 | ReadFileTool + WriteFileTool, workspace 沙箱限制 |
| Shell 命令执行 | 已实现 | ShellTool, 命令白名单 + 危险模式阻断 |
| Web 搜索 | 规划中 | 搜索引擎查询和网页抓取 |
| 通用问答 | 已实现 | 通过 LLM 回答云原生/通用技术问题 |

## 安全约束

- 文件操作限定在 workspace 目录内
- Shell 命令禁止破坏性操作 (rm -rf, chmod 777 等)
- 不暴露 API 密钥和凭证
- 不执行未经审查的外部脚本

## 工具集

| 工具 | 状态 | 用途 |
|------|------|------|
| ReadFileTool | 已实现 | workspace 内文件读取, 敏感文件过滤 |
| WriteFileTool | 已实现 | workspace 内文件写入, 自动创建父目录 |
| ShellTool | 已实现 | 安全沙箱内的 Shell 命令, 命令白名单 |
| WebSearchTool | 规划中 | 网络搜索和信息检索 |

## 技术取舍

| 决策 | 理由 | 备选方案 |
|------|------|----------|
| Fallback 定位 | 明确分工, 专职 Agent 优先 | 全能 Agent (放弃: 职责不清, system prompt 过长) |
| Workspace 沙箱 | 最小权限原则, 防止越权 | 全文件系统访问 (放弃: 安全风险) |
| Shell 白名单策略 | 动态黑名单容易遗漏危险命令 | 黑名单 (放弃: 不完备) |

## 变更日志

| 日期 | 变更 | 原因 |
|------|------|------|
| 2026-02-26 | 实现 ReadFileTool + WriteFileTool + ShellTool | MVP 工具集, 使 GeneralAgent 可实际处理用户请求 |
| 2026-02-26 | 接入中控运行时, 由 Scheduler 默认调度执行 | 落地 Agent Control Plane 主链路 |
| 2025-02 | 初始设计, 定义 fallback 定位和安全约束 | 项目初始化 |
