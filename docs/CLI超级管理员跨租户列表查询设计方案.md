# CLI 超级管理员跨租户列表查询设计方案（Go CLI）

## 1. 背景与范围

在 `wiserec` 和 `mlops` 管理台中，平台提供两种全局管理权限：**超级管理员**与**超级管理员只读**。持有这两种权限中任意一种的用户，在执行资源列表查询时，可以不局限于当前选中的单一租户，而在全部租户范围内检索目标资源（例如在全部租户的服务列表中按名称查询指定服务）。

- **实施范围**：**仅修改 `cli-go`**，`cli-python` 不再演进、不做任何代码改动。
- **核心目标**：
  1. 在 `cli-go` 中采集、持久化并按需补全 `/ai/user/info` 返回的 `isSuperAdmin` 与 `isAISupporter` 权限标识。
  2. 严格保持现有 `business.json`、`selected.businessId`、多会话隔离（`SessionState`）、`StateID` 一致性校验及 HTTP 请求头 `businessid` / `ai-businessId` 契约不变，对写操作、在线权限校验和会话保活零冲击。
  3. 以命令级显式开关 `--all-business` / `-A` 覆盖全部 10 个目标列表查询命令，并在 `ml tree`（按权限按需展示）与 `--help`（统一保留并注明权限前提）中清晰体现。

---

## 2. 需求与已确认决策

### 2.1 权限判定规则

登录管理台时调用的 `GET /ai/user/info` 响应体中携带权限字段：

- `result.isSuperAdmin == true`：拥有**超级管理员**权限；`false` 表示没有，字段一定不为 `null`。
- `result.isAISupporter == true`：拥有**超级管理员只读**权限；`false` 表示没有，字段一定不为 `null`。
- **允许跨租户查询条件**：`isSuperAdmin == true || isAISupporter == true`。

### 2.2 已确认核心决策

| 决策项 | 确认结论 |
| --- | --- |
| 代码仓库范围 | 仅修改 `cli-go`，不修改 `cli-python` |
| 交互方式与选项命名 | 命令级显式开关：`--all-business` / `-A`（不引入会话级“全部租户”上下文切换） |
| HTTP 请求头协议 | 开启 `--all-business` 时，HTTP 请求头 `businessid`（及 `ai-businessId`）**仍然保持当前选中的 `selected.businessId`** |
| POST 列表请求体协议 | 除 `ml service list` 外，其余 8 个 POST 列表接口开启 `-A` 时均直接将请求体中的 `businessId` 置为 `null`（Go `nil`），无其他特殊字段或枚举值；`ml service list` 的 `clusterBusinessId` **保持当前租户 `selected.businessId`，不允许置为 `null`** |
| GET 列表查询协议 | `ml offline experiment list` 开启 `--all-business` 时，Query 参数传 **`businessId=ALL`** |
| 首批覆盖范围 | 纳入全部 10 个顶层资源列表查询命令；明确排除 `ml featureset wide list`、`ml featureset model list`、`ml sample-task list`、`ml feature-task list` 及非顶层/无 `businessId` 列表 |
| 跨租户表格列展示 | 原本不含租户列的 6 个列表命令在开启 `-A` 时，动态追加列 **`("业务编码", "businessId")`**（显示名称统一为“业务编码”） |
| Web Studio JSON 输出 | 本次一并移除 `ml webstudio list` 的 `redactStudio` 脱敏逻辑，**普通查询与 `-A` 查询**在 `-o json` 下均直接输出服务端原始响应 JSON |
| `ml tree` 展示策略 | 按当前环境本地登录凭据权限**按需展示**：仅超级管理员/超级管理员只读可见顶部提示与 `支持 -A` 标记，普通用户与未登录用户完全无感知 |
| `--help` 展示策略 | 10 个命令的 `--help` 统一保留 `--all-business / -A` 选项展示，并在帮助说明中明确标注权限前提 |

---

## 3. 总体架构与数据流

