# KubeMin-Agent Skills 规范

## 目标

统一 Skill 的定义、加载、触发与治理方式，确保 Skill 在 Control Plane 默认链路中可用、可测试、可维护。

## 目录约定

- 内置 Skill：`kubemin_agent/skills/<skill-name>/SKILL.md`
- 工作区 Skill：`<workspace>/skills/<skill-name>/SKILL.md`
- 同名覆盖策略：工作区 Skill 优先于内置 Skill

## Frontmatter 规范

每个 `SKILL.md` 顶部必须包含 YAML frontmatter：

```yaml
---
name: <skill-name>
description: <一句话描述>
version: "1"
always: false
agents: [general, k8s, workflow, patrol, orchestrator, guide, game_audit]
triggers: [keyword1, keyword2]
---
```

字段说明：

- `name`：Skill 名称，建议与目录名一致
- `description`：Skill 能力摘要，用于 `/skills` 和上下文摘要
- `version`：Skill 版本号，默认 `"1"`
- `always`：是否默认激活；默认 `false`
- `agents`：允许生效的 Agent 名称列表；为空表示不限 Agent
- `triggers`：触发关键词列表；为空表示不按意图触发

## 激活规则

对某个 Agent 的一次任务，Skill 按以下规则判定激活：

1. 先满足 Agent 匹配：`agents` 为空或包含当前 `agent_name`
2. 然后满足以下任一条件：
   - `always: true`
   - `agents` 非空且 `triggers` 为空（该 Agent 的默认技能）
   - `triggers` 任一关键词命中当前用户消息（大小写不敏感子串匹配）

## 设计要求

- Skill 内容必须是“可执行策略”，而不是泛泛说明
- 需明确安全边界（只读、敏感信息过滤、禁止操作）
- 需包含输出结构约束（报告模板、结果格式、校验点）
- 避免与 `system_prompt` 重复冲突；Skill 优先承载可变策略

## 测试要求

每次新增或修改 Skill 机制，至少补齐：

- `SkillsLoader` 解析与覆盖优先级测试
- 按 `agents/triggers/always` 的选择测试
- 至少 1 个 Agent 的上下文注入测试（确保技能真正进入系统提示）

## 维护与变更

- 技能变更需同步更新相关架构文档的“技术取舍/变更日志”
- 破坏性变更（字段删除、触发规则改变）需在 PR 中明确迁移说明

## 特殊说明：auto_commit

`skills/auto_commit/SKILL.md` 属于开发协作场景的工作区技能，不应作为生产内置 Skill。默认不得 `always` 全局激活，避免在未明确授权时触发自动提交行为。
