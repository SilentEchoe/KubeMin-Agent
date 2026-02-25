# GameTestAgent 使用文档

GameTestAgent 是一个**独立模块化**的 Web 游戏测试/审核子 Agent。它可以作为 KubeMin-Agent 中控层的子 Agent 被调度，也可以作为独立服务运行。

## 功能

- 阅读 PDF 玩法指南，理解预期游戏行为
- 通过浏览器自动化（Playwright）与 Web 游戏交互
- 验证游戏逻辑正确性（规则是否按指南执行）
- 审核游戏内容合规性（文本/图片敏感内容检测）
- 测试 UI/UX 质量（交互元素、布局、反馈）

## 安装

### 基础安装

```bash
pip install -e .
playwright install chromium
```

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

**参数说明**：

| 参数 | 必填 | 说明 |
|------|------|------|
| `--port` | 否 | 服务端口（默认 8080） |
| `--host` | 否 | 绑定地址（默认 0.0.0.0） |
| `--api-key`, `-k` | 是 | LLM API Key |
| `--model`, `-m` | 否 | LLM 模型 |

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

当 GameTestAgent 注册到 KubeMin-Agent 中控层后，用户可以通过自然语言触发：

```
用户: 帮我测试这个游戏 https://game.example.com，玩法指南在 /path/to/guide.pdf
```

Scheduler 会自动识别意图并调度到 GameTestAgent。

## 测试报告格式

GameTestAgent 生成的测试报告包含以下章节：

1. **Game Overview** -- 游戏基本信息
2. **Logic Test Results** -- 游戏逻辑正确性验证结果
3. **Content Audit Results** -- 内容合规审核结果
4. **UI/UX Findings** -- UI/UX 测试发现
5. **Issues Found** -- 发现的问题列表
6. **Overall Assessment** -- 总体评估（PASS / FAIL / CONDITIONAL）

## 专属工具

| 工具 | 功能 |
|------|------|
| `read_pdf` | 读取 PDF 玩法指南，提取文本内容 |
| `browser_action` | 浏览器自动化：navigate / click / type / scroll / wait / evaluate / content |
| `take_screenshot` | 截图保存至 workspace/screenshots/，用于视觉验证 |
| `audit_content` | 页面内容审核：敏感文本检测 + 图片列表提取 |

## 截图存储

测试过程中的截图保存在 `{workspace}/screenshots/` 目录下，文件名格式：

```
{YYYYMMDD_HHMMSS}_{label}.png
```
