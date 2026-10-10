# 09. 前后端类型对齐与 Mock 映射（前端接入规范）

> 配套文档：`08-后端API契约.md`（唯一事实来源）。
> 本文比对对象：`packages/admin/src/types.ts`、`packages/admin/src/App.tsx` 内 Mock 数据、`packages/admin/src/services/geminiService.ts`。
> 裁决原则：**以后端 schema 为准**；前端确有需要的字段，通过新增后端 issue 回补后端，再改前端。

---

## 1. 前端类型 vs 后端 schema 差异清单与裁决

逐个 DTO 比对。裁决标记：**[后端为准]** 前端改类型适配后端；**[回补后端]** 前端确需、后端补字段（走后端 issue）；**[一致]** 无需改动。

### 1.1 命名与序列化（全局裁决）

| # | 差异 | 裁决 |
|---|------|------|
| G1 | 前端全部 camelCase（`seasonId`、`timeCoins`），后端 JSON 全部 snake_case（`season_id`、`time_coins`） | **[后端为准]** 前端类型改为 snake_case，或在 API client 层统一做转换（二选一，全仓一致；推荐前者，避免双份字段名）。后端已有的 `creator_id/target_user_id/assignee_id` 等"兼容旧前端"字段是迁移期产物，**新代码禁用**，迁移完成后由后端删除 |
| G2 | 前端成功判定无约定；后端为 `{code:0, data, msg}` 包裹 | **[后端为准]** API client 统一解包：`code === 0` 成功，否则抛错（`data.error_code` + `msg`） |
| G3 | 前端日期混用 `new Date().toDateString()` / ISO 字符串；后端 `datetime`→ISO 8601、`date`→`YYYY-MM-DD`、`time`→`HH:MM:SS` | **[后端为准]** 前端统一按 ISO 字符串处理，展示层再格式化 |

### 1.2 UserRole（types.ts:2-5）

| # | 差异 | 裁决 |
|---|------|------|
| U1 | 前端枚举名 `PARENT/CHILD`，值恰为 `'GUILD_MASTER'/'ADVENTURER'`；后端枚举名与值均为 `GUILD_MASTER/ADVENTURER` | **[后端为准]** 前端枚举改名为 `GUILD_MASTER/ADVENTURER`（值不变，纯改名）。`PARENT/CHILD` 是语义注释，不是接口值，不得再作为类型名使用 |

### 1.3 Season（types.ts:20-28 vs SeasonRead）

| # | 差异 | 裁决 |
|---|------|------|
| S1 | 字段名：`themeId→theme_id`、`narrativeContext→narrative_context`、`startDate/endDate→start_date/end_date`、`isActive→is_active` | **[后端为准]**（同 G1） |
| S2 | 前端缺 `family_id、created_at、updated_at` | **[后端为准]** 补齐字段（详情/列表原样透传即可，前端不必全部使用） |
| S3 | 前端"赛季历史"直接复用 `Season[]`；后端有专用 `GET /scn/seasons/history → SeasonHistoryItem{season,total_tasks,completed_tasks}` | **[后端为准]** 前端新增 `SeasonHistoryItem` 类型，历史页展示完成度统计（比 Mock 更强的能力，直接用） |

### 1.4 SeasonTheme（types.ts:9-18 / constants/themes.ts）vs 后端双主题体系

| # | 差异 | 裁决 |
|---|------|------|
| T1 | 前端只有一种"主题"概念（5 个静态皮肤：primaryColor 等 Tailwind class）；后端是**两套**：① 赛季 `ThemeId` 枚举（预设皮肤，对应前端素材），② `/scn/theme-styles` 家庭级动态主题（`tokens/css_vars`，支持 AI 生成） | **[后端为准]** 前端拆成两个类型：`ThemeId`（枚举，保留 `constants/themes.ts` 作渲染素材映射）与 `ThemeStyleRead`（对应动态主题）。赛季详情只携带 `theme_id` 字符串；动态主题样式单独拉 `/scn/theme-styles` |
| T2 | 前端 Mock 无动态主题 CRUD/激活/AI 生成 | **[后端为准]** 新页面按契约第 7 节接入（父母端功能） |

