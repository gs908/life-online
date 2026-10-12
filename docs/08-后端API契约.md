# 08. 后端 API 契约（唯一事实来源）

> **本文档由 `server/app/api/v1/` 路由与 `server/app/schemas/` Pydantic schema 逐文件核对生成（基准：develop@09cf8fc，2026-10-09）。**
> 前后端联调一律以本文档为准；与本文档冲突的任何前端类型、Mock 数据、旧文档（含 `06-API设计要点.md`）均以本文档为准。
> 后端代码变更时必须同步更新本文档（见 `09-前后端类型对齐与Mock映射.md` 的变更流程）。
> 可对照运行时 OpenAPI：`http://host:8000/docs`。

---

## 0. 通用约定

### 0.1 路径前缀

所有路由挂载在 `/api/v1` 下。资源前缀：`sys_*`（身份/账号类）、`scn_*`（业务场景类）。

### 0.2 响应包裹（实际代码，非旧文档描述）

所有接口（含错误）返回统一包裹 `ApiResponse<T>`（`app/schemas/common.py`）：

```jsonc
// 成功
{ "code": 0, "data": <T>, "msg": "" }
// 失败（全局异常处理器 app/middleware/__init__.py）
{ "code": 1, "data": { "error_code": "<machine_code>" }, "msg": "<human message>" }
```

> ⚠️ 旧文档 `06-API设计要点.md` 写的 `{ ok: true, data } / { ok: false, error: {...} }` **与代码不符，作废**。前端请按 `code === 0` 判定成功。

### 0.3 鉴权

- `Authorization: Bearer <access_token>`（JWT，`type=access`）。
- 获取：`POST /sys/auth/wechat/jscode`（微信小程序）、`POST /sys/auth/password/login`（网页端账号密码，H5/浏览器）、`POST /sys/auth/password/register`（网页端邀请码注册并登录）或 `POST /sys/auth/refresh`（刷新）。
- 角色守卫：`GUILD_MASTER`（父母）专属接口下表标注「父母」；其余为登录用户（CurrentUser）可访问。

### 0.4 分页约定

- 请求：`?page=1&page_size=20`，`page >= 1`，`1 <= page_size <= 200`。
- 响应：`PageResult<T> = { "items": [T], "total": int, "page": int, "page_size": int }`。
- 未分页的列表接口直接返回数组。

### 0.5 错误码表（`app/common/exceptions.py`）

| HTTP | error_code | 含义 | 前端处理建议 |
|------|-----------|------|-------------|
| 401 | `unauthorized` | 未登录 / token 过期或无效 | 跳登录或尝试 refresh |
| 403 | `permission_denied` | 角色/越权（如孩子调父母接口、跨家庭资源） | 提示无权限 |
| 404 | `not_found` | 资源不存在 | 提示并刷新列表 |
| 409 | `conflict` | 状态冲突（如重复接取） | 提示冲突信息 |
| 422 | `validation_error` | 请求参数校验失败（`data` 为 pydantic errors 数组） | 表单纠错 |
| 429 | `rate_limited` | 触发限流（当前仅密码登录/改密：同一用户名窗口期内失败次数超限） | 提示等待后重试 |
| 502 | `external_service_error` | LLM / 微信 / 存储外部失败 | 提示稍后重试 |
| 500 | `app_error` / 其他 | 内部错误 | 提示联系支持 |

### 0.6 命名与类型

- JSON 字段一律 **snake_case**。
- 时间：`datetime` → ISO 8601 字符串（UTC）；`date` → `YYYY-MM-DD`；`time`（如 `required_start_time`）→ `"HH:MM:SS"`。
- 枚举值全大写字符串（`TaskType` 等，见各 DTO）。

---

