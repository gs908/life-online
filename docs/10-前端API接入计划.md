# 10. 前端 API 接入计划（DEV-10 交付）

> 依据（唯一事实来源）：`docs/08-后端API契约.md`、`docs/09-前后端类型对齐与Mock映射.md`。
> 规划对象：现有 `packages/admin` ＝ **产品移动端 · 家长管理功能**（业主 2026-10-09 术语澄清后的口径），按 **React + Vant** 体系演进。
> **系统管理后台（shadcn admin）不在本计划范围内**——凡归属该端的能力，本文仅标注"归属系统管理后台、待独立端建设"，不做接入设计。
> 本 issue 不要求完成全部接入；本文 + `packages/admin/src/services/api/` 代码骨架是后续拆分前端接入子 issue 的基础。

---

## 1. 端划分与 API Client 归属

| 端 | 定位 | 技术栈 | API Client 关系 |
|---|---|---|---|
| 产品移动端（孩子使用 + 家长管理） | 产品玩法：接任务、提交、审核、赛季、特权 | React + Vant（现有 `packages/admin` 演进） | **本计划的落地载体**，接入骨架的第一消费方 |
| 系统管理后台 | 基础数据/系统管理（模板库、特权模板、平台配置） | shadcn admin（待独立端建设） | **复用同一套 api-client 包**，接入设计不在本 issue 范围 |
| 孩子端（小程序形态待定） | 孩子日常使用 | React + Vant | 复用同一套 api-client 包 |

**结论：API Client 基础层按端无关设计。** 骨架现落在 `packages/admin/src/services/api/`（第一消费方），待孩子端/系统管理后台启动后**原样提升为 `packages/api-client` 独立包**（纯 TS、零 React 依赖、零 DOM API 依赖——token 存储走注入的 StorageAdapter，见 §2.3）。提升时机：第二个消费方立项时。

## 2. API Client 架构设计

### 2.1 分层与目录（骨架已建）

```
packages/admin/src/services/
├── api/                    # 端无关 API Client（未来提升为 packages/api-client）
│   ├── http.ts             # 请求核心：BASE_URL、Bearer 注入、{code:0} 解包、错误抛出、401 刷新重试
│   ├── token.ts            # token 存取 + 单飞刷新（single-flight）
│   ├── errors.ts           # ApiError（携带后端 error_code / msg / http status）
│   ├── types.ts            # 契约 DTO（snake_case，与 docs/08 逐字段一致）
│   ├── modules/
│   │   ├── auth.ts         # /sys/auth/*、/sys/accounts/*、/sys/families/*
│   │   ├── seasons.ts      # /scn/seasons/*
│   │   ├── tasks.ts        # /scn/task-instances/*
│   │   ├── coins.ts        # /scn/time-coin-logs/*、/scn/time-configs/*
│   │   ├── privileges.ts   # /scn/privileges/*、/scn/privilege-uses/*
│   │   ├── uploads.ts      # /sys/uploads
│   │   └── ai.ts           # /scn/ai/*（替代 geminiService）
│   └── index.ts            # 统一出口
└── geminiService.ts        # ⚠️ 待删除（阶段 6，见 §5）
```

调用方向：`组件/hook → services/api/modules/* → http.ts`。**禁止组件直接 fetch、禁止绕过解包层。**

### 2.2 请求核心约定（来自 docs/08 §0）

- 统一前缀 `/api/v1`；BASE_URL 经环境变量注入（`VITE_API_BASE_URL`），开发期代理到本地 server。
- 成功判定：`code === 0`；否则抛 `ApiError(error_code, msg, httpStatus)`——**不使用** 旧 06 文档的 `ok` 包裹。
- 命名：**snake_case 直传，不做 camelCase 转换层**（docs/09 G1 推荐项，避免双份字段名）。前端 `types.ts` 的接口层类型按 `api/types.ts` 重写。
- 时间字段统一 ISO 8601 字符串（`date`→`YYYY-MM-DD`、`time`→`HH:MM:SS`），展示层格式化（docs/09 G3）。
- 分页：`{page, page_size}` → `PageResult<T>{items,total,page,page_size}`。
- **兼容旧字段禁用清单**（新代码一律不读不写）：`creator_id / target_user_id / assignee_id / user_id / task_id / privilege_id / date`；任务指派用 `target_child_id / assignee_child_id`（且是**冒险者档案 child_id**，不是账号 id）。

