---
name: workflow-authoring
description: Workflow 生成技能 — YAML 结构约束、校验顺序与发布前检查清单
version: "1"
always: false
agents: [workflow]
triggers: [workflow, yaml, pipeline, ci/cd, 编排, 发布, 部署流程]
---

# Workflow Authoring Skill

## 生成步骤

1. 先澄清目标：交付物、环境、触发方式、失败回滚策略
2. 生成 YAML 草稿：包含 `apiVersion/kind/metadata/spec`
3. 校验：
   - 先语法（YAML）
   - 再结构（必填字段）
4. 优化：补齐步骤依赖、资源限制、重试与超时

## 输出规范

- 先给简短设计说明，再给完整 YAML
- 明确指出关键字段含义（依赖关系、重试、超时）
- 给出最小验证方式（如如何调用 `validate_yaml`）

## 安全约束

- 不直接执行 apply，仅生成/修改 YAML
- 不嵌入敏感凭据明文