## 1. health

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/api/v1/health` | ping，返回 `{status,name,version,debug}` | 无 |
| GET | `/api/v1/health/ready` | 就绪探针 `{ready: true}` | 无 |

## 2. 认证 `/sys/auth`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| POST | `/sys/auth/wechat/jscode` | 小程序 code 换 token | 无 |
| POST | `/sys/auth/password/login` | 网页端账号密码登录（H5/浏览器） | 无 |
| POST | `/sys/auth/password/register` | 网页端用邀请码注册并登录 | 无 |
| PUT | `/sys/auth/password/me` | 修改/设置自己的登录密码 | 登录 |
| POST | `/sys/auth/refresh` | refresh_token 换新 token 对 | 无 |
| POST | `/sys/auth/dev-login` | 开发环境非微信登录（仅 `DEV_LOGIN_ENABLED=true`） | 无 |
| POST | `/sys/auth/logout` | 登出（仅日志，客户端清 token） | 登录 |
| GET | `/sys/auth/me` | 当前用户 `UserRead` | 登录 |

**WechatJscodeRequest** `{ code: str, nickname?: str, avatar_url?: str }`
**PasswordLoginRequest** `{ username: str (3-32, `[A-Za-z0-9_]`, 大小写不敏感), password: str (8-128) }`
**PasswordRegisterRequest** `{ code: str, username: str, password: str, nickname?: str, avatar?: str = "⚔️" }`
**PasswordChangeRequest** `{ new_password: str, old_password?: str, username?: str }`（已有密码渠道必须带 `old_password`；首次设置必须带 `username`）
**RefreshRequest** `{ refresh_token: str }`
**DevLoginRequest** `{ role?: "GUILD_MASTER" \| "ADVENTURER" = "ADVENTURER", name?: str }`
**TokenPair** `{ access_token, refresh_token, token_type: "Bearer", access_expires_in: int, refresh_expires_in: int }`
> 微信登录若 openid 无账号，返回业务错误要求邀请码流程（`NeedInviteCodeError` → 走 `/sys/families/join`）。

**password 通道语义**（DEV-22，实现唯一事实来源：`server/app/api/v1/auth.py`、`server/app/services/password_service.py`、`server/app/common/security/password.py`、模型 `sys_channel_password`）：

- 凭据存 `sys_channel_password` 渠道表（与 `sys_channel_wechat` 并列），一账号至多一条；密码 scrypt 哈希（N=2^15, r=8, p=1，标准库实现，无明文）。微信注册的已有账号可经 `PUT /sys/auth/password/me` 补设密码（首次设置需带 `username`），多渠道并存互不影响。
- `username` 全表唯一、统一小写存储（登录大小写不敏感）；`POST /password/register` 与小程序侧 `/sys/families/join` 同语义：消费一张邀请码创建账号并直接返回 `TokenPair`（邀请码无效/已用/过期 → 404/409，与 join 一致）。
- 登录失败统一 401 `unauthorized`「用户名或密码错误」，不区分用户不存在与密码错误（防用户名枚举）；用户不存在时服务端也对固定 dummy 哈希做一次等参数 scrypt 校验，消除与密码错误路径（约 100ms）的可测时间差（DEV-26）。同一用户名在窗口期内（默认 15 分钟）失败超过 `AUTH_LOGIN_MAX_ATTEMPTS`（默认 5）次后返回 429 `rate_limited`。限流为进程内计数（重启清零、多 worker 各自计数；计数字典设容量上限 10000——条目仅在记录失败时创建，超限检查只读不写入，满时先清扫窗口外条目、仍满则丢弃兜底，防不存在用户名喷射撑爆内存），Redis 接入后可升级为全局精确计数。
- 通道开关：`AUTH_PASSWORD_LOGIN_ENABLED`（默认 `true`，生产可用）；关闭时 login/register 返回 503 `service_unavailable`。**`PUT /sys/auth/password/me` 同受此门禁**（DEV-26 口径）：该端点内含 `old_password` 在线校验（爆破面），且首次设置会写入登录 username（注册语义），关闭密码通道即整体冻结密码凭据面，不留下"能设密码却不能登录"的半开状态（已登录用户在通道关闭时调用亦得 503）。与 `DEV_LOGIN_ENABLED`（默认 `false`，仅开发环境）互不相关。
- scrypt 校验内存上限（maxmem）按存储串中的 N·r 动态计算（需求约 128·N·r，取 2 倍余量），并对 N（2^14–2^20，须为 2 的幂）、r（1–32）、p（1–8）做合理性校验：未来把哈希参数 N 提到 2^17 时存量哈希验证不受影响，同时防存储串被篡改后触发巨型分配（DEV-26）。
- 返回标准 `TokenPair`（复用 `auth_service.issue_token_pair`），refresh / 鉴权链路与微信登录完全一致。

**dev-login 语义**（实现唯一事实来源：`server/app/api/v1/auth.py`、`server/app/dev/login.py`、`server/app/schemas/token.py::DevLoginRequest`）：

- 仅供开发/测试环境使用：仅当服务端 `DEV_LOGIN_ENABLED=true` 时可用；为 `false`（生产默认）时返回 `permission_denied`（403），msg 提示"开发登录未启用(DEV_LOGIN_ENABLED=false),生产环境禁止使用"。**生产环境禁止开启。**
- 按角色获取（首次调用则创建）固定的开发测试账号，幂等：同一角色重复登录返回同一账号，不堆叠新家庭/账号。所有 dev 账号挂在名为"开发环境"的家庭下；`GUILD_MASTER` 返回该家庭 owner（`name` 参数被忽略，固定"开发家长"）；`ADVENTURER` 返回家庭内第一个冒险者（不存在则用 `name` 创建，默认"开发孩子"）。
- 返回标准 `TokenPair`，后续走与微信登录完全相同的刷新/鉴权链路。

## 3. 账号 `/sys/accounts`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/sys/accounts/me` | 当前账号；冒险者触发每日重置（津贴发放、abandon 清零） | 登录 |
| PATCH | `/sys/accounts/me` | 更新自己 | 登录 |
| POST | `/sys/accounts/adventurers` | 直接创建孩子冒险者账户 | 父母 |