```text
GET /ai/user/info
  ├─ result.isSuperAdmin  (bool)
  └─ result.isAISupporter (bool)
        │
        ▼ (Edge 登录捕获 / 旧凭据首次 -A 自动懒补全)
localstate.Credentials (credentials.json，按 profile 独立存储)
  ├─ IsSuperAdmin  *bool  `json:"is_super_admin,omitempty"`   // nil 表示旧版凭据未采集
  ├─ IsAISupporter *bool  `json:"is_ai_supporter,omitempty"`
  ├─ HasAdminFlags() bool
  ├─ CanQueryAllBusiness() bool
  └─ AdminRoleLabel() string
        │
        ▼
platform.Session.Authorize() -> *platform.API
  ├─ 在线权限服务 requireAccess() 仍上报 selected.businessId
  ├─ API.headers() 中 businessid 与 ai-businessId 固定保持 selected.businessId
  └─ API.RequireAllBusiness(ctx) error
        └─ 若凭据缺标志先调 /ai/user/info 补全并原子落盘；再校验 CanQueryAllBusiness()
        │
        ▼
catalogQuery（6 个列表命令统一复用）+ 4 个独立列表命令
  ├─ POST 接口：校验通过后自行传 nil（JSON null）
  ├─ GET 离线实验接口：校验通过后自行传 "ALL"（string，直接用于 query.Set）
  └─ 表格在 -A 模式下动态补充“业务编码”列
```

### 为什么不采用“会话级切换全部租户（如 `ml business use --all`）”？

1. **与现有契约冲突**：`cli-go` 的 `platform.API`、`requireAccess` 权限审计、`keepalive` 保活、`checkTarget()` 目标变更检测、`jupyter`/`webstudio` 上下文以及所有写操作均强依赖有效的单一 `selected.businessId`。
2. **防止误操作**：会话级状态容易忘切回；单次 `--all-business` / `-A` 保证默认操作始终处于当前租户安全边界内。
3. **白名单精确控制**：只对验证支持跨租户的 10 个只读列表命令注册 `-A` 标志，不支持的命令在 Cobra 参数解析层即拒绝。

---

## 4. 详细模块设计（基于 `cli-go`）

### 4.1 凭据模型与存储（`cli-go/internal/localstate`）

涉及文件：
- `cli-go/internal/localstate/business.go`
- `cli-go/internal/localstate/login.go`

#### 4.1.1 扩展 `Credentials` 结构体

在 `localstate/business.go` 的 `Credentials` 中新增两个指针字段：

```go
type Credentials struct {
	Origin        string          `json:"platform_origin"`
	StateID       string          `json:"state_id"`
	Profile       string          `json:"profile"`
	Username      string          `json:"username"`
	Cookie        string          `json:"cookie"`
	CSRFToken     string          `json:"csrftoken"`
	AcquiredAt    json.RawMessage `json:"acquired_at,omitempty"`
	ChineseName   string          `json:"cn_name,omitempty"`
	Department    string          `json:"department,omitempty"`
	IsSuperAdmin  *bool           `json:"is_super_admin,omitempty"`
	IsAISupporter *bool           `json:"is_ai_supporter,omitempty"`
	ExpiresAt     json.RawMessage `json:"expires_at"`
}
```

使用 `*bool` 精确区分三种状态：`nil`（旧版 `credentials.json` 尚未采集）、`true`、`false`，完全兼容历史本地缓存文件。

新增辅助方法：
- `func (c Credentials) HasAdminFlags() bool`：`c.IsSuperAdmin != nil && c.IsAISupporter != nil`
- `func (c Credentials) CanQueryAllBusiness() bool`：`(c.IsSuperAdmin != nil && *c.IsSuperAdmin) || (c.IsAISupporter != nil && *c.IsAISupporter)`
- `func (c Credentials) AdminRoleLabel() string`：
  - `IsSuperAdmin == true` → `"超级管理员"`
  - `IsAISupporter == true` → `"超级管理员（只读）"`
  - `HasAdminFlags()` → `"普通用户"`
  - 其他 → `"未获取"`

#### 4.1.2 原子回写权限标志（保护 `StateID` 一致性）

在 `localstate/login.go` 新增 `Paths.UpdateAdminFlags(profile, stateID, username string, superAdmin, aiSupporter bool) error`：
- 获取 `p.LockState()` 锁；
- 读取 `credentials.json`，仅当 `entry.Profile == profile && entry.StateID == stateID && entry.Username == username` 时，原地更新 `IsSuperAdmin` 与 `IsAISupporter` 并调用 `writeState()` 写回；
- **不改变 `StateID`**，避免破坏与 `business.json` 及多会话状态的一致性。