### 1.5 TaskType / TaskStatus（types.ts:30-44）

| # | 差异 | 裁决 |
|---|------|------|
| K1 | 枚举值逐一比对：`DAILY/CHALLENGE/CHAIN/TIMED/COOP`、`AVAILABLE/IN_PROGRESS/PENDING_REVIEW/COMPLETED/EXPIRED` | **[一致]** 前端枚举值可直接沿用 |

### 1.6 Task（types.ts:82-104 vs TaskRead / TaskCreate）

| # | 差异 | 裁决 |
|---|------|------|
| A1 | 字段名 snake_case 化（`xpReward→xp_reward`、`loreSnippet→lore_snippet`、`requiredStartTime→required_start_time` 等） | **[后端为准]** |
| A2 | 前端 `proofImage?: string`（base64 data URI）vs 后端 `proof_url`（读）+ `proof_object_key`（写，先走 `/sys/uploads`） | **[后端为准]** 前端删除 base64 方案：提交=先 `POST /sys/uploads`(purpose=`task_proof`) 再 `submit{proof_object_key}`；展示用 `proof_url` |
| A3 | 前端缺：`template_id、category、expire_at、review_comment、xp_awarded、coin_delta、abandon_count_at_submit、submitted_at、completed_at、created_at、updated_at、family_id、creator_account_id` | **[后端为准]** TaskRead 全字段补齐；`type/required_start_time/reminder_*` 在实例上来自模板（后端已做兼容透传） |
| A4 | 前端 `assigneeId` 单字段；后端区分 `target_child_id`（指派对象）/`assignee_child_id`（实际接取人），且是 **child_id**（冒险者档案 ID），非账号 ID | **[后端为准]** 前端改为两字段；注意 `UserRead` 同时返回 `id`（账号）与 `child_id`（档案），任务指派用 `child_id` |
| A5 | 前端 `deadline?: string` vs 后端 `deadline: datetime|null`；创建时后端另有 `expire_at` | **[后端为准]** 语义：`deadline`=完成截止，`expire_at`=实例过期回收 |
| A6 | 前端创建任务 Mock 直接 push 数组；后端 `POST /scn/task-instances`（TaskCreate，必填 `season_id、title`） | **[后端为准]** 创建即"建模板+初始实例"，无独立模板接口 |

### 1.7 User（types.ts:66-80 vs UserRead）

| # | 差异 | 裁决 |
|---|---|---|
| P1 | 字段名：`timeCoins→time_coins`、`dailyAbandonCount→daily_abandon_count`、`lastLoginDate→last_login_date` | **[后端为准]** |
| P2 | 前端 `privilegesUnlocked: number[]`（等级数组）vs 后端 `privileges_unlocked: string[]`（特权模板 ID 数组） | **[后端为准]** **类型冲突（number vs string）**。后端模型以特权模板为粒度（`PrivilegeRead.level_required`），"按等级解锁"改由前端把 `templates` 按 `level_required` 分组渲染特权树；已解锁集合用 `/scn/privileges/unlocks`。本地视图类型的 `privilegesUnlocked` 字段已删除（DEV-23），接入（阶段④）时不再有类型冲突 |
| P3 | 前端缺：`family_id、child_id、current_season_id、created_at、updated_at` | **[后端为准]** 补齐 |
| P4 | Mock 中父母 `level:99, timeCoins:9999`；后端父母 level 固定 1、time_coins 0 | **[后端为准]** 父母端不展示等级/时间币（或展示家庭汇总，那是新需求→走后端 issue） |
| P5 | 前端每日重置靠 `lastLoginDate` 本地比对；后端在 `GET /sys/accounts/me`（冒险者）服务端自动重置 | **[后端为准]** ✅ 已执行（DEV-23）：本地重置逻辑已删除，登录/引导调 `/sys/accounts/me` 即可 |

