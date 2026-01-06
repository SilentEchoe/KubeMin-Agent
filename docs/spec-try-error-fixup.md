# /applications/try 校验与自动修复（规格）

本规格定义 Agent 如何使用 `POST /api/v1/applications/try` 的错误输出来实现“自愈式生成”：自动修复可确定的问题、对需要决策的问题发起追问、并在必要时重建 workflow 结构。

---

## 1. try 接口响应结构（已确认）

**成功**
```json
{ "valid": true }
```

**失败**
```json
{
  "valid": false,
  "errors": [
    { "field": "component[1].type", "code": "INVALID_COMPONENT_TYPE", "message": "..." }
  ]
}
```

字段含义：
- `errors[].field`：JSONPath-like 定位（例如 `workflow[1].components[0]`）
- `errors[].code`：机器可判读的错误码
- `errors[].message`：人类可读信息

---

## 2. 校验-修复主循环（通用）

1) 生成草案 `Application JSON`
2) 远程校验：调用 `POST /applications/try`
3) 若 `valid=true`：结束（Phase 1 输出；Phase 2 允许 create/exec）
4) 若 `valid=false`：
   - 解析 `errors[]` → 归类（可自动修复 / 需用户决策 / 不可修复）
   - 生成“修复计划”（Fix Plan）
   - 执行自动修复（在本地 JSON 上应用 patch）
   - 对需要决策的信息发起追问（填槽后再继续）
   - 必要时触发 workflow 重建
   - 回到步骤 2

建议上限：
- 自动修复回合：最多 N 轮（例如 5 轮），超过则停止并输出错误清单与当前 JSON 供人工处理。

---

## 3. workflow 重建规则（你已授权可改 workflow）

workflow 视为派生结构：当其与 `component[]` 不一致或引起校验失败时，允许全量重建。

### 3.1 触发条件
- errors 中出现 `COMPONENT_NOT_FOUND`
- 组件集合发生变化（新增/删除/重命名/type 修正）
- 用户切换“并行/串行/依赖顺序”要求

### 3.2 默认重建策略（Phase 1 默认 C）

按组件类型分层并串行执行：

1) `config` + `secret`（StepByStep）
2) `store`（StepByStep）
3) `webservice`（StepByStep）

每一层内：
- 若用户提供显式顺序：按用户顺序
- 否则：按组件名排序（字典序），保证稳定输出

若某层为空，则跳过该层 step。

### 3.3 step 命名（稳定）
- `step1-config-secret`
- `step2-store`
- `step3-webservice`

---

## 4. 错误码 → 修复动作（第一批必须支持）

### 4.1 INVALID_COMPONENT_TYPE

**典型场景**
- `component[i].type` 不是合法枚举（例如 `server`）

**自动修复**
- 将 type 限制为：`webservice` / `store` / `config` / `secret`
- 基于用户意图做映射（启发式）：
  - 文本包含 `mysql|redis|db|database|cache|mq` → 倾向 `store`
  - 文本包含 `api|backend|frontend|gateway|service|server` → 倾向 `webservice`
  - 文本包含 `config|配置` → 倾向 `config`
  - 文本包含 `secret|密码|密钥|token` → 倾向 `secret`

**需要用户决策时的追问**
- 当启发式不确定或存在冲突关键词：提示可选枚举并让用户选择。

**后续联动**
- type 修正后，重新评估该组件应落入 workflow 哪一层；必要时触发 workflow 重建。

---

### 4.2 COMPONENT_NOT_FOUND

**典型场景**
- workflow 引用了不存在的组件名（`workflow[x].components[y]`）

**自动修复（优先）**
- 直接触发 workflow 全量重建（见第 3 节），以保证引用与组件集合一致。

**补充修复（可选）**
- 若用户明确要求保留某个 step 的语义，可进行“相似名称替换建议”：
  - 找到最相近的 `component[].name` 候选（例如编辑距离/前缀匹配）
  - 让用户确认替换

---

## 5. 未知错误码处理（兜底策略）

当 `code` 不在已知表中：
- 不做盲目自动修复
- 仍然基于 `field` 给出定位（组件索引/step 名称）
- 将 `message` 原样呈现给用户
- 提供两类建议：
  - “结构性修复”：重建 workflow / 补齐必填字段 / 删除空对象
  - “语义性追问”：让用户补充缺失信息（例如端口、镜像、存储大小等）

---

## 6. 输出给用户的校验报告（建议格式）

- `valid`: true/false
- `errors`: 按组件/step 分组显示
- `fix plan`: 本轮 Agent 将要执行的自动修复动作列表（可让用户确认）