**UserRead**（后端用户唯一形状）：

```jsonc
{
  "id": "str",                // 账号 ID
  "family_id": "str",
  "role": "GUILD_MASTER | ADVENTURER",
  "name": "str",
  "avatar": "str",
  "locale": "zh-CN",
  "child_id": "str | null",   // 冒险者扩展档案 ID（父母为 null）
  "level": 1,                 // 父母固定 1
  "xp": 0,
  "time_coins": 0,            // 冒险者时间币余额
  "daily_abandon_count": 0,
  "last_login_date": "YYYY-MM-DD | null",
  "current_season_id": "str | null",
  "privileges_unlocked": ["str"],   // 已解锁特权模板 ID 列表
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

**UserUpdate**（PATCH body，均可选）：`name, avatar, locale, time_coins, level, xp, current_season_id`（`privileges_unlocked` 目前被忽略）。
**AdventurerCreate** `{ name: str, avatar?: str = "⚔️" }`

## 4. 家庭 `/sys/families`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| POST | `/sys/families` | 创建家庭（含首个 GUILD_MASTER） | 无 |
| GET | `/sys/families/me` | 我的家庭成员 | 登录 |
| POST | `/sys/families/invites` | 生成邀请码 | 父母 |
| POST | `/sys/families/join` | 用邀请码加入 | 无 |

**FamilyRead** `{ id, name, owner_id, created_at }`
**FamilyMembersRead** `{ family: FamilyRead, guild_masters: [UserRead], adventurers: [UserRead] }`
**FamilyInviteCreate** `{ role?: "GUILD_MASTER"|"ADVENTURER" = "ADVENTURER", expires_in_hours?: int = 72 (1–720) }`
**FamilyInviteRead** `{ id, family_id, code, role, created_by, expires_at, used_at, used_by }`
**FamilyJoinRequest** `{ code, nickname, avatar?, openid, unionid? }`

## 5. 赛季 `/scn/seasons`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/scn/seasons?include_inactive=true` | 本家庭赛季列表 | 登录 |
| GET | `/scn/seasons/active` | 当前激活赛季（无则 `data: null`） | 登录 |
| GET | `/scn/seasons/history` | 赛季历史统计 | 登录 |
| GET | `/scn/seasons/{season_id}` | 赛季详情（限本家庭） | 登录 |
| POST | `/scn/seasons` | 创建赛季 | 父母 |
| PATCH | `/scn/seasons/{season_id}` | 更新赛季 | 父母 |
| POST | `/scn/seasons/{season_id}/activate` | 激活（互斥，自动停用其他） | 父母 |
| DELETE | `/scn/seasons/{season_id}` | 删除赛季 | 父母 |

**SeasonRead**：

```jsonc
{
  "id": "str", "family_id": "str",
  "name": "str",
  "theme_id": "DEFAULT | FROSTBOUND | INFERNO | SYLVAN | CYBERPUNK",
  "narrative_context": "str",
  "start_date": "datetime", "end_date": "datetime | null",
  "is_active": true,
  "created_at": "datetime", "updated_at": "datetime"
}
```

**SeasonCreate** `{ name, theme_id?, narrative_context?, start_date, end_date? }`
**SeasonUpdate**（均可选）`{ name, theme_id, narrative_context, end_date, is_active }`
**SeasonHistoryItem** `{ season: SeasonRead, total_tasks: int, completed_tasks: int }`

> `ThemeId` 是**赛季主题枚举**（预设皮肤，前端 `constants/themes.ts` 对应渲染素材）；与第 7 节的动态主题样式 `ThemeStyle` 是两个概念。