### 2.3 Token 存储与刷新策略

| 项 | 决策 | 理由 |
|---|---|---|
| access_token | 内存变量 + localStorage 持久化（经 StorageAdapter 注入） | H5 场景刷新页面不丢登录；XSS 面与现有 Vant/H5 原型同级，暂不引入 HttpOnly Cookie 方案（需后端改 CORS+Cookie，成本高，如有安全要求再提后端 issue） |
| refresh_token | localStorage 独立 key，随 `/sys/auth/refresh` 轮换 | 契约 `TokenPair` 每次刷新返回新对 |
| 主动刷新 | 按 `access_expires_in` 设定时器提前 60s 刷新 | 避免请求中途过期 |
| 被动兜底 | 401 → 单飞刷新（并发请求只触发一次 refresh）→ 重放原请求一次；再失败 → 清 token、广播登出事件 | 防止并发 401 引发刷新风暴 |
| 登出 | `POST /sys/auth/logout`（尽力而为）+ 清两把 key + 事件通知 UI 回登录页 | 契约 §2 |
| 小程序端差异 | StorageAdapter 注入 `wx.getStorageSync/setStorageSync` 实现 | 端无关设计的关键：核心层不 import 任何平台 API |

`NeedInviteCodeError`（微信登录无账号）由 auth 模块识别为独立错误类型，UI 引导走邀请码加入流程（`/sys/families/join`）。

### 2.4 错误处理与用户反馈

| error_code | HTTP | UI 处理 |
|---|---|---|
| `unauthorized` | 401 | 刷新→重试→跳登录（见 §2.3） |
| `permission_denied` | 403 | toast"无权限"，不跳转 |
| `not_found` | 404 | toast + 刷新列表 |
| `conflict` | 409 | toast 后端 msg（如重复接取） |
| `validation_error` | 422 | 表单内联纠错（`data` 为 pydantic errors 数组） |
| `external_service_error` | 502 | toast"稍后重试"（LLM/微信/存储） |
| 其他/网络错误 | — | toast 通用错误；请求层不做自动重试（除 401 流程外） |

## 3. Mock → 后端接口映射总表

docs/09 §2 已给出逐条映射，本表补 **UI 载体**（哪些文件动手）与**替换阶段号**：

| Mock（App.tsx / 组件） | 后端接口 | UI 载体 | 阶段 |
|---|---|---|---|
| `MOCK_USERS` + `switchUser` 角色切换 | `/sys/auth/*`、`/sys/accounts/me`、`/sys/families/me`；按 `UserRead.role` 渲染 | App.tsx、Header.tsx | ① |
| `DEFAULT_SEASON` / `activeSeason` | `GET /scn/seasons/active` + CRUD + `activate` | SeasonConfigModal | ② |
| `seasonHistory: Season[]` | `GET /scn/seasons/history`（`SeasonHistoryItem`，含完成度统计） | SeasonHistory.tsx | ② |
| `INITIAL_TASKS` / `tasks` + 全部本地状态机 | `GET /scn/task-instances`（分页+season_id/status/assignee 过滤） | ChildDashboard、ParentDashboard、QuestCard | ③ |
| `handleAddTask`（本地 push） | `POST /scn/task-instances`（TaskCreate） | AddTaskModal | ③ |
| `startQuest`（本地扣押金） | `POST .../start`（后端扣押金） | ChildDashboard | ③ |
| `handleAbandonQuest`（本地退款/罚币） | `POST .../abandon`（后端罚币） | AbandonQuestModal | ③ |
| `handleSubmitTask`（base64 存 state） | `POST /sys/uploads` → `POST .../submit{proof_object_key}` | SubmitTaskModal | ③提交流、⑤上传细节 |
| `handleApproveTask`（本地 XP 倍率计算） | `POST .../approve{rating, comment}`（后端发 XP/退扣币） | ReviewTaskModal | ③ |
| `handleDeleteTask` | `DELETE /scn/task-instances/{id}` | ParentDashboard | ③ |
| `DEFAULT_TIME_CONFIG` + 本地每日重置 | `GET/PUT /scn/time-configs/me`；重置在 `GET /sys/accounts/me` 服务端完成 | TimeConfigModal、App.tsx daily-reset effect | ④ |
| `childUser.timeCoins` 本地增减 | 以 `UserRead.time_coins` 为准，变更后 refetch | XPBar、Header | ④ |
| （无页面） | `GET /scn/time-coin-logs` + `POST .../adjust` | **新增**流水页 | ④ |
| `redemptionHistory` / 特权树 | `/scn/privileges/templates、unlocks、uses`、`/scn/privilege-uses` | PrivilegeTree、ParentDashboard | ④（随时间币一起，接口已在 09 映射） |
| `proofImage` base64 | `POST /sys/uploads`（multipart，purpose=`task_proof`）；展示用 `proof_url` | SubmitTaskModal、QuestCard | ⑤ |
| `geminiService.generateQuestSuggestion` | `POST /scn/ai/generate-quest` | AddTaskModal | ⑥ |
| `geminiService.evaluateTaskProof` | `POST /scn/ai/evaluate-proof` | ReviewTaskModal | ⑥ |

