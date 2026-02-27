# Agent 最小可用工具集实施方案

## 目标

为 GeneralAgent, K8sAgent, WorkflowAgent 实现最小可用工具集 (MVP), 接入已有的 ControlPlaneRuntime, 使三个 Agent 能真正处理用户请求。

## 现状

- `Tool` ABC 已定义: `name`, `description`, `parameters`, `execute()`
- `ToolRegistry` 已实现: 注册/执行/验证参数
- GameAuditAgent 已有 4 个工具 (PDFReaderTool, BrowserTool, ScreenshotTool, ContentAuditTool)
- GeneralAgent/K8sAgent/WorkflowAgent 的 `_register_tools()` 为空

---

## GeneralAgent (Fallback, 优先级最高)

### read_file -- 读取文件

- 参数: `path` (string, required)
- 安全: 限制在 workspace 内, 禁止读取 `.env`/密钥文件
- 返回: 文件内容 (超长则截断前 4000 字符)

### write_file -- 写入文件

- 参数: `path` (string, required), `content` (string, required)
- 安全: 限制在 workspace 内, 禁止覆盖系统文件
- 返回: 写入确认

### run_command -- 执行 Shell 命令

- 参数: `command` (string, required), `timeout` (integer, optional, default=30)
- 安全: 命令白名单 (ls/cat/echo/grep/find/wc/head/tail/pwd/env/date/curl/git/python3/pip/node/npm)
- 禁止: rm -rf, chmod, chown, sudo, kill, mkfs, dd, 管道到 sh/bash
- 返回: stdout + stderr (截断 4000 字符), exit_code

```
涉及文件:
  [NEW] kubemin_agent/agent/tools/filesystem.py  -- ReadFileTool + WriteFileTool
  [NEW] kubemin_agent/agent/tools/shell.py       -- ShellTool
  [MODIFY] kubemin_agent/agents/general_agent.py -- _register_tools 注册三个工具
```

---

## K8sAgent (只读诊断)

### kubectl -- 执行 kubectl 只读命令

- 参数: `command` (string, required), `namespace` (string, optional)
- 允许: get, describe, logs, top, explain, api-resources, version
- 禁止: apply, delete, patch, edit, scale, create, replace, exec
- 安全: 自动注入 `--namespace` 限定, 过滤含 Secret data 的输出
- 返回: kubectl 输出 (截断 4000 字符)

```
涉及文件:
  [NEW] kubemin_agent/agent/tools/kubectl.py     -- KubectlTool
  [MODIFY] kubemin_agent/agents/k8s_agent.py     -- _register_tools 注册
```

---

## WorkflowAgent (YAML 生成)

### read_file -- 复用 GeneralAgent 的 ReadFileTool (读取现有 YAML)

### write_file -- 复用 GeneralAgent 的 WriteFileTool (写出生成的 YAML)

### validate_yaml -- 校验 YAML 语法和 KubeMin 结构

- 参数: `content` (string, required)
- 校验: YAML 语法解析, 检查必要字段 (apiVersion, kind, metadata, spec)
- 返回: 校验结果 (valid/invalid + 错误详情)

```
涉及文件:
  [NEW] kubemin_agent/agent/tools/yaml_validator.py  -- YAMLValidatorTool
  [MODIFY] kubemin_agent/agents/workflow_agent.py    -- _register_tools 注册
```

---

## 验证计划

1. `ruff check kubemin_agent/` -- 全部通过
2. `pytest tests/` -- 现有测试不回退
3. 为每个新工具编写单元测试 (tests/test_tools.py)
4. 编译检查: `python3 -m compileall kubemin_agent`

---

## 架构原则：工具与 MCP 白名单机制 (Tool/MCP Allowlist)

为了明确 Agent 的能力边界，提升系统安全性和可靠性，所有的 Agent 必须采用**显式白名单机制 (Explicit Allowlist)** 来注册和使用 Tool 与 MCP 服务器。

### 为什么需要白名单限制？

1. **明确的职责边界 (Separation of Concerns):** 确保每个 Agent 只能访问完成其特定任务所需的最小权限集合。例如，`K8sAgent` 仅能使用只读的 `kubectl` 功能，无权进行文件写入或执行系统 Shell。
2. **提升安全性 (Reduce Blast Radius):** 防止 LLM 在遭遇 Prompt Injection 攻击或产生幻觉时发生越权操作。按白名单分配权限沙箱，可以从底层直接拦截越界调用。
3. **减少上下文污染 (Optimize Token & Precision):** 精简注入到 System Prompt 中的工具定义，降低模型因过多无关工具而产生的疑惑，从而提高意图识别与工具调用的准确度，并节省 Token 花销。
4. **增强可审计性 (Auditability):** 便于在 `ControlPlaneRuntime` 或 `AgentRegistry` 层面对跨界行为进行日志记录与拦截告警。

### 实施规范

- `BaseAgent` 应提供声明允许工具链（`allowed_tools` / `allowed_mcps`）的接口或属性。
- 子类 Agent 必须在初始化时明确列出所需的具体工具清单。
- `ToolRegistry` 在为 Agent 挂载工具时，严格根据该白名单进行筛选与注册，拒绝加载清单外的任何工具。