---

### 4.2 Edge 登录解析与认证状态展示

涉及文件：
- `cli-go/internal/edgelogin/session.go`
- `cli-go/internal/edgelogin/edge.go`
- `cli-go/internal/command/command.go`（`ml login` 结果输出）
- `cli-go/internal/command/auth.go`（`ml auth status` 输出）

1. **`edgelogin/session.go`**：
   - 在 `userInfo` 结构体和 `parseUserInfo(body []byte)` 中增加解析：
     ```go
     IsSuperAdmin  *bool `json:"isSuperAdmin"`
     IsAISupporter *bool `json:"isAISupporter"`
     ```
   - 在 `awaitLogin()` 组装 `localstate.Credentials` 时写入 `IsSuperAdmin`、`IsAISupporter`。
2. **`edgelogin/edge.go` 与 `ml login`**：
   - `edgelogin.Summary` 新增 `AdminRole string`（取 `creds.AdminRoleLabel()`），`ml login` 成功汇总表增加展示权限角色。
3. **`command/auth.go`**：
   - `ml auth status` 的 `output.Fields` 中新增 `{Key: "role", Value: creds.AdminRoleLabel()}`，方便用户和排障直接核对当前环境账号权限。

---

### 4.3 `platform.API` 统一查询上下文抽象

涉及文件：
- `cli-go/internal/platform/session.go`

#### 4.3.1 请求头严格不变

`API.headers()` 保持现有实现不变：
- `headers.Set("businessid", a.businessID)`（经由 `a.metadata.headers(a.businessID)`）
- `headers.Set("ai-businessId", a.businessID)`

#### 4.3.2 新增统一权限校验方法 `RequireAllBusiness` 与旧凭据懒补全

公共方法只负责校验跨租户查询权限（及旧凭据自动补全），**不返回 `any`**，由各接口按自身协议类型安全地填入 JSON `nil` 或 Query 字符串 `"ALL"`，避免 `url.Values.Set` 等场景的类型断言或编译错误。

在 `platform/session.go` 新增方法：

```go
// RequireAllBusiness 校验当前账号是否具备超级管理员或超级管理员只读权限。
// 若本地旧凭据尚未采集权限标志，会先调用 /ai/user/info 补全并原子回写。
func (a *API) RequireAllBusiness(ctx context.Context) error {
	if !a.credentials.HasAdminFlags() {
		if err := a.refreshAdminFlags(ctx); err != nil {
			return err
		}
	}
	if !a.credentials.CanQueryAllBusiness() {
		return errors.New("当前账号不具备超级管理员或超级管理员只读权限，不支持使用 --all-business 跨租户查询")
	}
	return nil
}
```

调用方式示例：
- **POST JSON 列表接口**：
  ```go
  var queryBusinessID any = api.BusinessID()
  if allBusiness {
      if err := api.RequireAllBusiness(ctx); err != nil {
          return err
      }
      queryBusinessID = nil
  }
  body["businessId"] = queryBusinessID
  ```
- **GET 离线实验列表接口（强类型 `string`）**：
  ```go
  queryBusinessID := api.BusinessID()
  if allBusiness {
      if err := api.RequireAllBusiness(ctx); err != nil {
          return err
      }
      queryBusinessID = "ALL"
  }
  query.Set("businessId", queryBusinessID)
  ```

`refreshAdminFlags(ctx)` 实现要点：
- 调用 `a.JSON(ctx, http.MethodGet, "/ai/user/info", nil, nil)`；
- 校验 `result.code == 0` 并解析 `isSuperAdmin` 与 `isAISupporter`（必须为布尔值，缺失则按 `false` 处理并报错或提示重新登录）；
- 更新内存中的 `a.credentials.IsSuperAdmin`、`a.credentials.IsAISupporter`，并调用 `a.session.Paths.UpdateAdminFlags(...)` 静默落盘（落盘失败不阻断本次只读查询，仅保持本次内存生效）。

> 注：即使本地缓存显示有权限、但后台刚刚收回权限，服务端拒绝时仍通过正常 `API.JSON` / `platform.Result` 报错透出，服务端始终是最终权限权威。

#### 4.3.3 在线权限服务校验与审计边界（已知限制）

