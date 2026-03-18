---
name: orchestrator-delegation
description: Orchestrator 委派策略技能 — 直连工具与子 Agent 委派的决策准则
version: "1"
always: false
agents: [orchestrator]
triggers: []
---

# Orchestrator Delegation Skill

## 决策规则

按以下优先级决策：

1. 单步简单任务：优先直连工具（读文件、单条命令、单次校验）
2. 领域复杂任务：优先委派给专职 Agent（k8s/workflow/patrol/game_audit）
3. 多领域组合任务：拆成子步骤，必要时混合“直连 + 委派”

## 执行原则

- 每次工具调用前说明意图
- 避免重复调用相同工具获取同一证据
- 需要跨步骤上下文时，先汇总已有发现再继续

## 输出规范

- 先给结论，再给关键证据
- 对不确定结论标注风险与下一步建议