### 1.8 Privilege（types.ts:46-51 vs PrivilegeRead）

| # | 差异 | 裁决 |
|---|------|------|
| V1 | 前端只有展示四字段（`levelRequired/title/description/icon`）；后端 `PrivilegeRead` 另有 `id/family_id/season_id/is_system/is_active` | **[后端为准]** 补齐；`id` 是使用/解锁接口的必传参 |
| V2 | 前端特权树写死等级数组；后端 `GET /scn/privileges/templates` 返回系统+家庭模板并已按 `level_required` 排序 | **[后端为准]** 特权树数据源改为该接口 |

### 1.9 RedemptionRecord（types.ts:53-59 vs RedemptionRead）

| # | 差异 | 裁决 |
|---|------|------|
| R1 | 字段名：`privilegeTitle→privilege_title`、`date→used_at`；`user` 为自由文本 vs `child_id` | **[后端为准]** |
| R2 | 前端 `cost?: string`（"Monthly Use"文案）与后端 `cost: str|null` 一致 | **[一致]** |
| R3 | 前端缺：`family_id、season_id、privilege_template_id` | **[后端为准]** 补齐 |

### 1.10 TimeConfig（types.ts:61-64 vs TimeConfigRead）

| # | 差异 | 裁决 |
|---|------|------|
| C1 | **结构冲突**：前端 `exceptions: Record<number, number>`（字典）；后端 `exceptions: [{day_of_week, coin_amount}]`（数组） | **[后端为准]** 前端改数组；如需字典视图在前端 UI 层自行转换，不进 API 层 |
| C2 | 前端缺 `family_id` | **[后端为准]** 补齐 |
| C3 | 更新语义：后端 `PUT /scn/time-configs/me` 对 exceptions 是**整体替换** | **[后端为准]** 前端保存时提交完整数组 |

### 1.11 Mock 中完全没有后端对应概念的部分

| # | 前端 Mock 现状 | 后端现状 | 裁决 |
|---|---------------|---------|------|
| M1 | ~~无登录/无家庭概念，`MOCK_USERS` 写死两个用户~~ **已解决（DEV-23）**：Mock 用户已删除，接入登录态与家庭上下文（开发期 H5 走 `POST /sys/auth/dev-login`，契约 §2） | 完整 auth+家庭+邀请码体系（契约 §2–§4）；**DEV-22 已补网页端生产通道：`/sys/auth/password/login` + `/password/register` + `PUT /password/me`（账号密码，scrypt 哈希 + 失败限流 429，契约 §2）** | **[后端为准]** 已接入开发期登录；生产登录由前端把 LoginPage 切到 password 通道（`dev-login` 仅 `DEV_LOGIN_ENABLED=true` 可用，生产保持关闭） |
| M2 | 时间币流水无页面 | `GET /scn/time-coin-logs` 分页流水 + `POST /adjust` | **[后端为准]** 父母端补"时间币流水"页（后端能力已就绪） |
| M3 | 主题仅静态 5 皮肤 | 动态主题 CRUD + AI 生成 | **[后端为准]** 按契约 §7 接入 |

---

## 2. Mock 数据 → 后端接口映射表

`App.tsx` 中的每块 Mock 状态/操作 → 对应后端接口（无对应 → 标注缺口处理方式）：