开启 `--all-business` / `-A` 后，CLI 调用在线权限服务（`access-service`）时**仍仅基于当前选中的租户（`selected.businessId`）进行校验与上报**：

- **版本准入规则范围**：假设当前选中租户 `A`，使用 `-A` 查出了租户 `B` 的列表数据，现有权限服务**只会检查租户 `A` 对应的业务级版本规则**，不会对结果中涉及的租户 `B` 单独执行业务级版本准入检查。
- **审计日志归属**：权限服务记录的调用审计中，**`business_id` 字段仍只记录当前选中的租户 `A`**（不会拆分或替换为租户 `B`）；命令行审计字段 `full_command` 会保留 `--all-business` / `-A`，可用于事后识别该次请求属于跨租户列表查询。
- **风险评估与演进边界**：该能力仅对具备平台超级管理员或超级管理员只读权限的少数人员开放，且严格限定于只读列表查询；本期不修改权限服务协议与数据库结构，如后续需要按跨租户维度单独做审计统计或版本策略控制，再作为权限服务增强需求独立演进。

---

### 4.4 全量列表命令覆盖清单与实现方式

所有 10 个纳入命令统一注册 Cobra 标志：

```go
cmd.Flags().BoolP("all-business", "A", false, "在全部租户中查询（需超级管理员或超级管理员只读权限）")
```

*(已全仓检索 `cli-go/internal/`，短选项 `-A` 无任何冲突。)*

#### 4.4.1 `catalogQuery` 统一支持（覆盖 6 个命令）

在 `cli-go/internal/command/catalog_query.go` 中：
- `catalogQuery` 结构体新增：
  - `allowAllBusiness bool`：开启后在 `build()` 中自动注册 `--all-business` / `-A` 标志；
  - `appendBusinessColumn bool`：当该命令默认表格列不含 `businessId` 且本次执行传入 `-A` 时，在 `render()` 中动态追加 `recordColumn{title: "业务编码", key: "businessId"}`。
- `withBusiness` 辅助函数升级为读取 `allBusiness, _ := cmd.Flags().GetBool("all-business")`：开启时调用 `api.RequireAllBusiness(cmd.Context())` 校验权限并将 `body["businessId"] = nil`，否则赋值为 `api.BusinessID()`。
- 仅 `catalogQuery` 一处改造即可干净覆盖 6 个列表命令中的大部分逻辑。

#### 4.4.2 纳入范围明细（共 10 个顶层列表查询命令）