## 6. 任务 `/scn/task-instances`（路由器前缀 `/scn`，另承载 `/scn/task-templates`）

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/scn/task-instances?page&page_size&season_id&status&template_id&assignee_child_id` | 任务实例分页列表（`template_id` 供模板详情/重新生成确认数未消费实例，DEV-35） | 登录 |
| GET | `/scn/task-instances/{task_id}` | 详情（限本家庭） | 登录 |
| POST | `/scn/task-instances` | 创建模板并生成初始实例（CHAIN 仅链首步） | 父母 |
| POST | `/scn/task-templates` | 只建模板不投放实例（CHAIN 第 2..N 步，DEV-36） | 父母 |
| DELETE | `/scn/task-instances/{task_id}` | 删除实例 | 父母 |
| POST | `/scn/task-instances/{task_id}/start` | 孩子接取（扣时间币押金；COOP 记 OWNER 参与者） | 登录 |
| POST | `/scn/task-instances/{task_id}/join` | 加入 COOP：孩子均摊押金 / 家长亲子参与（DEV-36） | 登录 |
| POST | `/scn/task-instances/{task_id}/submit` | 孩子提交证明（多证据，块 E） | 登录 |
| POST | `/scn/task-instances/{task_id}/approve` | 父母审核（发 XP、退/扣币；链末 ×1.5、XP 均摊） | 父母 |
| POST | `/scn/task-instances/{task_id}/abandon` | 孩子放弃（罚币） | 登录 |
| GET | `/scn/task-instances/{task_id}/proofs` | 任务证据列表（未软删，按提交顺序；限本家庭） | 登录 |

**任务证据 `/scn/task-proofs`**（块 E，docs/07 A7.2）：

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/scn/task-proofs/{proof_id}` | 单条证据（404 含已软删；限本家庭） | 登录 |
| DELETE | `/scn/task-proofs/{proof_id}` | 软删一条证据（`deleted_at` 置位，行保留；仅上传者本人或父母） | 登录 |

**TaskRead**（任务实例唯一形状）：

```jsonc
{
  "id": "str", "family_id": "str", "season_id": "str",
  "template_id": "str | null",
  "creator_account_id": "str | null",
  "target_child_id": "str | null",    // 指派给某个孩子（null=可任接）
  "assignee_child_id": "str | null",  // 实际接取的孩子
  "category": "STUDY|CHORE|SPORT|ART|LIFE|OTHER | null",  // 来自模板
  "title": "str", "description": "str", "lore_snippet": "str | null",
  "xp_reward": 50,
  "type": "DAILY|CHALLENGE|CHAIN|TIMED|COOP",   // 来自模板
  "status": "AVAILABLE|IN_PROGRESS|PENDING_REVIEW|COMPLETED|EXPIRED",
  "deadline": "datetime | null",
  "expire_at": "datetime | null",
  "generated_for_date": "date | null",           // 生成器产出实例的逻辑日(见 6A);一次性手工任务为 null
  "required_start_time": "HH:MM:SS | null",     // 来自模板
  "proof_url": "str | null",                    // 过渡：= proofs[0].url（读取以 proofs 为准）
  "proofs": [TaskProofRead],                     // 多证据（块 E），未软删，按提交顺序
  "rating": "1-5 | null",
  "review_comment": "str | null",
  "xp_awarded": "int | null",
  "coin_delta": 0,
  "abandon_count_at_submit": 0,
  "started_at": "datetime | null",
  "submitted_at": "datetime | null",
  "completed_at": "datetime | null",
  "reminder_message": "str | null",             // 来自模板
  "reminder_minutes_before": 15,                // 来自模板
  "time_deposit": 10,
  "created_at": "datetime", "updated_at": "datetime",
  // 兼容旧前端字段（迁移期保留，勿新用）：
  "creator_id": "str | null", "target_user_id": "str | null", "assignee_id": "str | null"
}
```

