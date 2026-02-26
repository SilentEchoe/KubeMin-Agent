# 上下文工程 (Context Engineering)

## 概述

上下文工程是 Agent 系统中最核心的工程挑战之一。它决定了 LLM 在每一轮决策时能"看到"什么信息、信息如何组织、以及如何在有限的上下文窗口中最大化决策质量。

核心矛盾: LLM 上下文窗口有限 (几十 K ~ 几百 K tokens), 但 Agent 运行时会产生大量信息 (对话历史 + 系统指令 + 工具返回 + 会话记忆 + 外部文档 + 历史操作)。上下文工程就是解决 "给模型看什么、不看什么、按什么顺序看" 的问题。

## 四个关键维度

### 1. 上下文选择 -- 放什么进去

| 信息类型 | 当前实现 | 策略 |
|----------|----------|------|
| System Prompt | 常驻加载 (ContextBuilder.build_system_prompt) | 含身份、Bootstrap 文件、Memory、Skills |
| 对话历史 | base.py 滑动窗口 `history[-10:]` | 只保留最近 10 轮 |
| 工具返回 | browser.py `MAX_CONTENT_LENGTH=4000` | 超长截断 |
| 外部知识 | PDFReaderTool 按需加载 | 只在调用时进入上下文 |
| 长期记忆 | MemoryStore 全量加载 MEMORY.md + 当日笔记 | 无检索，全部塞入 |
| Skills | SkillsLoader 按需/常驻两级 | always-load 全文 + 其余仅摘要 |

### 2. 上下文排序 -- 按什么顺序放

LLM 对信息位置敏感 (Primacy & Recency Bias):

- **最前面**: 放最重要的不可违反规则 (安全策略)
- **中间**: 放参考资料和历史信息 (容易被"遗忘")
- **最后面**: 放当前任务的具体指令 (Recency Bias 保证被重视)

当前 GameAuditAgent 的排布:

```
[System Prompt]
  +-- SECURITY POLICY (最高优先级)
  +-- game_url hint
  +-- Workflow 工作流
  +-- Testing scope
  +-- AUDIT STRATEGIES
  +-- Report format
[对话历史 -10:]
[当前用户消息]
```

### 3. 上下文压缩 -- 怎么精简

| 技术 | 当前实现 | 代码位置 |
|------|----------|----------|
| 截断 | snapshot 超 4000 字符截断 | browser.py L155-156 |
| 截断 | audit text 预览限 1000 字符 | content_audit.py L11 |
| 截断 | console audit 限 1000 字符 | content_audit.py L168 |
| 选择性遗忘 | 只保留最近 10 轮对话 | base.py L75 |
| 结构化 | audit 返回结构化报告而非原始 HTML | content_audit.py |
| 摘要 | (未实现) | -- |

### 4. 上下文隔离 -- 什么不该进来

已实现的安全策略本质上就是上下文隔离: 将游戏/PDF 内容限定为 "数据" 而非 "指令", 防止外部内容污染 Agent 的决策上下文。

---

## 增强方向与实施步骤

### 方向 1: 动态上下文预算

**问题**: 当前固定保留 10 轮历史, 不考虑任务复杂度和 token 预算。简单任务浪费上下文, 复杂任务历史不够。

**实施步骤**:

1. 在 `ContextBuilder` 中新增 `max_context_tokens: int` 参数 (默认按模型窗口的 80% 计算)
2. 新增 `estimate_tokens(text: str) -> int` 方法, 使用 `tiktoken` 或简单的字符数/4 估算
3. 修改 `build_messages()`:
   - 先计算 system_prompt 占用的 token 数
   - 计算 current_message 占用
   - 剩余预算分配给历史对话, **从最近往前贪心填充**, 超预算就丢弃更早的
4. 在 `base.py` 和 `loop.py` 中移除硬编码的 `history[-10:]`, 改用 ContextBuilder 的动态分配