| # | CLI 命令 | 实现文件 | 接口与方法 | 开启 `-A` 时请求参数 | 特殊约束 / 适配点 | 表格“业务编码 / 租户”列 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `ml service list` | `command/service.go` (`catalogQuery`) | `POST /ai/backend/mep/services/queryList` | `body.businessId = null` | **`body.clusterBusinessId` 必须保持 `api.BusinessID()`，不允许置为 `null`**；`headers.businessid` 保持 `selected.businessId` | `-A` 时动态追加 `("业务编码", "businessId")` |
| 2 | `ml model list` | `command/model.go` (`catalogQuery`) | `POST /ai/backend/mep/models/queryList` | `body.businessId = null` | 直接复用 `withBusiness` | 已有（`业务编码`） |
| 3 | `ml dataset list` | `command/dataset.go` (`catalogQuery`) | `POST /ai/backend/mtp/dataSet/queryList` | `body.businessId = null` | 复用 `withBusiness` | 已有（`租户`） |
| 4 | `ml train list` | `command/train.go`<br>`platform/train.go` | wiserec: `POST /ai/backend/modelDev/modelTrain/list`<br>mlops: `POST /ai/backend/mtp/traintask/queryList` | wiserec: `body.data.businessId = null`<br>mlops: `body.businessId = null` | `api.TrainList` 增加 `allBusiness bool` 参数（双管理台共用 `data["businessId"]`）；`TrainTask()` 内部查找默认传 `false` 不受影响 | `-A` 时动态追加 `("业务编码", "businessId")` |
| 5 | `ml algorithm list` | `command/algorithm.go` (`catalogQuery`) | `POST /ai/backend/modelDev/algorithmWarehouse/list` | `body.data.businessId = null` | 自定义 `body` 中开启 `-A` 时调 `api.RequireAllBusiness` 后设 `body["businessId"] = nil` | `-A` 时动态追加 `("业务编码", "businessId")` |
| 6 | `ml deployment template list` | `command/templates.go` (`catalogQuery`) | `POST /ai/backend/mep/scm/deploytemplate/queryList` | `body.businessId = null` | 直接复用 `withBusiness` | 已有（`业务编码`） |
| 7 | `ml resource template list` | `command/templates.go` (`catalogQuery`) | `POST /ai/backend/mep/resourcetemp/queryList` | `body.businessId = null` | 直接复用 `withBusiness` | 已有（`业务编码`） |
| 8 | `ml webstudio list` | `command/studio.go`<br>`jupyter/studio.go` | `POST /ai/backend/webstudio/dataExplorer/queryEnvList` | `body.businessId = null` | 1. **互斥校验**：同时传入 `--all-business` 与 `--business-id` 时返回 `usageError`；<br>2. `jupyter.StudioListBody` 的 `businessID` 参数类型由 `string` 改为 `any` 以支持序列化 `null`；<br>3. 移除 `redactStudio` 脱敏逻辑，普通查询与 `-A` 查询均直接输出服务端原始响应 | `-A` 时动态追加 `("业务编码", "businessId")` |
| 9 | `ml mtp swanboard project list` | `command/swanboard.go` | `POST /ai/backend/mtp/swanboard/project/list` | `body.businessId = null` | 仅挂载在 `projectList`；开启 `-A` 时调 `api.RequireAllBusiness` 后设 `businessId = nil` | `-A` 时动态追加 `("业务编码", "businessId")` |
| 10 | `ml offline experiment list` | `command/offline.go` | `GET /ai/backend/experiment/project/list` | **Query `businessId=ALL`** | 仅 `trial == false` 时注册 `-A`；开启 `-A` 时调 `api.RequireAllBusiness` 后设 `query.Set("businessId", "ALL")` | `-A` 时动态追加 `("业务编码", "businessId")` |

#### 4.4.3 明确排除的列表命令

1. **按业务需求明确排除**：
   - `ml featureset wide list`
   - `ml featureset model list`
   - `ml sample-task list`
   - `ml feature-task list`，仅查询当前业务
2. **请求体本身不含 `businessId` 字段（仅靠请求头 `businessid` 隔离）**：
   - `ml quality feature list`
   - `ml quality wide-featureset list`
3. **绑定具体父资源 ID 的子资源列表**（非全租户检索，本批不纳入）：
   - `ml service host list`、`ml service deployment list`
   - `ml train instance list`、`ml train history list`
   - `ml offline experiment trial list`
   - `ml mtp swanboard project namespace list`、`ml mtp swanboard project experiment list`、`ml mtp swanboard experiment feature list`、`ml mtp swanboard experiment config list`
   - `ml dataset files list`
   - `ml feature-task execution list`
   - `ml sample-task period list`、`ml sample-task execution list`
   - `ml quality ... assembly list` / `feature list`
4. **本地/非租户列表**：
   - `ml env list`、`ml business list`、`ml history list`、`ml jupyter terminal list`、`ml jupyter files list`

---

### 4.5 表格展示与 `ml tree` / `--help` 设计

#### 4.5.1 表格与 JSON 输出规范
1. **默认单租户模式兼容性**：不传 `-A` 时，所有 10 个命令的表格列顺序和列标题与当前完全一致；JSON 输出方面，除 **`ml webstudio list -o json` 本次主动移除 `redactStudio` 脱敏、改为直接输出服务端原始 JSON** 外，其余 9 个命令与当前完全一致。
2. **跨租户模式动态补充“业务编码”列**：对原本不含 `businessId` 列的 6 个命令（`service`、`train`、`algorithm`、`webstudio`、`mtp swanboard project`、`offline experiment`），开启 `-A` 且输出格式为 `table` 时，动态追加 `("业务编码", "businessId")` 列（空值展示 `-`）。
3. **首列 ID 规范**：继续沿用 `cli-go` 现有首列 36 字符固定宽度、不换行、不截断规范。
4. **JSON 输出细则**：
   - **`ml webstudio list -o json`**：本次移除 `redactStudio` 脱敏逻辑并清理无用函数，**普通查询与 `-A` 查询**均直接输出服务端原始响应 JSON（不再将字段值替换为 `[REDACTED]`）。**输出前仍必须按现有规则校验响应**：先通过 `platform.Result` 检查业务结果码（`code == 0`），并校验 `result.envs`（有效记录数组）与 `result.count`（非负整数），全部校验通过后再输出未经脱敏的 JSON；接口报错或结构异常时 CLI 仍退出失败，确保调用脚本可继续依赖退出码判断查询是否成功。注意：移除脱敏属于有意行为调整，会影响依赖原脱敏输出的脚本，且响应中若含凭据/链接类字段将原样输出，须在使用手册与发布说明中明确提示。
   - **`ml offline experiment list -o json`**：不带 `-A` 时字段集合与现有实现完全一致；开启 `-A` 时在过滤字段集合中补充保留 `businessId` 字段。
   - 其余 8 个列表命令的 JSON 输出与现有实现保持一致。

