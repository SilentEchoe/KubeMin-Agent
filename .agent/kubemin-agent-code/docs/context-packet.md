# Context Packet (任务上下文包)

提需求时一次性提供"最小且充分"的上下文，减少追问，提升单轮交付成功率。

---

## 快速模板

```markdown
### Goal (目标)
一句话描述期望效果

### Scope (范围)
- 文件: `path/to/file.py`
- 符号: `class Foo`, `def bar()`

### Current → Expected (现状与期望)
- 现状: 
- 期望: 
- 错误日志（如有）:

### Risk (风险)
Low / Medium / High

### Constraints (约束，可选)
- 兼容性: 
- 性能要求: 
- 异步安全: 

### Deliverables (期望输出)
- [ ] 代码
- [ ] 测试  
- [ ] 文档
- [ ] PR 文案
```

---

## 填写示例

```markdown
### Goal
为 Agent 新增 Kubernetes 资源查询工具（kubectl_tool）

### Scope
- 文件: `agent/tools/kubectl.py`（新建）
- 文件: `agent/loop.py`（注册工具）
- 符号: `class KubectlTool(Tool)`

### Current → Expected
- 现状: Agent 无法直接查询 K8s 集群资源
- 期望: Agent 可通过 kubectl_tool 执行 `kubectl get/describe` 等只读命令
- 错误日志: 无

### Risk
Medium（涉及安全边界：需限制为只读命令）

### Constraints
- 仅允许只读命令（get、describe、logs）
- 必须限制 namespace 范围
- 命令超时上限 30s

### Deliverables
- [x] 代码
- [x] 测试
- [ ] 文档
```

---

## 最小信息集

当不确定提供什么时，至少包含：

1. **Goal** - 一句话目标
2. **Scope** - 文件路径 + 关键符号
3. **Current → Expected** - 复现步骤或错误输出
4. **Risk** - 你的判断

---

## 提供代码片段的原则

| ✅ 做 | ❌ 避免 |
|------|--------|
| 仅贴关键片段 (30-120行) | 整文件粘贴 |
| 标注路径和符号名 | 无上下文的代码块 |
| 包含调用方/被调用方 | 仅贴单个函数 |
| 标注 async/sync 边界 | 忽略异步上下文 |