| 前端 Mock（App.tsx） | 后端接口 | 状态 |
|---------------------|---------|------|
| `MOCK_USERS`（用户/角色） | `GET /sys/auth/me`、`GET /sys/families/me`、`GET /sys/accounts/me` | ✅ 已有；**已接入（DEV-23 阶段①），Mock 已删除** |
| LoginPage 开发期登录（dev-login） | 生产/演示环境改走 `POST /sys/auth/password/login`（DEV-22 已就绪，契约 §2；新用户先 `POST /sys/auth/password/register` 凭邀请码注册） | 🔵 后端已备、前端待切换（含 401 统一文案 / 429 限流提示 / 409 用户名冲突提示） |
| `currentUser` 切换父母/孩子视图 | `UserRead.role`（GUILD_MASTER/ADVENTURER） | ✅ 已有（无"切换"概念——按登录角色渲染）；**已接入（DEV-23），`switchUser` 已删除** |
| `DEFAULT_SEASON` / `activeSeason` | `GET /scn/seasons/active`、`POST /scn/seasons`、`PATCH /scn/seasons/{id}`、`POST /{id}/activate` | ✅ 已有 |
| `seasonHistory`（`Season[]`） | `GET /scn/seasons/history`（SeasonHistoryItem） | ✅ 已有（形状不同，见 S3） |
| `INITIAL_TASKS` / `tasks` | `GET /scn/task-instances`（分页+过滤） | ✅ 已有；**已接入（DEV-18 阶段③），本地任务状态机已删除，视图组件统一消费 `TaskRead`** |
| 新建任务（AddTaskModal） | `POST /scn/task-instances` | ✅ 已有；**已接入（DEV-18），表单产出 `TaskCreate`（docs/09 A6）** |
| 接取任务 | `POST /scn/task-instances/{id}/start` | ✅ 已有；**已接入（DEV-18），押金由后端扣除，余额变更后 refetch `UserRead.time_coins`** |
| 提交证明（SubmitTaskModal，base64） | `POST /sys/uploads` + `POST /scn/task-instances/{id}/submit` | ✅ 已有（需改造为上传流，A2）；**已接入（DEV-18，按 docs/10 §4 ③→⑤ 交替约定先打通上传流；上传细节打磨仍属阶段⑤）** |
| 审核打分（ReviewTaskModal） | `POST /scn/task-instances/{id}/approve` | ✅ 已有；**已接入（DEV-18），本地 XP 倍率/升级计算已删除（后端 `approve` 结算 `xp_awarded`）；AI 辅助评分留待阶段⑥** |
| 放弃任务（AbandonQuestModal） | `POST /scn/task-instances/{id}/abandon` | ✅ 已有；**已接入（DEV-18），罚币/退款由后端处理** |
| `handleDeleteTask`（本地 filter） | `DELETE /scn/task-instances/{id}` | ✅ 已有；**已接入（DEV-18），含确认交互** |
| `DEFAULT_TIME_CONFIG`（TimeConfigModal） | `GET/PUT /scn/time-configs/me` | ✅ 已有（形状不同，C1） |
| `redemptionHistory`（特权使用记录） | `GET /scn/privilege-uses`、`POST /scn/privilege-uses`、`POST /scn/privileges/uses` | ✅ 已有 |
| 特权树（PrivilegeTree 组件） | `GET /scn/privileges/templates`、`GET /scn/privileges/unlocks` | ✅ 已有 |
| **geminiService.generateQuestSuggestion**（浏览器直连 Gemini） | `POST /scn/ai/generate-quest` | ✅ 已完成（DEV-24，见 §3） |
| **geminiService.evaluateTaskProof**（浏览器直连 Gemini） | `POST /scn/ai/evaluate-proof` | ✅ 已完成（DEV-24，见 §3） |
| 时间币余额展示（`timeCoins`） | `UserRead.time_coins` | ✅ 已有 |
| 时间币流水/调整 | `GET /scn/time-coin-logs`、`POST /scn/time-coin-logs/adjust` | 🔵 后端已备、前端缺页面 |
| 动态主题（AI 生成/激活） | `/scn/theme-styles`（含 `/generate`） | 🔵 后端已备、前端缺页面 |
| 通知/提醒推送（`reminderMessage` 展示） | 模板字段在 TaskRead 中返回；推送体系（NotificationType 等）后端模型已有、**API 未暴露** | 🔴 **缺口**：需要通知列表 API → 提后端 issue |
| `reminderMinutesBefore` 本地提醒触发 | 前端本地逻辑（后端 scheduler 有 worker，无前端拉取接口） | 🔴 **缺口**：如需服务端提醒 → 提后端 issue |
| Mock 中的 `deadline` 过期自动 EXPIRED | 后端状态机+worker（TIMED 超时回收） | ✅ 已有（前端轮询列表即可） |