```
涉及文件:
  [MODIFY] kubemin_agent/agent/context.py   -- 新增 token 预算逻辑
  [MODIFY] kubemin_agent/agents/base.py     -- 移除 history[-10:], 委托给 ContextBuilder
  [MODIFY] kubemin_agent/agent/loop.py      -- 同上
```

### 方向 2: 工具结果摘要

**问题**: 浏览器 snapshot、console_logs、network 等工具返回大量原始文本, 简单截断会丢失关键信息。

**实施步骤**:

1. 在 `kubemin_agent/agent/tools/` 下新增 `summarizer.py`:
   - 定义 `ToolResultSummarizer` 类
   - 提供 `summarize(tool_name: str, raw_result: str, max_tokens: int) -> str` 方法
   - 对 snapshot: 提取关键元素和 uid, 移除重复/静态内容
   - 对 console_logs: 只保留 error/warning, 去重
   - 对 network: 只保留失败请求, 按状态码分组
2. 在 `BrowserTool.execute()` 返回结果前调用 summarizer
3. 可选: 用 LLM 做二次摘要 (成本较高, 作为开关提供)

```
涉及文件:
  [NEW]    kubemin_agent/agent/tools/summarizer.py  -- 工具结果摘要器
  [MODIFY] kubemin_agent/agent/tools/browser.py     -- 集成 summarizer
  [MODIFY] kubemin_agent/agent/tools/content_audit.py -- 集成 summarizer
```

### 方向 3: 跨 Agent 上下文传递

**问题**: Scheduler 调度子 Agent 时, 当前直接传递用户原始消息。子 Agent 缺少前置上下文, 或收到过多无关信息。

**实施步骤**:

1. 定义 `AgentContext` 数据类, 包含:
   - `task_summary: str` -- 精炼后的任务描述
   - `relevant_history: list[dict]` -- 与本次任务相关的历史
   - `shared_findings: dict` -- 其他 Agent 的发现 (如果有)
   - `metadata: dict` -- 调度元信息 (来源 Agent、优先级等)
2. Scheduler 在调度前, 用 LLM 将上下文压缩为 `AgentContext`
3. 子 Agent 的 `run()` 方法接收 `AgentContext` 而非纯字符串
4. 子 Agent 完成后, 将结果写回 `AgentContext.shared_findings` 供后续 Agent 使用

```
涉及文件:
  [NEW]    kubemin_agent/control/agent_context.py  -- AgentContext 数据类
  [MODIFY] kubemin_agent/control/scheduler.py      -- 构建 AgentContext
  [MODIFY] kubemin_agent/agents/base.py            -- run() 接收 AgentContext
```

### 方向 4: 记忆检索 (RAG) -- 统一 Backend 接口

**问题**: MemoryStore 目前全量加载 MEMORY.md, 随着内容增长会占用过多上下文。且后端存储方式硬编码, 无法切换。

**设计**: 策略模式 (Strategy Pattern), 统一 `MemoryBackend` 接口, 上层只依赖抽象, 底层可自由切换。

```
ContextBuilder / Agent
       |
  MemoryStore  (外观层: remember / recall / forget)
       |
  MemoryBackend  (抽象基类: store / search / delete / list_all)
       |
  ┌────┼──────────────┐
  |    |               |
FileBackend  JSONLBackend  VectorBackend (预留)
(.md 文件)    (.jsonl)      (向量数据库)
```

**数据模型**:

```python
@dataclass
class MemoryEntry:
    id: str              # 唯一标识
    content: str         # 记忆内容
    tags: list[str]      # 标签 (用于过滤)
    created_at: datetime  # 创建时间
    source: str          # 来源 (agent_name, session_key)
    metadata: dict       # 扩展字段
```

**Backend 差异**:

| Backend | search 策略 | 适用场景 |
|---------|------------|----------|
| FileBackend | 关键词子串匹配 | 开发/测试, 记忆量少, 零依赖 |
| JSONLBackend | TF-IDF 评分 | 中等规模, 无需外部依赖 |
| VectorBackend | 嵌入向量 + 余弦相似度 | 大量记忆, 语义检索 (预留接口) |