## 4. 替换顺序与各阶段细案

> 顺序固定：**当前用户 → 赛季 → 任务 → 时间币 → 上传 → AI**（派发约束）。每阶段结束 Mock 对应常量/逻辑**立即删除**（docs/09 §4.6，不共存）。每阶段独立可验收、可拆一个子 issue。

### 阶段① 当前用户（登录态 + 家庭上下文）
- 接口：`POST /sys/auth/wechat/jscode`（小程序）/ 邀请码流程 `POST /sys/families/join`；`GET /sys/auth/me`、`GET /sys/accounts/me`、`GET /sys/families/me`。
- 改造：App.tsx 删 `MOCK_USERS/switchUser`，增加 AuthProvider（登录页 + 角色路由：GUILD_MASTER→ParentDashboard，ADVENTURER→ChildDashboard）；Header 读真实用户。
- 删除：Mock 用户、本地每日重置 effect 的本地比对部分（`lastLoginDate` 逻辑交后端，P5）。
- 验收：无 Mock 用户；刷新页面保持登录；401 走刷新→重登。
- ⚠️ 前置缺口：H5 网页端登录通道契约未覆盖（见 §6-1），拆 issue 前需先落该后端 issue。

### 阶段② 赛季
- 接口：`GET /scn/seasons/active`（无激活赛季时 `data:null` → 引导创建）、列表、`POST/PATCH/activate/DELETE`、`GET /scn/seasons/history`。
- 改造：SeasonConfigModal 改为真实 CRUD；`themeId` 用 `ThemeId` 枚举（保留 `constants/themes.ts` 素材映射）；SeasonHistory 改用 `SeasonHistoryItem` 展示完成度（S3，能力增强）。
- 删除：`DEFAULT_SEASON`、`seasonHistory: Season[]` 本地态。
- 验收：创建→激活→展示全链路走后端；无激活赛季有引导。

### 阶段③ 任务
- 接口：`GET /scn/task-instances`（分页 + `season_id/status/assignee_child_id` 过滤）、`POST`（创建）、`start/submit/approve/abandon/DELETE`。
- 改造：App.tsx 任务本地状态机整体退役，改为请求 + 响应驱动（或引入轻量数据层：TanStack Query 建议在拆 issue 时定，本骨架不预置）。
- **删除的业务逻辑（重点回归风险）**：本地押金扣减/退款（后端 start/approve/abandon 已处理）、本地 XP 倍率与升级计算（后端 approve 发 XP）、`requiredStartTime` 本地提醒的本地状态依赖（提醒 toast 保留，数据源改 TaskRead）。
- 提交流：SubmitTaskModal 先改走上传占位（阶段⑤完成前可暂以"无图提交"灰度？——**不可**：`proof_object_key` 必填，故本阶段必须先把上传打通，见顺序说明：**实现上③的 submit 依赖⑤的接口可用，联调时按 ③→⑤ 交替**，但改造切面仍按本顺序评审）。
- 验收：接取/提交/审核/放弃全链路后端驱动；`conflict`（重复接取）有友好提示。

### 阶段④ 时间币（含流水页、特权、时间币配置）
- 接口：`GET /scn/time-coin-logs`、`POST /scn/time-coin-logs/adjust`；`GET/PUT /scn/time-configs/me`（**exceptions 数组整体替换**，C1/C3）；特权 `/scn/privileges/*`、`/scn/privilege-uses`。
- 改造：TimeConfigModal 数据结构改数组；新增"时间币流水"页（后端能力已备，M2）；余额一律 refetch `UserRead.time_coins`，不再本地加减。
- 删除：`DEFAULT_TIME_CONFIG`、所有本地币值变更。
- 验收：调整/流水/配置保存正确；周末 exceptions 生效显示正确。

