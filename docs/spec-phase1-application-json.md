# Phase 1：稳定生成/校验 Application JSON（规格）

本规格用于约束 Agent（服务形态）在 Phase 1 的行为：对话式收集需求，稳定生成 `Application JSON` 与本地模板渲染产物，并通过 `POST /api/v1/applications/try` 做远程校验，不做创建与部署。

> 说明：更细粒度的 Job 拆分与资源编排由 KubeMin 工作流引擎负责；Agent 层只输出“粗粒度组件编排”（workflow）用于描述组件级依赖与顺序。

---

## 1. 服务配置（环境变量）

- `KUBEMIN_API_BASE_URL`：例如 `http://127.0.0.1:8080/api/v1`
- （可选）`KUBEMIN_API_TIMEOUT_SECONDS`：默认 `10`
- （可选）`KUBEMIN_API_RETRY`：默认 `0`

---

## 2. Phase 1 能力边界

**输入**
- 用户自然语言需求（业务开发者为主）
- 可选：选择一个本地模板（MySQL / Redis / Webservice Basic）

**输出**
- 稳定、可复现的 `Application JSON`
- 本地模板渲染产物（用于复用与参数化）
- 校验报告：本地规则校验 + 远程 `applications/try` 的结果

**不做**
- `POST /applications` 创建应用
- `workflow/exec` 执行部署
- `workflow/tasks/:id/status` 轮询运行状态

---

## 3. Application JSON（稳定子集）

### 3.1 顶层字段

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---:|---|---|
| `name` | string | 是 | - | 应用名（建议 kebab-case） |
| `namespace` | string | 是 | `default` | 命名空间 |
| `version` | string | 是 | `1.0.0` | 版本号 |
| `description` | string | 否 | `""` | 描述 |
| `project` | string | 否 | `""` | 项目名（可空） |
| `alias` | string | 否 | `""` | 别名（可空） |
| `component` | array | 是 | - | 组件列表 |
| `workflow` | array | 否 | - | 组件级编排（可省略） |

> 远程接口 `POST /applications` 的响应中会返回 `id`、`workflow_id`、`tmp_enable` 等字段；Phase 1 的输入 JSON 不包含这些服务端生成字段。

### 3.2 component[]（组件）

#### 3.2.1 通用字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `name` | string | 是 | 组件名（workflow 引用的唯一标识） |
| `type` | string | 是 | 枚举：`webservice` / `store` / `config` / `secret` |
| `replicas` | number | 否 | 副本数（默认 `1`） |
| `image` | string | 条件必填 | `webservice`/`store` 必填 |
| `properties` | object | 否 | 组件属性（按类型定义） |
| `traits` | object | 否 | OAM Traits（按需要附加） |

#### 3.2.2 类型：webservice

常用字段（来自测试用例约定）：
- `properties.ports`: `[{ "port": number, "expose"?: boolean }]`
- `properties.env`: `{ [key: string]: string }`

#### 3.2.3 类型：store（MySQL/Redis 等中间件）

与 `webservice` 类似，通常还会有：
- `traits.storage[]`（持久化/临时存储）
- `properties.env`（如 MySQL 初始化变量）

#### 3.2.4 类型：config

- `properties.conf`: `{ [key: string]: string }`（会生成 ConfigMap）
- `properties.labels`（可选）

#### 3.2.5 类型：secret

- `properties.secret`: `{ [key: string]: string }`（Opaque Secret 内容）

> 约定：Phase 1 默认把用户输入当作“明文值”。若需要支持“已 base64 编码值”，应在对话层提供显式开关（例如 `--secret-values=base64`），否则保持默认明文。

---

## 4. Traits（Phase 1 必须支持的最小集合）

Phase 1 的模板与典型组合要求至少支持：

### 4.1 traits.storage[]