#### 4.5.2 `ml tree` 与 `--help` 展示设计

涉及文件：`cli-go/internal/command/tree.go`

1. **`ml tree` 按本地有效凭据权限离线按需展示**：
   - `writeTree()` 继续保持完全离线（不发网络请求）。在成功解析 `profile` 后，通过带本地有效期校验的 **`paths.LoadCredentials(profile, time.Now())`** 只读加载当前环境的有效凭据（若未登录、缓存缺失、格式无效或**凭据已过期**，均静默降级为普通用户视角，避免将过期账号误展示为当前有权限）。
   - **普通用户 / 未登录用户 / 凭据已过期 / 会话未绑定环境 / 老凭据未采集权限标志**：`ml tree` 输出与当前完全一致，不展示任何 `-A` 标记，避免对绝大多数用户造成干扰。
   - **超级管理员 / 超级管理员只读用户（`creds.CanQueryAllBusiness() == true`）**：
     - 顶部环境信息区追加一行提示：
       `当前账号权限：<角色名> · 标记“支持 -A”的列表命令可使用 --all-business / -A 查全租户`
     - 在 `treeBranches()` 中，对拥有 `child.Flags().Lookup("all-business") != nil` 的叶子命令（自动从 Cobra 标志识别，避免维护重复白名单），且未被标记为 `[不支持]` 或 `[当前环境禁用]` 时，在行尾追加 `  支持 -A`（结尾无标点，严格符合命令树格式规范）。
     - **按管理台区分预期（前提：当前环境未通过本地或服务端策略禁用相关命令）**：
       - **WiseRec 管理台**：未禁用时，全部 **10 个**列表命令均展示 `支持 -A`。
       - **MLOps 管理台**：未禁用时，仅当前平台支持的 **7 个**列表命令展示 `支持 -A`（`service list`、`model list`、`dataset list`、`train list`、`deployment template list`、`resource template list`、`webstudio list`）；仅 WiseRec 支持的 3 个命令（`algorithm list`、`mtp swanboard project list`、`offline experiment list`）在 `ml tree` 中自动隐藏，在 `ml tree --all` 中仅显示 `[不支持]`、不叠加 `支持 -A`。
       - 若上述任意命令被当前环境策略禁用，则该命令在 `ml tree` 中隐藏、在 `ml tree --all` 中仅显示 `[当前环境禁用]` 且不叠加 `支持 -A`，实际展示 `支持 -A` 的数量相应减少。
   - 效果示意（超级管理员视角）：
     ```text
     当前环境：wiserec · 管理台类型：wiserec
     当前账号权限：超级管理员 · 标记“支持 -A”的列表命令可使用 --all-business / -A 查全租户
     仅展示当前环境支持的命令；查看全部命令：ml tree --all
     ml  WiseRec 命令行工具
     ├── service  服务查询、模拟调用与主机诊断
     │   └── list  分页查询当前业务的服务  支持 -A
     ├── featureset  特征集查询
     │   └── wide
     │       └── list  分页查询宽表特征集
     ```
2. **`--help` 展示策略**：
   - 10 个命令的 `--help` 统一保留 `--all-business` / `-A` 选项展示，并写明帮助文案：`在全部租户中查询（需超级管理员或超级管理员只读权限）`，保持 CLI 帮助、使用手册与 Skill 一致。

---

## 5. 边界与异常处理

