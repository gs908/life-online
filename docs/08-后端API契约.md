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
- 获取：`POST /sys/auth/wechat/jscode`（微信登录）或 `POST /sys/auth/refresh`（刷新）。
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
| POST | `/sys/auth/refresh` | refresh_token 换新 token 对 | 无 |
| POST | `/sys/auth/dev-login` | 开发环境非微信登录（仅 `DEV_LOGIN_ENABLED=true`） | 无 |
| POST | `/sys/auth/logout` | 登出（仅日志，客户端清 token） | 登录 |
| GET | `/sys/auth/me` | 当前用户 `UserRead` | 登录 |

**WechatJscodeRequest** `{ code: str, nickname?: str, avatar_url?: str }`
**RefreshRequest** `{ refresh_token: str }`
**DevLoginRequest** `{ role?: "GUILD_MASTER" \| "ADVENTURER" = "ADVENTURER", name?: str }`
**TokenPair** `{ access_token, refresh_token, token_type: "Bearer", access_expires_in: int, refresh_expires_in: int }`
> 微信登录若 openid 无账号，返回业务错误要求邀请码流程（`NeedInviteCodeError` → 走 `/sys/families/join`）。

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

## 6. 任务 `/scn/task-instances`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/scn/task-instances?page&page_size&season_id&status&assignee_child_id` | 任务实例分页列表 | 登录 |
| GET | `/scn/task-instances/{task_id}` | 详情（限本家庭） | 登录 |
| POST | `/scn/task-instances` | 创建模板并生成初始实例 | 父母 |
| DELETE | `/scn/task-instances/{task_id}` | 删除实例 | 父母 |
| POST | `/scn/task-instances/{task_id}/start` | 孩子接取（扣时间币押金） | 登录 |
| POST | `/scn/task-instances/{task_id}/submit` | 孩子提交证明 | 登录 |
| POST | `/scn/task-instances/{task_id}/approve` | 父母审核（发 XP、退/扣币） | 父母 |
| POST | `/scn/task-instances/{task_id}/abandon` | 孩子放弃（罚币） | 登录 |

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
  "required_start_time": "HH:MM:SS | null",     // 来自模板
  "proof_url": "str | null",                    // 证明图访问 URL（由 object_key 生成）
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

**TaskCreate**（POST body；= TaskTemplateCreate + 实例参数）：
`{ season_id, library_id?, category?, title, description?, lore_snippet?, xp_reward?(50, ≥0), type?(DAILY), target_child_id?, required_start_time?, reminder_message?, reminder_minutes_before?(15), time_deposit?(10), is_active?(true), target_user_id?, deadline?, expire_at? }`

**TaskSubmitRequest** `{ proof_object_key: str }` — **不是 base64**：先 `POST /sys/uploads`（purpose=`task_proof`）拿 `object_key`，再提交。
**TaskApproveRequest** `{ rating: int 1–5（必填）, comment?: str }`

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

**UploadRead** `{ id, family_id, uploader_account_id, storage_provider, object_key, bucket, public_url, content_type, size, purpose, access_url, created_at }`
> 任务提交用 `object_key`；展示用 `access_url`。（预签名直传 `UploadUrlRequest` 已预留 DTO，暂未启用。）
>
> **存储路径规范（DEV-20）**：`object_key = {prefix}/{用户}/{年}/{月}/{日}/{任务号}-{文件序号}.{扩展名}`。`prefix`/`bucket` 由 yaml（`storage.minio` / `storage.local`）统一管理；年/月/日按北京时区；任务号 = `task_id`（未携带时以 `purpose` 代替）；文件序号 = 同用户同日同任务维度自增。`task_id` 校验归属本家庭，跨家庭任务返回 404。
>
> **URL 行为（MinIO / local 双模式）**：`access_url` 始终按 `object_key` 现算——MinIO 模式返回带过期时间的预签名 URL（`public_url` 不落库）；local 模式返回稳定路径 `{public_base_url}/{object_key}`（`public_url` 落库）。前端两种模式下都只消费 `access_url` / `TaskRead.proof_url`，无需感知存储差异。

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

以下接口只存在于旧文档 `06-API设计要点.md`，**后端代码中没有**，前端不得按其开发（需要时先提后端 issue）：

- `GET /scn/levels/curve`
- `POST /scn/task-instances/preview-xp`
- `GET /scn/template-library`（及模板库相关 CRUD）
- 其余以 `06` 文档"新增"名义列出但不在本文档中的接口

---

*生成方式：人工逐文件核对 `server/app/api/v1/*.py`（14 个路由文件）与 `server/app/schemas/*.py`（13 个 DTO 文件）、`app/models/enums.py`、`app/middleware/__init__.py`、`app/deps.py`。后端路由/schema 改动时本文档必须同 PR 更新。*