**TaskProofRead** `{ id, task_instance_id, kind: "IMAGE|VIDEO|AUDIO", url: "str | null", size, content_type, created_at }`
> `kind` 由 `content_type` 推导（image/*→IMAGE，video/*→VIDEO，audio/*→AUDIO）；`url` 按 `object_key` 现算，与 `UploadRead.access_url` 同口径（minio 预签名 / local 稳定路径）。

**TaskCreate**（POST body；= TaskTemplateCreate + 实例参数）：
`{ season_id, library_id?, category?, title, description?, lore_snippet?, xp_reward?(50, ≥0), type?(DAILY), target_child_id?, required_start_time?, reminder_message?, reminder_minutes_before?(15), time_deposit?(10), is_active?(true), target_user_id?, deadline?, expire_at? }`

**TaskSubmitRequest** `{ proof_object_keys: string[] }`（块 E 起多证据；旧字段 `proof_object_key?: str` 过渡保留，等价单元素列表）— **不是 base64**：先循环 `POST /sys/uploads`（purpose=`task_proof`，建议带同一 `task_id`，DEV-30 起 key 含任务实例标识）逐个拿 `object_key`，再一次提交全部 keys。逐个校验：必须存在于 `sys_upload`、上传者为当前用户、`purpose=task_proof`、content-type 可推导 kind、未被其他任务占用（`sys_upload.task_instance_id` 或既有 `scn_task_proof` 行任一命中即 422，防 local 模式下用任意字符串引用/探测他人对象）；任何一个不合法**整单 422**，不留半提交状态。数量上限 `upload.max_proof_files`（默认 9），重复 key / 空列表 422。提交成功时按所选集合整体落 `scn_task_proof` 行：新 key 建行、本任务已软删的 key 复活、未再携带的旧证据软删（提交即"当前所选集合"）；并把未绑定的凭证回填 `task_instance_id`。
**TaskApproveRequest** `{ rating: int 1–5（必填）, comment?: str }`

## 6A. 任务模板 `/scn/task-templates` 与模板库 `/scn/template-library`（DEV-35 块 A，已实现）

> 模板级接口：只管模板与触发规则，POST 不再强制建实例（创建/改规则/激活后由生成器即时补一次生成）。与 `/scn/task-instances`（实例状态机）分界。

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/scn/task-templates?season_id&is_active&type` | 模板列表（含 triggers，不分页） | 登录 |
| POST | `/scn/task-templates` | 创建模板+触发规则并即时生成 | 父母 |
| GET | `/scn/task-templates/{id}` | 模板详情 | 登录（限本家庭） |
| PATCH | `/scn/task-templates/{id}` | 部分更新（triggers 整组替换；`target_child_id` 可改，置 null 清空指派） | 父母 |
| POST | `/scn/task-templates/{id}/deprecate` | 废弃（停用+审计，既有实例不动） | 父母 |
| POST | `/scn/task-templates/{id}/activate` | 重新启用并立即补生成 | 父母/管理端 |
| POST | `/scn/task-templates/{id}/regenerate` | 终结可用/进行中实例并尝试生成 | 父母/管理端 |
| DELETE | `/scn/task-templates/{id}` | 硬删（**仅无 COMPLETED/EXPIRED 历史实例时可用**，否则 422 引导走 deprecate） | 管理端（家庭 owner） |
| GET | `/scn/template-library?category&keyword&favorites_only` | 模板库列表（系统预置+家庭自建） | 登录 |
| GET | `/scn/template-library/{id}` | 库条目详情 | 登录 |
| POST | `/scn/template-library/{id}/favorite` | 收藏开关（返回切换后状态） | 父母 |
| POST | `/scn/template-library/{id}/apply` | 用 `suggested_*` 播种新模板并即时生成 | 父母 |

**TaskTemplateCreate**（POST body；`triggers` 缺省时按类型补默认规则：DAILY/TIMED→`DAILY@00:00`，CHALLENGE→每周一 `CRON "0 0 * * 1"`，一次性/CHAIN/COOP 无默认）：
`{ season_id, library_id?, category?, title, description?, lore_snippet?, xp_reward?, type?, target_child_id?, required_start_time?, reminder_message?, reminder_minutes_before?, time_deposit?, is_active?, timed_mode?(NONE), deadline_time?, start_time?, duration_minutes?, pool_policy?(REUSE_UNTIL_CONSUMED), estimated_minutes?, difficulty?(1-5), triggers?: [TaskTriggerCreate] }`

**timed_mode 一致性（创建/更新 422）**：`DEADLINE` 需 `deadline_time`；`DURATION` 需 `start_time`+`duration_minutes`；`NONE` 三者皆空。PATCH 对合并后的完整模板复验。

**TaskTriggerCreate** `{ kind: DAILY|WEEKDAYS|MONTHLY|CRON|ONCE, cron_expr?, weekdays?([0-6], 0=周一), day_of_month?(1-31, 月末不足取当月最后一天), generate_at?("HH:MM", 默认 00:00), starts_on?, ends_on?, is_active?(true) }`
按 kind 校验（422）：`WEEKDAYS` 需非空 weekdays；`MONTHLY` 需 day_of_month；`CRON` 需合法 5 段表达式（校验与匹配同用 APScheduler 语义，day_of_week **0=周一**）；`ONCE` 需 starts_on（该日生成一次）。

**TaskTriggerRead** = TaskTriggerCreate + `{ id, template_id, created_at, updated_at }`。
**TaskTemplateRead** = TaskTemplateCreate 字段（去 season_id 语义不变）+ `{ id, family_id, season_id, creator_account_id, deprecated_at, deprecated_reason, triggers: [TaskTriggerRead], created_at, updated_at }`。
**TaskTemplateDeprecate** `{ reason?: str(≤128) }`；**TaskTemplateRegenerate** `{}`（占位）。
**TemplateLibraryApplyRequest** `{ season_id, target_child_id? }`。

**regenerate 语义（Mars 审查后产品拍板）**：
- 终结范围 = 未消费三态中的 `AVAILABLE + IN_PROGRESS`；**PENDING_REVIEW 不终结**（孩子已提交待审核的成果保留审核机会）。IN_PROGRESS 终结时全额退押金（不计放弃惩罚）。
- 待审核实例仍占实例池槽位（D1），存在时**本轮不新建**：响应 `action="kept"`、`new_instance=null`；审核完结（COMPLETED/驳回后完成）后下个触发周期恢复生成。
- 响应 `data = { template_id, terminalized_instance_ids: string[], action: "created"|"exists"|"kept"|"not_due"|"skipped_expired", new_instance: {id, generated_for_date, status} | null }`；`new_instance` 仅在 `action="created"` 时非空（其余值一律按"未生成新实例"处理）。`exists` 亦会出现在强生成撞当日既有行的路径（如当日实例已消费后 PATCH triggers/activate）。
- 前端"事前 N"= `GET /scn/task-instances?template_id=X` 按 `AVAILABLE + IN_PROGRESS` 两态 total 求和。

**已知项**：生成器跳过"生成即过期"的当日生成（限时任务在截止时刻过后才到期/创建时不产出注定被过期 job 判死的实例，`action="skipped_expired"`）；`ends_on` 窗口结束后的非限时未消费实例不再顺延也不过期（REUSE_UNTIL_CONSUMED 语义自洽，如需清理属后续产品决策）。

> **收藏实现**：收藏行是本家庭名下一条例外克隆（`meta.favorite_of` 指向原条目），不新增表；`favorites_only=true` 返回收藏行自身，列表项带 `is_favorite` / `favorite_of`。

> ⚠️ **规划中变更(尚未实现,以 [12-任务触发与实例化池方案](./12-任务触发与实例化池方案.md) 为准)**:
> - ~~`TaskRead` 增 `generated_for_date`~~（✅ DEV-35 已落地）。
> - ~~模板级接口 `/scn/task-templates*`、模板库 `/scn/template-library*`~~（✅ DEV-35 已实现，见 §6A；`preview-deposit` 仍未实现）。
> - ~~多证据提交(`proof_object_keys`、`TaskRead.proofs[]`)与证据接口(`/scn/task-instances/{id}/proofs`、`/scn/task-proofs/{id}`)~~ 已随块 E(DEV-33/DEV-37)实现合入,前端可对接。
> - 清理接口 `POST /scn/evidence/purge(-preview)`(docs/07 A7.3)仍未实现。

## 7. 动态主题样式 `/scn/theme-styles`

> 家庭级自定义主题（AI 生成 tokens/css_vars），区别于赛季 `ThemeId` 预设枚举。

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/scn/theme-styles` | 主题列表（系统+本家庭） | 登录 |
| GET | `/scn/theme-styles/{theme_id}` | 详情 | 登录 |
| POST | `/scn/theme-styles` | 创建家庭主题 | 父母 |
| PATCH | `/scn/theme-styles/{theme_id}` | 更新 | 父母 |
| POST | `/scn/theme-styles/{theme_id}/activate` | 激活（家庭内互斥） | 父母 |
| DELETE | `/scn/theme-styles/{theme_id}` | 删除 | 父母 |
| POST | `/scn/theme-styles/generate` | **AI 生成家庭主题** | 父母 |

**ThemeStyleRead** `{ id, family_id, name, scene_prompt, description, tokens: object, css_vars: object, is_system: bool, is_active: bool, created_at, updated_at }`
**ThemeStyleCreate** `{ name, scene_prompt?, description?, tokens?{}, css_vars?{}, is_active?=false }`
**ThemeStyleUpdate** 同上全可选。
**ThemeGenerateRequest** `{ scene_prompt: str, name?, activate?=false }`

## 8. 时间币流水 `/scn/time-coin-logs`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/scn/time-coin-logs?page&page_size&child_id` | 流水分页 | 登录 |
| POST | `/scn/time-coin-logs/adjust` | 人工调整 | 父母 |

**CoinTransactionRead**：

```jsonc
{
  "id": "str", "family_id": "str", "child_id": "str",
  "season_id": "str | null", "task_instance_id": "str | null",
  "type": "DAILY_RESET|TASK_DEPOSIT|TASK_REFUND|ABANDON_PENALTY|MANUAL_ADJUST",
  "amount": 0,            // 正数增加，负数扣减
  "balance_after": 0,
  "note": "str | null",
  "created_at": "datetime",
  "user_id": "str | null", "task_id": "str | null"   // 兼容旧字段
}
```

**CoinAdjustRequest** `{ child_id?, user_id?, amount: int（正加负减，必填）, note? }`

## 9. 特权 `/scn/privileges`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/scn/privileges/templates` | 特权模板树（系统+本家庭，按 level 排序） | 登录 |
| GET | `/scn/privileges/unlocks?child_id` | 已解锁特权 | 登录 |
| POST | `/scn/privileges/uses` | 使用一次已解锁特权 | 登录 |

**PrivilegeRead** `{ id, family_id, season_id, level_required: int, title, description, icon, is_system: bool, is_active: bool }`
**UserPrivilegeRead** `{ id, family_id, child_id, season_id, privilege_template_id, privilege: PrivilegeRead, unlocked_at, used_count, last_used_at, user_id（兼容） }`
**UserPrivilegeUseRequest** `{ child_id?, user_id?, privilege_template_id? | privilege_id?, cost? }`
**使用成功返回 RedemptionRead（见第 10 节）。**

## 10. 特权使用记录 `/scn/privilege-uses`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/scn/privilege-uses?page&page_size&child_id` | 使用记录分页 | 登录 |
| POST | `/scn/privilege-uses` | 手工记录一次使用（自由文本特权） | 登录 |

**RedemptionRead** `{ id, family_id, child_id, season_id, privilege_template_id, privilege_title: str, cost: str | null, used_at: datetime, user_id / privilege_id / date（兼容） }`
**RedemptionCreate** `{ child_id?, user_id?, privilege_template_id? | privilege_id?, privilege_title?, cost? }`

## 11. 时间币配置 `/scn/time-configs`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/scn/time-configs/me` | 本家庭配置 | 登录 |
| PUT | `/scn/time-configs/me` | 更新配置（整体替换 exceptions） | 父母 |

**TimeConfigRead**：

```jsonc
{
  "family_id": "str",
  "default_daily_allowance": 100,
  "exceptions": [ { "day_of_week": 0, "coin_amount": 200 } ]   // 0=周日…6=周六，数组而非字典
}
```

**TimeConfigUpdate** `{ default_daily_allowance?（≥0）, exceptions?: [{day_of_week 0–6, coin_amount ≥0}] }`

## 12. 上传 `/sys/uploads`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| POST | `/sys/uploads` | multipart 上传：`file`（必填）+ `purpose`（`avatar|task_proof|season_banner|other`）+ `task_id`（可选，`task_proof` 时建议携带） | 登录 |

**UploadRead** `{ id, family_id, task_instance_id, uploader_account_id, storage_provider, object_key, bucket, public_url, content_type, size, purpose, access_url, created_at }`
> 任务提交用 `object_key`；展示用 `access_url`。`task_instance_id`（DEV-30，可空）：上传时携带 `task_id` 即回显；否则在任务提交时回填绑定。（预签名直传 `UploadUrlRequest` 已预留 DTO，暂未启用。）
>
> **存储路径规范（DEV-20 / DEV-30）**：
> - `task_proof` 携带 `task_id`（DEV-30）：`object_key = {prefix}/{用户}/{任务实例id}/{yyyymmdd}/task_proof-{序号}_{原始文件名安全化}.{扩展名}`。任务实例 id 唯一定位任务；yyyymmdd 按北京时区；文件名安全化 = 保留 unicode 字母数字（中文原样）、其余折叠为 `_`、截断 64 字符、剥路径段。
> - 其余上传（头像/横幅等，及未携带 `task_id` 的 task_proof）：`object_key = {prefix}/{用户}/{年}/{月}/{日}/{purpose}-{序号}.{扩展名}`（DEV-20 形状不变）。
>
> `prefix`/`bucket` 由 yaml（`storage.minio` / `storage.local`）统一管理；序号 = 同 key 前缀维度自增。`task_id` 校验归属本家庭，跨家庭任务返回 404。历史对象不做迁移（开发验证阶段）。
>
> **任务关联（DEV-30）**：携带 `task_id` 的上传写 `sys_upload.task_instance_id`（数据库层可按任务检索）；未携带的凭证由 `submit` 回填绑定，已绑定其他任务的凭证拒绝复用（422）。
>
> **证明文件约束（块 E，`upload` 配置段）**：`purpose=task_proof` 的上传在上传口收口校验——大小 ≤ `max_proof_file_mb`（默认 50MB），content-type须匹配 `allowed_content_types` 白名单（默认 `image/*`、`video/*`、`audio/*` 通配），违规 422。数量上限（`max_proof_files`，默认 9）在任务提交口校验。
>
> **URL 行为（MinIO / local 双模式）**：`access_url` 始终按 `object_key` 现算——MinIO 模式返回带过期时间的预签名 URL（`public_url` 不落库）；local 模式返回稳定路径 `{public_base_url}/{object_key}`（`public_url` 落库）。前端两种模式下都只消费 `access_url` / `TaskRead.proof_url`，无需感知存储差异。
>
> **存量回归（DEV-20 收尾）**：旧实现曾把 MinIO 预签名 URL 落到 `public_url`，该类 URL 会过期；读取端对 `storage_provider=minio` 的行一律忽略存量 `public_url`、按 `object_key` 现算 `access_url`（选读取端忽略而非一次性迁移：无需对每个环境执行 UPDATE，部署即生效，对 local 行为零影响）。文件序号自增采用「先插库占位、后写对象」：object_key 唯一索引在存储写入前仲裁并发，撞号顺延重试；对象写入失败删除占位行，不留孤儿。

## 13. AI `/scn/ai`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| POST | `/scn/ai/generate-quest` | AI 生成任务文案 | 父母 |
| POST | `/scn/ai/evaluate-proof` | AI 评分任务证明 | 父母 |

**GenerateQuestRequest** `{ topic: str（1–500）, child_level?: int = 1（1–200）, narrative_context?: str = "" }`
→ `data`（无静态类型，来自 LLM，schema 见 `ai_service.QUEST_JSON_SCHEMA`）：
`{ title, description, lore_snippet, xp_reward, type: "DAILY|CHALLENGE|CHAIN|TIMED|COOP", reminder_message? }`

**EvaluateProofRequest** `{ task_title: str, image_data_url: str }`
→ `{ rating: 1–5, comment: str }`
> ⚠️ 当前实现为**纯文本 LLM 评分**（未把图片送入模型，见 `ai_service.evaluate_proof`）；多模态支持是后端待办，前端不要假设评分已"看图"。

**AI 配置口径（DEV-24）**：模型选择与默认参数（temperature / max_tokens / timeout 等）收敛在后端
`config.yaml` 的 `ai:` 段（按 `llm` / `image` / `video` 三能力分组，key 只经环境变量引用）。请求体
**只携带业务参数**（如上），不接受也不返回任何模型配置；前端不接触模型配置。某能力未启用
（`enabled=false`）或未配置时，对应接口返回 `503 service_unavailable`。

## 14. 已规划但**尚未实现**的接口（前端禁止对接）

### 14.1 旧文档 `06` 遗留（后端无代码）

以下接口只存在于旧文档 `06-API设计要点.md`，**后端代码中没有**，前端不得按其开发（需要时先提后端 issue）：

- `GET /scn/levels/curve`
- `POST /scn/task-instances/preview-xp`
- 其余以 `06` 文档"新增"名义列出但不在本文档中的接口

### 14.2 本轮定稿方案（见 `12-任务触发与实例化池方案.md`）

以下接口/字段已在 12 定稿；实现后回填本文档相应章节，未实现前前端禁止对接：

- ~~`GET/POST /scn/task-templates`、`PATCH /scn/task-templates/{id}`、`POST /{id}/deprecate|activate|regenerate`~~（✅ DEV-35 已实现，见 §6A；`preview-deposit` 已随 DEV-34 实现）
- ~~`GET /scn/template-library`、`POST /scn/template-library/{id}/favorite|apply`~~（✅ DEV-35 已实现，见 §6A）
- ~~`GET /scn/task-instances/{id}/proofs`、`GET/DELETE /scn/task-proofs/{id}`~~；~~`TaskSubmitRequest.proof_object_keys: string[]`（`proof_object_key` 过渡保留）；`TaskRead.proofs[]`~~（✅ 块 E / DEV-33、DEV-37 已实现，见 §6）
- `POST /scn/evidence/purge(-preview)`

---

*生成方式：人工逐文件核对 `server/app/api/v1/*.py`（14 个路由文件）与 `server/app/schemas/*.py`（13 个 DTO 文件）、`app/models/enums.py`、`app/middleware/__init__.py`、`app/deps.py`。后端路由/schema 改动时本文档必须同 PR 更新。*