| 场景 | 预期行为 |
| --- | --- |
| 普通用户（`isSuperAdmin=false` 且 `isAISupporter=false`）传入 `-A` | 客户端前置拦截，不发业务列表请求，输出明确中文提示并退出码 1 |
| 仅 `isAISupporter=true`（超管只读）传入 `-A` | 放行，正常执行跨租户只读列表查询 |
| 仅 `isSuperAdmin=true`（超管）传入 `-A` | 放行，正常执行跨租户列表查询 |
| 老版本 `credentials.json`（缺少权限字段）首次传入 `-A` | 自动请求 `GET /ai/user/info` 补全权限标志并在 `LockState` 下按 `StateID` 原子回写，再判定权限 |
| 后台已收回超管权限，但本地缓存仍为 `true` | 请求发出后由服务端拒绝，CLI 按正常接口错误展示 |
| `ml webstudio list -A --business-id xxx` | 参数校验阶段返回 `usageError`：`--all-business 与 --business-id 不能同时使用` |
| `ml service list -A` | `body.businessId` 为 `null`，`body.clusterBusinessId` 保持 `selected.businessId`，Header `businessid` 保持 `selected.businessId` |
| `ml offline experiment list -A` | Query 参数为 `businessId=ALL`，Header `businessid` 保持 `selected.businessId` |
| 未选择当前租户时传入 `-A` | 在 `Authorize()` 阶段提示先执行 `ml business use`（因请求头 `businessid` 和 `clusterBusinessId` 仍需有效 `selected.businessId`） |
| 选中租户 A 后用 `-A` 查到租户 B 的数据 | 权限服务仍按租户 A 检查业务级版本规则，审计日志中的 `business_id` 也只记录租户 A（`full_command` 保留 `-A` / `--all-business` 标识） |
| 跨租户查到其他租户资源 ID 后需查详情或操作 | 用户可通过表格“业务编码”列确认归属租户，按需 `ml business use` 切换后再执行后续命令 |

---

## 6. 配套交付与验证计划（实施阶段）

### 6.1 模块与代码规范
- 仅修改 `cli-go/`，不修改 `cli-python/`。
- 遵守单文件规模规范（原则上 `< 500 LoC`，接近 `800 LoC` 须拆分）。

### 6.2 Go 单元测试计划（`go test ./...`）
1. **凭据与登录解析单测**（`internal/localstate`、`internal/edgelogin`）：
   - `parseUserInfo` 对 `isSuperAdmin` / `isAISupporter` 四种布尔组合及缺失字段的解析。
   - `Credentials` JSON 序列化/反序列化（兼容旧版无权限字段缓存）、`CanQueryAllBusiness()`、`AdminRoleLabel()`。
   - `UpdateAdminFlags` 仅在 `Profile`、`StateID`、`Username` 匹配时原子更新且不改 `StateID`。
   - `ml auth status` 展示 `role` 字段。
2. **`platform.API.RequireAllBusiness` 与懒补全单测**（`internal/platform`）：
   - 普通用户前置阻断返回 error 且不发业务列表请求；超管/超管只读校验通过返回 `nil`。
   - 旧凭据缺失标志时自动调 `/ai/user/info` 补全并落盘，随后按真实权限放行或阻断。
3. **10 个列表命令端到端单测**（`internal/command`）：
   - 逐一验证 `-A` 下 HTTP Header `businessid` 与 `ai-businessId` 保持 `selected.businessId`。
   - 验证 POST 类命令请求体 `businessId` 为 JSON `null`；重点验证 `service list` 的 `clusterBusinessId` 保持 `selected.businessId`、`train list` 在 `wiserec` 与 `mlops` 双管理台分支均正确。
   - 验证 `ml offline experiment list -A` 的 Query 参数 `businessId=ALL`。
   - 验证 `ml webstudio list -A --business-id xxx` 返回互斥参数错误。
   - 验证 `ml webstudio list -o json`（含普通查询与 `-A` 查询）在业务结果码、`envs` 与 `count` 校验通过后直接输出服务端原始字段（不再替换为 `[REDACTED]`），并在业务报错或响应结构异常时仍返回失败退出码。
   - 验证原本无租户列的 6 个命令在 `-A` 下表格包含“业务编码”列，非 `-A` 下原有列结构不变。
