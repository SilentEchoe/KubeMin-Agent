---
name: patrol
description: KubeMin-Cli 平台巡检技能 — 健康检查策略、事件分析规则与报告模板
always: true
---

# Patrol Skill — KubeMin-Cli 平台巡检

本技能为 PatrolAgent 提供巡检领域知识，确保系统性、可重复地评估平台健康状态。

## 巡检策略

### STRATEGY 1 — 资源健康检查

按优先级依次检查以下资源类型：

1. **Node 状态**
   - 执行 `kubectl get nodes -o wide` 查看所有节点状态
   - 关注 `NotReady`、`MemoryPressure`、`DiskPressure`、`PIDPressure` 条件
   - 记录节点版本和资源利用率

2. **Pod 运行状态**
   - 执行 `kubectl get pods --all-namespaces -o wide` 查看全局 Pod 状态
   - 关注 `CrashLoopBackOff`、`ImagePullBackOff`、`Pending`、`Error`、`OOMKilled` 状态
   - 对异常 Pod 执行 `kubectl describe pod <name> -n <ns>` 获取详细原因
   - 检查重启次数异常偏高的 Pod（restarts > 5）

3. **Deployment / StatefulSet / DaemonSet**
   - 执行 `kubectl get deployments --all-namespaces` 检查副本就绪比例
   - 关注 `READY` 列中 desired ≠ available 的 Deployment
   - 检查滚动更新是否卡住（`Progressing=False`）

4. **Service / Endpoint**
   - 验证关键 Service 的 Endpoints 是否为空
   - 执行 `kubectl get endpoints --all-namespaces` 并过滤空 Endpoints

5. **PersistentVolumeClaim**
   - 检查 PVC 状态，关注 `Pending` 状态的 PVC

### STRATEGY 2 — 平台事件分析

1. 执行 `kubectl get events --all-namespaces --sort-by='.lastTimestamp'` 获取最近事件
2. 按以下分类识别关键事件：

| 事件类型 | 关键词 | 严重级别 | 说明 |
|---------|--------|---------|------|
| 调度失败 | `FailedScheduling` | HIGH | 资源不足或亲和性约束无法满足 |
| OOM 终止 | `OOMKilled` | HIGH | 容器内存超限被杀死 |
| 镜像拉取失败 | `Failed to pull image` | MEDIUM | 镜像不存在或仓库认证失败 |
| 探针失败 | `Unhealthy` / `probe failed` | MEDIUM | Liveness/Readiness 探针持续失败 |
| 节点异常 | `NodeNotReady` | CRITICAL | 节点不可用 |
| 卷挂载失败 | `FailedMount` | MEDIUM | PV/PVC 挂载异常 |
| 回退事件 | `BackOff` | MEDIUM | 容器反复重启 |

3. 对 HIGH / CRITICAL 事件进行根因分析（查看关联资源的 describe 输出）

### STRATEGY 3 — 报告生成

巡检完成后，使用 `write_file` 工具将报告写入 workspace，文件名格式：`patrol-report-YYYY-MM-DD.md`

报告必须遵循以下结构：

```markdown
# KubeMin-Cli 平台巡检报告

**巡检时间**: YYYY-MM-DD HH:MM
**巡检范围**: 全集群 / 指定命名空间
**健康评分**: X/100

## 摘要

一段话总结平台当前健康状态和关键发现。

## 资源状态

### 节点
| 节点名 | 状态 | 版本 | 备注 |
|--------|------|------|------|

### 异常 Pod
| Pod | 命名空间 | 状态 | 重启次数 | 原因 |
|-----|---------|------|---------|------|

### Deployment 就绪情况
| Deployment | 命名空间 | 期望/就绪 | 状态 |
|-----------|---------|----------|------|

## 事件分析

### 关键事件
| 时间 | 命名空间 | 对象 | 事件类型 | 消息 | 严重级别 |
|------|---------|------|---------|------|---------|

### 根因分析
对每个 HIGH/CRITICAL 事件给出分析和建议。

## 风险评估

| 风险项 | 级别 | 影响范围 | 建议措施 |
|--------|------|---------|---------|

## 建议

按优先级列出改进建议。

## 与上次巡检对比

标注新增问题、已解决问题、持续存在的问题。
```

### 健康评分计算规则

- 基础分 100 分
- 每个 CRITICAL 事件 -15 分
- 每个 HIGH 事件 -10 分
- 每个 MEDIUM 事件 -5 分
- 每个 NotReady 节点 -20 分
- 每个 CrashLoopBackOff Pod -8 分
- 每个 Deployment 副本不足 -5 分
- 最低 0 分

## 安全约束

- **只读操作**：仅使用 get / describe / logs 命令，严禁任何变更操作
- **敏感信息过滤**：报告中不包含 Secret 内容、API Key、密码等信息
- **命名空间遵守**：遵守 KubectlTool 的命名空间隔离策略