典型字段（以 `tmpCreate` 为统一输出字段名）：
- `name`：volume 名
- `type`：`persistent` / `ephemeral` / `config` / `secret`
- `mountPath`：挂载路径
- `subPath`（可选）
- `readOnly`（可选）
- `sourceName`（config/secret 用）
- `tmpCreate`（persistent 用，是否动态创建 PVC）
- `size`、`storageClass`（persistent 用）

兼容性提示：
- 测试用例中出现过一次 `create: true`（旧字段）；Agent 输出统一使用 `tmpCreate`，但在导入/修复时允许兼容识别 `create` → `tmpCreate`。

### 4.2 traits.envFrom[]

- `[{ "type": "configMap" | "secret", "sourceName": string }]`

---

## 5. workflow[]（Agent 层粗粒度编排）

### 5.1 默认策略（你已确认：默认 C）

默认生成 **全部 `StepByStep`** 的 workflow，且按类型分层：

1) `config`/`secret` 层（同层内部串行）
2) `store` 层（同层内部串行）
3) `webservice` 层（同层内部串行）

当用户要求并行时才切换某一层为 `DAG`（Phase 2 可更激进，Phase 1 默认保守）。

### 5.2 workflow 结构

每个 step：
- `name`: string（建议稳定命名，如 `step1-config-secret` / `step2-store` / `step3-webservice`）
- `mode`: `StepByStep` 或 `DAG`
- `components`: `string[]`（必须来自 `component[].name`）

### 5.3 生成规则（稳定性）

- `workflow[].components` 永远从 `component[].name` 派生，禁止引用不存在的组件名。
- 组件排序稳定：优先按（层级→用户显式顺序→字典序）排序。
- 当用户未显式要求 workflow 时可省略；但若存在多组件与明显依赖（例如引用 config/secret），建议默认生成 workflow 以提升可读性与可控性。

---

## 6. Phase 1 本地模板（参数面板）

### 6.1 webservice-basic

**参数（建议）**
- `app.name`、`app.namespace`
- `service.name`
- `service.image`
- `service.port`、`service.expose`（默认 `false`）
- `service.replicas`（默认 `1`）
- `service.env`（可选）

**输出**
- 单个 `webservice` 组件
- 可选 workflow（默认可省略；若生成则 1 个 StepByStep）

### 6.2 mysql（store）

**参数（建议）**
- `app.name`、`app.namespace`
- `mysql.name`、`mysql.image`（默认 `mysql:8.0.x`）
- `mysql.port`（默认 `3306`）
- `mysql.replicas`（默认 `1`）
- `mysql.env`: `MYSQL_ROOT_PASSWORD`（必填）、`MYSQL_DATABASE`（可选）、`MYSQL_USER`/`MYSQL_PASSWORD`（可选）
- `mysql.storage.enabled`（默认 `true`）
- `mysql.storage.size`（默认 `5Gi`）
- `mysql.storage.storageClass`（可选）
- `mysql.storage.tmpCreate`（默认 `true`）
- `mysql.storage.mountPath`（默认 `/var/lib/mysql`）

**输出**
- 组件 type: `store`
- 绑定 `traits.storage[]`（persistent）
- workflow：按默认三层策略生成（只有 store 时也可生成单步）

### 6.3 redis（store）

**参数（建议）**
- `app.name`、`app.namespace`
- `redis.name`、`redis.image`（默认 `redis:7-alpine`）
- `redis.port`（默认 `6379`）
- `redis.replicas`（默认 `1`）
- `redis.persistence.enabled`（默认 `false`）
  - 若启用：同 mysql 的 `storage.*`

**输出**
- 组件 type: `store`
- 可选 `traits.storage[]`

---

## 7. Phase 1 与远程校验的契约

远程校验只使用：
- `POST ${KUBEMIN_API_BASE_URL}/applications/try`
- 成功响应：`{ "valid": true }`
- 失败响应：`{ "valid": false, "errors": [{ "field", "code", "message" }, ...] }`

Agent 在 Phase 1 的“完成”判定：
- `valid == true` 且本地规则校验通过（或仅存在可忽略告警）

