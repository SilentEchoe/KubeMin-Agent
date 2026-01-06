# CLI 形态草案（Phase 1/2）

本文件只定义交互与命令形态，不涉及实现。

> Agent 作为服务运行，CLI 只是最外层入口（业务开发者本地使用）。

---

## 环境变量

- `KUBEMIN_API_BASE_URL`：KubeMin HTTP API 基地址（含 `/api/v1`）

---

## Phase 1（默认）：生成 + 校验 + 模板

- `kubemin-agent new`
  - 对话式收集需求，生成 `application.json`
  - 可指定模板：`--template mysql|redis|webservice-basic`

- `kubemin-agent validate <path>`
  - 本地规则校验 + 远程 `POST /applications/try`
  - `--fix`：按 `docs/spec-try-error-fixup.md` 尝试自动修复并重试

- `kubemin-agent templates list`
- `kubemin-agent templates render <template> --params params.json`

---

## Phase 2（显式开启）：Plan + 创建 + 执行 + 观测

- `kubemin-agent plan`
  - 输出可迭代的计划（组件拆分、workflow 编排、待确认项）
  - 每轮可调用 `try` 并根据 errors 更新 plan

- `kubemin-agent create <path>`
  - `POST /applications`，输出 `appID`、`workflow_id`

- `kubemin-agent exec --app-id <id> --workflow-id <id>`
  - `POST /applications/:appID/workflow/exec`，输出 `taskId`

- `kubemin-agent status --task-id <id> [--watch]`
  - `GET /workflow/tasks/:taskID/status`

- `kubemin-agent cancel --app-id <id>`
  - `POST /applications/:appID/workflow/cancel`

- （扩展）`kubemin-agent version --app-id <id> --payload update.json`
  - `POST /applications/:appID/version`

