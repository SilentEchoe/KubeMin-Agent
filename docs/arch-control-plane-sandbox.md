# ControlPlane 全局沙箱架构文档

## 设计理念

KubeMin-Agent 现有安全能力主要集中在工具层（命令白名单、路径限制、输出校验），但控制平面进程本身与子 Agent 进程仍可能直接暴露在宿主机权限与网络能力下。

本方案的目标是将安全边界提升到**进程级全局沙箱**：

- 控制平面与所有子 Agent 必须在沙箱内部运行
- 沙箱策略默认 `strict`（fail closed）
- 本地与 K8s 部署采用一致的“默认拒绝”思路
- 工具层沙箱作为第二道防线，而非唯一防线

## 架构

```
CLI/Gateway Entry
   |
   +-- SandboxLauncher (global)
   |      +-- backend resolver: container > bwrap
   |      +-- strict preflight (fail closed)
   |      +-- re-exec in sandbox
   |
   +-- EgressGuard (process-level)
   |      +-- require proxy in strict mode
   |      +-- block direct outbound connections
   |      +-- pass allowlist to proxy
   |
   +-- ControlPlaneRuntime
          +-- Scheduler / Validator / Sub-Agents
          +-- Tool-level sandbox (ShellTool/KubectlTool...)
```

K8s 部署层额外提供：

- `securityContext` 最小权限基线
- `runtimeClassName`（默认 gVisor）
- `NetworkPolicy` 默认拒绝 + 显式放行

## 功能清单

| 功能 | 状态 | 说明 |
|------|------|------|
| 全局沙箱模式配置 | 已实现 | `sandbox.mode=off/best_effort/strict` |
| 启动层沙箱预检 | 已实现 | strict 下无后端时拒绝启动 |
| 本地容器沙箱重启 | 已实现 | 通过 docker/podman 重新拉起同命令 |
| 进程级外联守卫 | 已实现 | strict + 默认拒绝时要求代理并阻断直连 |
| K8s 安全清单基线 | 已实现 | securityContext + runtimeClass + NetworkPolicy |
| 运行入口收敛 | 已实现 | `agent/gateway` 仅走 ControlPlaneRuntime，不再保留 legacy AgentLoop 分支 |
| Shell 默认白名单收紧 | 已实现 | 移除解释器/包管理/构建类默认入口，降低命令执行攻击面 |

## 安全约束

- strict 模式下，沙箱不可用时必须失败，不允许静默回退
- strict + default_deny 下，代理地址缺失必须失败
- 仅允许显式配置的外联白名单；默认拒绝未知目标
- 沙箱内运行进程必须使用最小权限（非 root、只读根、禁止提权）
- 工具层安全限制必须保留，作为进程级沙箱失效时的兜底

## 工具集

| 组件 | 用途 |
|------|------|
| SandboxLauncher | 入口重启、后端探测、fail closed 预检 |
| EgressGuard | 进程级网络出口约束 |
| ShellTool SandboxRunner | 工具层命令执行隔离（二级防线） |

## 技术取舍

| 决策 | 理由 | 备选方案 |
|------|------|----------|
| 默认 `strict` | 安全优先，避免“看似开启实则回退” | 默认 `best_effort`（放弃：安全边界不稳定） |
| 本地后端优先容器 | 跨平台一致性更好 | 仅 bwrap（放弃：非 Linux 不可用） |
| 代理强制 + 默认拒绝 | 可观测、可审计、可集中治理 | 应用层域名拦截（放弃：绕过路径更多） |
| 工具沙箱保留 | 形成双层防护 | 移除工具沙箱（放弃：单点失效风险） |
| 浏览器 `--no-sandbox` 维持现状 | 与既有 GameAudit 运维策略兼容 | 全部强制禁用（放弃：现网兼容性风险） |

## 变更日志

| 日期 | 变更 | 原因 |
|------|------|------|
| 2026-03-25 | 移除 legacy AgentLoop 入口并收紧 `run_command` 默认白名单 | 统一运行时安全边界，降低误执行高风险命令概率 |
| 2026-03-18 | 新增 ControlPlane 全局沙箱架构文档，定义 strict 全局沙箱与代理强制策略 | 将安全边界从工具级提升到进程级 |
