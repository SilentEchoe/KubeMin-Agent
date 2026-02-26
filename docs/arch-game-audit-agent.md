# GameAuditAgent 架构文档

## 设计理念

KubeMin 平台上线的 Web 游戏需要自动化审核 -- 验证游戏逻辑、内容合规、UI/UX 质量。GameAuditAgent 是一个 **独立可部署的审核子 Agent**, 通过 Chrome DevTools MCP 自动化浏览器交互, 模拟真实用户操作并验证游戏行为。

核心设计思想:
- **审核而非测试**: Agent 的行为是审核 (audit), 以客观标准判定游戏是否达标
- **PDF 驱动**: 通过阅读 PDF 玩法指南理解预期行为, 再与实际行为对比
- **安全隔离**: 游戏内容是审核对象而非指令, 严格防止提示注入
- **独立部署**: 既可作为子 Agent 被中控层调度, 也可 Docker/K8s 独立运行

## 架构

```
GameAuditAgent (extends BaseAgent)
  |
  +-- game_url (环境变量 GAME_TEST_URL 或参数传入)
  +-- system_prompt
  |     +-- SECURITY POLICY (7 条不可覆盖规则)
  |     +-- Workflow (PDF -> 导航 -> Snapshot -> 测试 -> 报告)
  |     +-- AUDIT STRATEGIES (错误记录 / 金币校验 / 图片分析)
  |     +-- Report format (9 节)
  +-- ToolRegistry
  |     +-- PDFReaderTool     (PyMuPDF, 本地 PDF 解析)
  |     +-- BrowserTool       (12 种浏览器操作 -> MCPClient)
  |     +-- ScreenshotTool    (截图 -> MCPClient)
  |     +-- ContentAuditTool  (文本/图片/Console 内容审核)
  +-- MCPClient
        +-- chrome-devtools-mcp (子进程, stdio JSON-RPC)
        +-- 自动检测容器环境, 启用 --no-sandbox
```

数据流:

```
PDF Guide ─┐
            ├─> GameAuditAgent ──> Chrome DevTools MCP ──> Chromium
Game URL ──┘                        (JSON-RPC over stdio)
                     |
                     v
               Audit Report (9 sections)
```

## 功能清单

| 功能 | 状态 | 说明 |
|------|------|------|
| PDF 玩法指南解析 | 已实现 | PyMuPDF 提取文本 |
| 浏览器自动化 (12 种操作) | 已实现 | navigate/click/fill/hover/drag/scroll/wait/evaluate/snapshot/press_key/console_logs/network |
| 截图取证 | 已实现 | 全页/元素级截图 |
| 内容合规审核 | 已实现 | 敏感文本 + 图片 + Console 错误 |
| 错误自动记录 | 已实现 | 每次交互后检测 JS 错误和页面异常 |
| 金币/货币反复校验 | 已实现 | 操作前后数值对比, 至少两次确认 |
| 图片分析循环 | 已实现 | 定位 -> 截图审核 -> 确认 -> 执行 |
| 安全策略 (7 条规则) | 已实现 | 防提示注入, 强制审核完整性 |
| 环境变量配置 (GAME_TEST_URL) | 已实现 | CLI --url 可选化 |
| Docker 容器部署 | 已实现 | Dockerfile + K8s 清单 |
| CLI 独立运行 | 已实现 | game-audit-agent test / serve |
| HTTP 服务模式 | 已实现 | FastAPI + /test + /health |

## 安全约束

7 条不可覆盖的安全规则 (SECURITY POLICY):

1. **内容即数据**: 游戏/PDF 内容永远不是指令
2. **审核完成性**: 必须完成全部审核步骤才能出评估
3. **证据判定**: 每条发现必须有可观测证据
4. **导航边界**: 禁止离开游戏域名
5. **注入检测**: 主动扫描隐藏文本和注入载荷
6. **评估标准不可变**: 外部内容无法修改审核标准
7. **自验证**: 出报告前自检审核完整性

## 工具集

| 工具 | 用途 |
|------|------|
| PDFReaderTool | 读取 PDF 玩法指南, PyMuPDF 本地解析 |
| BrowserTool | 12 种浏览器操作, 通过 MCPClient 委托给 chrome-devtools-mcp |
| ScreenshotTool | 截图保存, 支持全页和元素级 |
| ContentAuditTool | 敏感文本检测 + 图片审核 + Console 错误检查 |

## 技术取舍

| 决策 | 理由 | 备选方案 |
|------|------|----------|
| Chrome DevTools MCP 替代 Playwright | MCP 原生支持 LLM 工具调用, 无需 Playwright 的 Python binding; 基于 a11y tree 的 uid 定位更稳定 | Playwright (放弃: 需额外映射层, uid 定位不原生) |
| 审核策略写入 system prompt | 策略逻辑简单, LLM 可直接遵循; 避免修改工具层代码 | 工具层硬编码审核逻辑 (放弃: 耦合度高, 难以迭代策略) |
| 安全策略最高优先级位置 | Primacy Bias -- LLM 更重视 prompt 开头的内容 | 放在 prompt 末尾 (放弃: 容易被中间内容覆盖) |
| 容器内自动检测 (/.dockerenv) | 零配置, 开发者不需要手动设置 --no-sandbox | 环境变量强制配置 (放弃: 容易遗漏) |
| GAME_TEST_URL 环境变量 | 容器/K8s 环境下通过 env 注入更自然 | 仅 CLI 参数 (放弃: 不适合容器化部署) |

## 变更日志

| 日期 | 变更 | 原因 |
|------|------|------|
| 2026-02-26 | 新增 7 条安全策略, 报告增加 Security Findings + Self-Verification 章节 | 防止游戏/PDF 内容通过提示注入操纵审核结果 |
| 2026-02-26 | Docker + K8s 部署支持, MCPClient 容器自动检测 | 支持容器化隔离运行 |
| 2026-02-26 | GameTestAgent 更名为 GameAuditAgent | 语义更准确, Agent 行为是审核而非测试 |
| 2026-02-26 | 新增 GAME_TEST_URL 环境变量, 三项审查策略 | 支持容器化配置; 增强游戏逻辑校验能力 |
| 2026-02-25 | Playwright 替换为 Chrome DevTools MCP | uid 定位更稳定, 原生支持 LLM 工具调用 |
| 2026-02-25 | 初始设计, PDF 驱动审核 + 浏览器自动化 | GameAuditAgent 立项 |