**实施步骤**:

1. 将 `agent/memory.py` 重构为 `agent/memory/` 包:
   - `__init__.py` -- 导出 MemoryStore, MemoryEntry, MemoryBackend
   - `entry.py` -- MemoryEntry 数据类
   - `backend.py` -- MemoryBackend 抽象基类
   - `file_backend.py` -- FileBackend (基于 .md 文件, 关键词匹配)
   - `jsonl_backend.py` -- JSONLBackend (基于 .jsonl, TF-IDF 检索)
   - `store.py` -- MemoryStore 外观层
2. MemoryStore 对外接口: `remember()`, `recall()`, `forget()`, `get_context()`
3. 通过构造参数或配置选择 Backend, 默认 FileBackend
4. 修改 `context.py` 使用新接口: `recall(query, top_k)` 替代全量加载

```
涉及文件:
  [DELETE] kubemin_agent/agent/memory.py
  [NEW]    kubemin_agent/agent/memory/__init__.py
  [NEW]    kubemin_agent/agent/memory/entry.py
  [NEW]    kubemin_agent/agent/memory/backend.py
  [NEW]    kubemin_agent/agent/memory/file_backend.py
  [NEW]    kubemin_agent/agent/memory/jsonl_backend.py
  [NEW]    kubemin_agent/agent/memory/store.py
  [MODIFY] kubemin_agent/agent/context.py  -- 使用新 MemoryStore 接口
```

### 方向 5: 上下文观测

**问题**: 目前无法知道每轮实际消耗了多少 token, 无法判断上下文是否接近溢出。

**实施步骤**:

1. 在 `LLMProvider.chat()` 的返回值 `LLMResponse` 中新增:
   - `prompt_tokens: int`
   - `completion_tokens: int`
   - `total_tokens: int`
2. 在 AgentLoop 和 BaseAgent 的 tool call 循环中记录每轮 token 消耗:
   - `logger.info(f"[iteration {i}] tokens: {response.prompt_tokens}/{model_max}")`
3. 当 prompt_tokens 超过模型窗口的 80% 时, 触发上下文压缩:
   - 自动丢弃最早的对话历史
   - 或对工具结果做摘要压缩
4. 可选: 暴露到 `/health` 端点, 供监控系统采集

```
涉及文件:
  [MODIFY] kubemin_agent/providers/base.py         -- LLMResponse 新增 token 字段
  [MODIFY] kubemin_agent/providers/litellm_provider.py -- 填充 token 字段
  [MODIFY] kubemin_agent/agent/loop.py             -- 记录 + 触发压缩
  [MODIFY] kubemin_agent/agents/base.py            -- 同上
```

---

## 优先级建议

| 优先级 | 方向 | 原因 |
|--------|------|------|
| P0 | 上下文观测 | 基础设施, 没有观测就无法判断其他优化的效果 |
| P0 | 动态上下文预算 | 直接影响 Agent 的稳定性, 防止上下文溢出 |
| P1 | 工具结果摘要 | GameAuditAgent 的 snapshot/network 返回量大, 摘要可显著提升效率 |
| P2 | 跨 Agent 上下文传递 | 多 Agent 协作场景的基础, 但当前只有单 Agent 调度 |
| P2 | 记忆检索 (RAG) | 长期运行后才会凸显, 前期 MEMORY.md 内容少不紧迫 |

## 当前代码参考

| 文件 | 职责 |
|------|------|
| `agent/context.py` | ContextBuilder: 组装 system prompt + 消息列表 |
| `agent/memory.py` | MemoryStore: 文件持久化记忆 |
| `agent/loop.py` | AgentLoop: 主循环 (消息 -> 上下文 -> LLM -> 工具 -> 响应) |
| `agents/base.py` | BaseAgent: 子 Agent 基类, 含 tool call 循环 |
| `agent/tools/browser.py` | BrowserTool: snapshot 截断 MAX_CONTENT_LENGTH |
| `agent/tools/content_audit.py` | ContentAuditTool: 审核结果截断 |
