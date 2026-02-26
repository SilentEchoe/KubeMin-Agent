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