### 阶段⑤ 上传
- 接口：`POST /sys/uploads`（multipart：`file` + `purpose`）。
- 改造：SubmitTaskModal 从 base64 改 `<input type=file>`/Vant Uploader → multipart 上传 → 拿 `object_key` 提交 submit；头像/赛季横幅同理（purpose 区分）。展示统一 `access_url`（任务证明用 TaskRead.`proof_url`）。
- 删除：`proofImage` base64 类型与数据流。
- 验收：上传→提交→列表展示 proof_url 全链路。

### 阶段⑥ AI（Gemini 直连移除）
见 §5。

## 5. Gemini 直连移除（强制，随阶段⑥执行）

1. 删除 `packages/admin/src/services/geminiService.ts` 整文件；从 `package.json` 移除 `@google/genai` 依赖；清理构建配置中的 `API_KEY` 注入（**浏览器持有 LLM key 属于密钥泄漏，必须一并清除**）。
2. `services/api/modules/ai.ts` 提供等价薄封装：
   - `generateQuest({topic, child_level, narrative_context})` → `POST /scn/ai/generate-quest`（父母 token），`data` 即 `{title, description, lore_snippet, xp_reward, type, reminder_message?}`（snake_case，后端内置同款 JSON schema 约束）；
   - `evaluateProof({task_title, image_data_url})` → `POST /scn/ai/evaluate-proof`（父母 token）。
3. UI 约束：后端当前为**纯文本评分（未看图）**，ReviewTaskModal 文案不得声称"AI 看图评分"；多模态是后端待办（§6-3）。

## 6. 对后端契约的反向校验（缺口清单 → 后端 issue 候选）

按本计划推进时，以下契约缺口/疑点需后端确认或补接口（**前端禁止自行 Mock 后端不存在的形状**）：

| # | 缺口 | 影响 | 建议 |
|---|---|---|---|
| 1 | **H5/网页端登录通道缺失**：契约仅有微信小程序 `jscode` 换 token，`packages/admin` 是浏览器 H5，无法走 jscode | 阶段① 直接被卡 | 提后端 issue：微信网页授权（OAuth2 code）或开发期账号登录接口 |
| 2 | 通知/提醒列表 API 未暴露（TaskRead 有 `reminder_*` 字段，但无拉取已产生提醒的接口） | TIMED 任务到点提醒只能纯前端本地算 | 提后端 issue（docs/09 已标注 🔴） |
| 3 | `evaluate-proof` 未把图片送入模型（纯文本评分） | 家长端 AI 评分参考价值有限 | 后端待办；前端文案先规避"看图"表述 |
| 4 | **审核 XP 计算规则未在契约中成文**：Mock 有 4/5 星加成、超时惩罚、快速完成加成等倍率；契约仅写 approve"发 XP" | 前后端数值行为可能不一致，影响产品数值 | 请后端在契约/数值文档（04）补 approve 的 XP 公式；差异处由业主裁决 |
| 5 | `GET /scn/levels/curve`、`POST .../preview-xp`、模板库接口：**未实现，禁止对接** | AddTaskModal 若需 XP 预览需等后端 | 需要时再提后端 issue |
| 6 | `PATCH /sys/accounts/me` 忽略 `privileges_unlocked` | 家长端不能手工改解锁集合 | 用 `/scn/privileges/*` 流程即可；如需手工解锁再提后端 issue |

## 7. 后续拆分建议（子 issue 粒度）

- **DEV-10-a 阶段①**：登录态 + 家庭上下文（前置：§6-1 后端 issue）
- **DEV-10-b 阶段②**：赛季接入
- **DEV-10-c 阶段③**：任务全链路（与 DEV-10-e 上传联调交替）
- **DEV-10-d 阶段④**：时间币/流水页/特权/配置
- **DEV-10-e 阶段⑤**：上传改造
- **DEV-10-f 阶段⑥**：AI 切换 + geminiService/@google/genai/API_KEY 退场
- 另：`packages/admin` → React + Vant 的 UI 体系迁移是独立工程线，不混入上述接入 issue；`packages/api-client` 独立包提升在第二个端立项时执行。

---

*基准：develop（docs/08@09cf8fc 核对版）+ `packages/admin` 现状（Mock 原型）。本文与 docs/08/09 冲突时以后两者为准。*
