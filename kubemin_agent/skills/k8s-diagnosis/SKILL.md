---
name: k8s-diagnosis
description: Kubernetes 只读诊断技能 — 故障分层排查、证据采集与结论输出模板
version: "1"
always: false
agents: [k8s]
triggers: [k8s, kubernetes, pod, crashloop, deployment, service, node, oom, 异常, 故障]
---

# K8s Diagnosis Skill

## 诊断流程

按以下顺序执行只读排查：

1. 资源概览：`kubectl get pods/deployments/services -A`
2. 错误定位：锁定异常对象（`CrashLoopBackOff` / `ImagePullBackOff` / `Pending` / `Error`）
3. 深入证据：
   - `kubectl describe <resource>`
   - `kubectl logs <pod> --tail=200`
4. 范围确认：判断是单实例、单命名空间还是跨集群问题
5. 根因归类：配置问题 / 资源瓶颈 / 依赖不可达 / 调度约束

## 输出规范

回答必须包含：

- 现象：发生了什么
- 证据：来自哪些命令输出
- 根因判断：最可能原因与置信度
- 处理建议：按优先级给出 1-3 条可执行动作

## 安全约束

- 仅允许只读命令，不得执行任何变更操作
- 不得输出 Secret、Token、密钥等敏感值