---

## 3. Gemini 直连移除方案（强制）

**结论：前端 `packages/admin/src/services/geminiService.ts` 整体删除，禁止任何浏览器直连 LLM 的实现进入主干。**

✅ **已执行（DEV-24）**：文件与 `@google/genai` 依赖、vite `API_KEY` 注入均已删除；两个调用经 `services/api/modules/ai.ts` 走后端（模型配置收敛在后端 `config.yaml` 的 `ai.llm` 段）。下表为原始迁移方案，留档备查。

| 现状（geminiService.ts） | 迁移目标 | 说明 |
|--------------------------|---------|------|
| `generateQuestSuggestion(topic, childLevel, narrativeContext)` | `POST /api/v1/scn/ai/generate-quest`，body `{topic, child_level, narrative_context}`（父母 token） | 响应 `data` 字段与前端 `GeneratedQuest` 一一对应（snake_case），后端已内置同款 JSON schema 约束 |
| `evaluateTaskProof(taskTitle, imageBase64)` | `POST /api/v1/scn/ai/evaluate-proof`，body `{task_title, image_data_url}`（父母 token） | 注意：后端当前为纯文本评分（未传图），评分仅供参考，UI 文案不得声称"AI 看图评分"；多模态为后端待办 |
| `process.env.API_KEY`（浏览器持有 Gemini key） | 无——key 只存在于后端 config | **安全要求**：浏览器暴露 LLM key 属于泄漏，必须随本次移除一并清掉 |

推荐替代实现形态：新建 `services/apiClient.ts`（统一 Bearer 注入 + `code===0` 解包 + 错误抛出）与 `services/aiService.ts`（两个 AI 调用的薄封装）。

---

## 4. 团队约定：前端开发以契约文档为准

1. **契约唯一事实来源**：`docs/08-后端API契约.md`（基于 `server/` 真实代码）。运行时以 `/docs` OpenAPI 交叉验证。`06-API设计要点.md` 中与 08 冲突的内容（响应包裹、未实现接口）一律以 08 为准。
2. **先接口、后页面**：前端新增任何页面/功能，必须先确认契约中已有对应接口；没有 → 先创建后端 issue 补接口（或扩 schema），后端合并后再写前端代码。**禁止前端自行 Mock 一个后端不存在的接口形状直接开发**——联调期必然返工。
3. **字段缺口走后端**：前端确需而后端没有的字段，在后端 issue 中说明用途与来源，由后端回补 schema + 更新契约文档，前端再接。
4. **禁用兼容字段**：`creator_id/target_user_id/assignee_id/user_id/task_id/privilege_id/date` 等兼容旧前端的字段（契约中已标注）不得在新代码中使用；后端将在前端迁移完成后删除。
5. **接口变更同步流程**：
   - 改动后端路由/schema 的 PR，**必须同一 PR 更新 `docs/08-后端API契约.md`**（破坏性变更需在变更说明中列"前端影响"）。
   - 契约变更后在开发群/issue 通知前端侧；前端 `types.ts` 的接口层类型与契约保持同步提交。
   - 季度性对齐：后端跑 OpenAPI diff（`openapi diff` 或 `/docs` 导出对比），核对 08 是否漂移。
6. **Mock 数据退场**：`App.tsx` 中的 MOCK 常量在对应页面接入真实 API 后立即删除，不允许 Mock 与真实调用长期共存。

---

## 5. 联调差异记录（前端接入执行期发现）

