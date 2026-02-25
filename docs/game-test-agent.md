# GameTestAgent 使用文档

GameTestAgent 是一个**独立模块化**的 Web 游戏测试/审核子 Agent。它通过 [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp) 自动化浏览器交互，可作为 KubeMin-Agent 中控层的子 Agent 被调度，也可以作为独立服务运行。

## 功能

- 阅读 PDF 玩法指南，理解预期游戏行为
- 通过 Chrome DevTools MCP 自动化浏览器交互（点击、输入、拖拽、滚动、JS 执行）
- 验证游戏逻辑正确性（规则是否按指南执行）
- 审核游戏内容合规性（文本/图片敏感内容检测）
- 测试 UI/UX 质量（交互元素、布局、反馈）
- 检查 Console 错误和 Network 异常请求

## 前置条件

- [Node.js](https://nodejs.org/) >= 20.19（用于运行 chrome-devtools-mcp）
- [Chrome](https://www.google.com/chrome/) 最新稳定版
- npm（随 Node.js 安装）

## 安装

### 基础安装

```bash
pip install -e .
```

Chrome DevTools MCP 通过 `npx` 自动下载，无需手动安装。

### HTTP 服务模式（额外依赖）

```bash
pip install -e ".[game-test-service]"
```

## 使用方式

### 1. CLI 一次性测试

```bash
game-test-agent test \
  --pdf guide.pdf \
  --url https://game.example.com \
  --api-key $LLM_API_KEY
```

**参数说明**：

| 参数 | 必填 | 说明 |
|------|------|------|
| `--pdf`, `-p` | 是 | PDF 玩法指南路径 |
| `--url`, `-u` | 是 | Web 游戏 URL |
| `--api-key`, `-k` | 是 | LLM API Key（也可通过 `LLM_API_KEY` 环境变量设置） |
| `--api-base` | 否 | LLM API 地址（通过 `LLM_API_BASE` 环境变量设置） |
| `--model`, `-m` | 否 | LLM 模型（默认 `openrouter/google/gemini-2.0-flash-001`） |
| `--workspace`, `-w` | 否 | 工作目录（默认 `~/.kubemin-agent/workspace`） |

### 2. HTTP 服务模式

```bash
game-test-agent serve \
  --port 8080 \
  --api-key $LLM_API_KEY
```

**API 接口**：

```bash
# 提交测试任务
curl -X POST http://localhost:8080/test \
  -F "game_url=https://game.example.com" \
  -F "pdf_file=@guide.pdf"

# 健康检查
curl http://localhost:8080/health
```

### 3. 作为模块调用

```bash
python -m kubemin_agent.agents.game_test test \
  --pdf guide.pdf \
  --url https://game.example.com \
  --api-key $LLM_API_KEY
```

### 4. 通过中控层调度

GameTestAgent 注册到中控层后，Scheduler 会自动识别意图并调度。

## 测试报告格式

1. **Game Overview** -- 游戏基本信息
2. **Logic Test Results** -- 游戏逻辑正确性验证结果
3. **Content Audit Results** -- 内容合规审核结果
4. **UI/UX Findings** -- UI/UX 测试发现
5. **Console/Network Issues** -- JS 错误和网络异常
6. **Issues Found** -- 发现的问题列表
7. **Overall Assessment** -- 总体评估（PASS / FAIL / CONDITIONAL）

## 专属工具

| 工具 | 功能 |
|------|------|
| `read_pdf` | 读取 PDF 玩法指南，提取文本内容 |
| `browser_action` | 12 种浏览器操作：navigate / click / fill / hover / drag / scroll / wait / evaluate / snapshot / press_key / console_logs / network |
| `take_screenshot` | 截图保存，支持全页截图和元素级截图 |
| `audit_content` | 内容审核：敏感文本检测 + 图片审核 + Console 错误检查 |

## 元素定位

GameTestAgent 使用 **uid 定位**（Chrome DevTools MCP 基于 a11y tree 自动分配），工作流程：

1. 调用 `snapshot` 获取页面结构和元素 uid
2. 使用 uid 进行 `click`、`fill`、`hover` 等操作
3. 操作后返回更新的 snapshot

## 架构

```
GameTestAgent
  |
  |-- MCPClient          (stdio JSON-RPC -> chrome-devtools-mcp subprocess)
  |-- BrowserTool        (12 种操作 -> MCP tool calls)
  |-- ScreenshotTool     (MCP take_screenshot)
  |-- ContentAuditTool   (MCP take_snapshot + evaluate_script + list_console_messages)
  |-- PDFReaderTool      (PyMuPDF, 本地处理)
```