4. **`ml tree` 展示单测**（`internal/command`）：
   - 未登录、普通用户或**凭据已过期**的超管账号执行 `ml tree`：完全离线且不出现 `支持 -A` 与权限提示行。
   - **WiseRec 管理台**下（无禁用命令前提），有效超管或超管只读凭据执行 `ml tree`：顶部展示权限提示、全部 **10 个**支持命令带 `支持 -A` 标记且结尾无标点；被排除命令（`featureset wide/model list`、`sample-task list`、`feature-task list`、`quality` 等）不带标记。
   - **MLOps 管理台**下（无禁用命令前提），有效超管或超管只读凭据执行 `ml tree`：仅 **7 个** MLOps 支持的列表命令带 `支持 -A` 标记；`ml tree --all` 中仅 WiseRec 支持的 3 个命令（`algorithm list`、`mtp swanboard project list`、`offline experiment list`）仅显示 `[不支持]`，不叠加 `支持 -A`。
   - 当环境策略禁用其中部分列表命令时，`ml tree` 隐藏被禁用命令且展示 `支持 -A` 的数量相应减少，`ml tree --all` 中被禁用命令仅显示 `[当前环境禁用]`，不叠加 `支持 -A`。

### 6.3 真实环境接口联调验收

单元测试仅验证 CLI 发出了预期的请求头、`null` 或 `ALL`（例如即使服务端因 `clusterBusinessId` 仍将结果限制在当前租户，单测也会通过），因此合入与发布前必须完成真实管理台联调验收：

1. **同名服务跨租户核心验收（WiseRec & MLOps 两套管理台）**：
   - 在两套管理台分别准备两个不同租户（租户 A、租户 B）下的同名服务；
   - 使用超管与超管只读账号，选中租户 A 后分别执行 `ml service list --name <同名服务>`（仅见租户 A）与 `ml service list --name <同名服务> -A`；
   - 核对 `-A` 结果同时返回租户 A 与租户 B 的服务记录、“业务编码”列分别准确显示 A/B、且分页总数（`total`）与跨租户真实总数一致（验证 `clusterBusinessId` 保持当前租户 A 时不会被服务端错误过滤回单租户）。
2. **其余 9 个列表接口真实验收**：
   - 按各命令支持的管理台范围（WiseRec 覆盖全部 10 个命令、MLOps 覆盖支持的 7 个命令），分别在真实环境执行 `-A` 查询，核对跨租户记录返回、“业务编码”列展示（含 4 个已有列和 6 个动态追加列）以及分页总数；
   - **分页总数专项验收口径（离线实验与训练看板）**：`ml offline experiment list`（`offline.go`）与 `ml mtp swanboard project list`（`swanboard.go`）在服务端未返回总数时，当前实现会回退使用本页条数填充计数字段。真实验收时须核对接口是否实际返回跨租户总数，并使用较小页大小（如 `--page-size 1` 或 `2`）验证 `--page 1` / `--page 2` 翻页结果，避免把“本页条数”误判为“跨租户总数”；
   - 重点验证 `ml offline experiment list -A`（Query `businessId=ALL`）在 WiseRec 下的真实返回与 `-o json` 中的 `businessId` 字段；
   - 验证 `ml webstudio list -o json`（含普通查询与 `-A` 查询）先校验响应码及结构再直接返回服务端原始 JSON（无 `[REDACTED]` 脱敏替换）。
3. **普通账号服务端拒绝验收**：
   - 确认普通账号在 CLI 侧被前置拦截；同时通过真实接口验证平台服务端本身也会拒绝普通账号的跨租户请求（防止仅靠客户端校验产生安全依赖）。
4. **验收记录规范**：
   - 发布说明与测试记录中须如实区分“已完成本地单测”与“已完成真实管理台联调验收”，未完成真实联调的接口不得宣称已全量验证。

### 6.4 文档与 Skill 同步
1. 更新 `docs/WiseRec CLI 使用手册.md`：在对应 10 个列表命令章节的“参数与选项”“说明”“示例”中补充 `--all-business` / `-A` 说明与使用前提（不写入版本信息）。
2. 检查并更新 `skill/` 下相关指引及 `scripts/skill_index/commands.md.in`，执行：
   ```bash
   python scripts/sync_skill_index.py
   python scripts/sync_skill_index.py --check
   ```
3. 执行 `ml tree` 核对实际命令树输出，确认所有层级说明结尾无标点。