接入阶段③（DEV-18）时对照后端真实代码（`server/app/api/v1/tasks.py`、`server/app/services/task_service.py`）发现的差异与约定，供后端/契约侧确认：

| # | 差异 | 现状与前端处理 | 建议 |
|---|------|---------------|------|
| D1 | **`POST /scn/task-instances/{id}/reject`（审核驳回）后端已实现，但 docs/08 §6 未收录** | 前端本阶段**未接入**（契约唯一事实来源为 docs/08）；ReviewTaskModal 仅提供 approve | 后端确认保留该接口后在 docs/08 §6 补条目（`TaskRejectRequest { comment? }`），前端再决定是否在审核弹窗加"驳回重做" |
| D2 | **后端 `start` 不限制"同孩子同时仅一个进行中任务"**（Mock 有此本地门禁） | 前端保留该 UX 门禁：接取第二个任务前弹 AbandonQuestModal 先放弃当前任务（纯展示层规则，依据服务端列表判断），后端行为未改动 | 若产品确认允许多任务并行，可移除前端门禁；若要求后端强约束，提后端 issue |
| D3 | 接取实际扣押金 = `coin_service.calculate_deposit_fee(task.time_deposit)`，当前实现恒等于 `time_deposit` | 前端 QuestCard 展示 `time_deposit` 即押金，无需改动；若后续引入手续费系数需同步契约 | 保持现状，留意 `calculate_deposit_fee` 未来变更 |
| D4 | `start` 余额不足抛 `validation_error`（HTTP 422），而非专用错误码 | 前端按 docs/10 §2.4 兜底：toast 后端 msg（文案已含"需要 X，当前 Y"） | 可选：后端为余额不足定义专用 error_code，便于前端精准提示 |

*记录基准：`packages/admin`@agent/leo2/301d69de19a0（DEV-18 阶段③）↔ `server/`@agent/leo2/682cb47f7926 基线，2026-10-10。*

---

*比对基准：`packages/admin`@develop cec241a ↔ `server/`@develop 09cf8fc，2026-10-09。*

## 5. 联调差异记录（前端接入实测，DEV 起各阶段追加）

> 前端按 docs/08 契约接入时发现的实际行为差异/补充。**仅记录，不代替契约**——后端确认后应回补 docs/08 并同步 `services/api/types.ts`。

### 阶段② 赛季（DEV-17，2026-10-10，基准 server@develop）

| # | 差异 | 前端处理 |
|---|------|---------|
| D1 | `GET /scn/seasons/history` 实际返回 `SeasonHistoryItem` 含 **`total_xp: int`**（契约 §5 只列 `season/total_tasks/completed_tasks`） | `api/types.ts` 已按实际补 `total_xp`；历史页直接展示，不再本地折算 |
| D2 | `POST /scn/seasons` 创建即激活：服务层先把本家庭激活赛季置 `is_active=false`，新赛季模型默认 `is_active=true` | 创建表单标注"创建后自动激活"；无激活赛季的引导直接进创建表单 |
| D3 | 单激活约束的冲突路径：并发下部分唯一索引 `ux_scn_season_active_per_family` 兜底，服务层捕获 `IntegrityError` → **409 `conflict`**，msg「该家庭已存在激活中的赛季,请稍后重试」 | 前端不自行判断单激活规则；`conflict` 原样透出后端 msg（errors.ts → 表单/确认层就地呈现） |
| D4 | `PATCH /scn/seasons/{id}` 无法清空 `end_date`：服务层 `if v is not None` 跳过 None 值 | 编辑表单不允许清空结束日期，字段下方注明"只能改为新日期"；如需支持清空请后端确认语义（显式 null） |
| D5 | `DELETE /scn/seasons/{id}` 成功返回 `data: {"deleted": true}`（契约未写明返回体） | 前端不读返回体；如后端要统一为 `data: null` 属破坏性变更，需同步契约 |

---
