# 07. 迭代计划与 Sprint 拆分

> 本章定位:把"接下来 2-3 个 Sprint 具体做什么"列清楚。
> 周期约定: 2 周 / Sprint,与原 `02-开发方案.md` 保持一致。
> 估算单位: 故事点(Story Point,斐波那契 1/2/3/5/8/13)。
> 团队规模参考: 后端 1-2 人 + Web 端 1 人 + 移动端 1-2 人(初期 1 人 Taro 双端)+ 测试 0.5 人。

---

## 0. 现状盘点(进入 Sprint A 之前)

| 模块 | 状态 | 备注 |
|---|---|---|
| 后端 MVP 闭环 | ✅ | 家庭/任务/状态机/审核/时间币/赛季/特权/AI 都有 |
| 后端指数 XP | ❌ | 本轮 Sprint A 第一件事 |
| 后端 P1 表 | ❌ | 模板库/隐藏任务/通知/看板/新手/分类/统计 |
| 后端 P1 API | ❌ | 见 06 章清单 |
| Web 管理后台 | ⚠️ | 跑通 mock,本轮 Sprint B 接真实 API |
| 家长端 Taro 工程 | ❌ | 本轮 Sprint C 起步 |
| 孩子端 Taro 工程 | ❌ | 本轮 Sprint C 起步 |
| docker-compose | ❌ | 本轮 Sprint A 末尾补齐 |

---

## 1. Sprint A(2 周) — 数值修订 + 后端 P1 全量 API

> 目标:把"指数 XP"和"三表五模块"全在后端落地,**不开新端**。

### 1.1 Epic A1 — 数值系统(指数 XP)

- Story A1.1(3): 把 `xp_service.xp_needed_for_level` 替换为 `xp_required_for_level(level, base_xp, growth)`,支持配置化。**改一处,影响所有调用**。
- Story A1.2(2): 升级后通知(LEVEL_UP 通知 + 推送钩子)。
- Story A1.3(5): `test_xp_service.py` 写满(曲线 + 边界 + 多步升级 + 配置覆盖)。
- Story A1.4(2): `POST /scn/task-instances/preview-xp` + `GET /scn/levels/curve`。

### 1.2 Epic A2 — 数据模型与迁移

- Story A2.1(5): 显式重写 `4bb73fc2e250_initial_schema.py`(对每张表用 `op.create_table`)。
- Story A2.2(3): 新增 `scn_task_template_library` + 索引。
- Story A2.3(3): 新增 `scn_hidden_quest` + 索引。
- Story A2.4(3): 新增 `scn_notification` + 索引。
- Story A2.5(3): 新增 `scn_onboarding_path` + `scn_onboarding_step`。
- Story A2.6(3): 新增 `scn_task_proof` + `scn_task_instance` 字段(`expire_at` / `xp_awarded` / `coin_delta` / `review_comment` / `abandon_count_at_submit`)。
- Story A2.7(2): 新增 `scn_stats_daily`。
- Story A2.8(1): `sys_child` 加 `onboarding_path_id` / `onboarding_step_id`。
- Story A2.9(1): `scn_task_template` 加 `category` / `library_id`。
- Story A2.10(3): `seed_dev.py` 脚本(幂等)。

### 1.3 Epic A3 — 模板库 API

- Story A3.1(5): `scn_template_library_service` + 路由。
- Story A3.2(2): 收藏/应用接口。
- Story A3.3(3): 测试(列表/搜索/应用/创建)。

### 1.4 Epic A4 — 隐藏任务 API

- Story A4.1(5): `scn_hidden_quest_service` + 路由(CRUD + 触发规则落地)。
- Story A4.2(3): "完成 N 任务后自动投放" worker(扫 `scn_task_instance`,匹配规则后生成新实例)。
- Story A4.3(2): 孩子端"惊喜弹窗"信息返回(在 `_to_read` 加 `is_hidden: bool`)。
- Story A4.4(3): 测试。

### 1.5 Epic A5 — 通知 API

- Story A5.1(5): `scn_notification_service` + 路由(列表/已读/未读数/设置)。
- Story A5.2(3): 升级 / 任务提交 / 任务审核 / 赛季开始的内置发送点。
- Story A5.3(5): 微信模板消息发送(封装 `wechat.send_template_msg`,带 retry/失败回退)。
- Story A5.4(3): `sys_notifications_config` 路由(Admin)。
- Story A5.5(3): 测试。

### 1.6 Epic A6 — 看板聚合

- Story A6.1(5): `daily_aggregate_job` 写 `scn_stats_daily`。
- Story A6.2(5): `/scn/stats/child/{id}` + `/scn/stats/family` 聚合服务。
- Story A6.3(3): `/sys/stats/overview`(Admin)。
- Story A6.4(3): 测试。

### 1.7 Epic A7 — 证据多文件 + 清理

- Story A7.1(5): `/scn/uploads` 关联 `task_instance_id`,写 `scn_task_proof`。
- Story A7.2(3): `/scn/task-instances/{id}/proofs` + `/scn/task-proofs/{id}`。
- Story A7.3(5): `/scn/evidence/purge(-preview)` + 软删/真删调度。
- Story A7.4(2): 测试。

### 1.8 Epic A8 — 新手引导 API

- Story A8.1(5): path/step CRUD + 启用规则。
- Story A8.2(3): 加入家庭/新赛季自动绑定 path 的钩子。
- Story A8.3(3): `/scn/onboarding/me` + 步骤完成。
- Story A8.4(3): 测试。

### 1.9 Epic A9 — 限时任务超时

- Story A9.1(3): 调度器增加 `expire_due_tasks_job`(每 5 分钟扫)。
- Story A9.2(3): 回收 50% 押金 + 状态置 EXPIRED + 通知。
- Story A9.3(2): 测试。

### 1.10 Epic A10 — 杂项

- Story A10.1(2): 账号注销/退出家庭接口。
- Story A10.2(1): `time_coin_balance` 强制重置(不依赖登录)。
- Story A10.3(1): 错误码扩展(写入 `app/common/exceptions.py` + 测试)。
- Story A10.4(2): 仓库根 `docker-compose.yml`(mysql + minio)。
- Story A10.5(2): 移除 `packages/client` 空目录,文档化 `parent/child` 工程占位。

### 1.11 Sprint A 总和

> 估算 ~120 故事点,**比 2 周 60-80 的常规负荷多**。
> 实操建议:
> - 把 Epic A6/A7 推到 Sprint B(看板与证据清理可后置);
> - Epic A1 + A2 必做,这是后面所有端的"地基"。

### 1.12 Sprint A 验收

- `pytest` 全绿(包含新 XP / 新表 / 通知 / 模板库 / 隐藏任务 / 新手 / 超时回收);
- `alembic upgrade head` + `alembic downgrade base` 双向 OK;
- 旧 mock 流程在真实 API 上能跑通(用 curl/Postman 验证至少一条完整链路);
- OpenAPI 文档在 `/docs` 展示新增接口。

---

## 2. Sprint B(2 周) — Web 管理后台接真实 API + 三端基础

> 目标:admin 端换真数据;同时把 Taro 工程骨架立起来,跑通登录。

### 2.1 Epic B1 — Admin 接真实 API

- Story B1.1(5): 抽出 `services/api.ts`(fetch 封装 + JWT 注入 + 错误处理)。
- Story B1.2(5): 登录页 + Token 持久化(localStorage / sessionStorage)。
- Story B1.3(3): 切换 Mock → 真实:任务列表/创建/审核/孩子档案。
- Story B1.4(3): 切换:赛季/主题/特权模板管理。
- Story B1.5(3): 切换:时间币配置。
- Story B1.6(5): 看板接入 `/scn/stats/family` + `/sys/stats/overview`。
- Story B1.7(5): 模板库管理(CRUD 系统预置)。
- Story B1.8(5): 隐藏任务投放 UI。
- Story B1.9(3): 通知配置(类型开关 / 必达列表)。
- Story B1.10(3): 验收:Admin 端能完成"创建任务 → 孩子提交(用 curl 模拟) → 审核 → 看统计"全链路。

### 2.2 Epic B2 — 家长端 Taro 工程初始化

- Story B2.1(3): 初始化 Taro 4 + React 18 + TS + UnoCSS,工程名 `packages/parent`。
- Story B2.2(2): 配置 weapp / h5 双平台 build。
- Story B2.3(3): 微信登录页(`/sys/auth/wechat/jscode`,Taro.login + 跳家庭/邀请码页)。
- Story B2.4(3): 邀请码加入家庭页。
- Story B2.5(3): 家长首页(家庭概览:成员数、本周完成数、今日待审)。
- Story B2.6(3): 验收:H5 跑得通"登录 → 加入家庭 → 看到成员"。

### 2.3 Epic B3 — 孩子端 Taro 工程初始化

- Story B3.1(3): 初始化 Taro 4 + React 18 + TS + UnoCSS,工程名 `packages/child`。
- Story B3.2(2): 双平台配置。
- Story B3.3(3): 微信登录。
- Story B3.4(3): Quest Board 首页(按状态分组显示任务)。
- Story B3.5(3): 任务详情(看 lore / 押金 / 倒计时)。
- Story B3.6(3): 验收:H5 跑得通"登录 → 看到任务列表 → 任务详情"。

### 2.4 Epic B4 — 工程化

- Story B4.1(2): 仓库根 `pnpm-workspace.yaml` 统一管理 packages。
- Story B4.2(3): 后端 `pytest` 套件(目标覆盖率 ≥ 60%)。
- Story B4.3(2): 前端 `eslint` + `tsc --noEmit` 在 CI 跑通。
- Story B4.4(2): `pre-commit`(ruff + eslint)基础钩子。

### 2.5 Sprint B 总和

~70 故事点,可行。
风险: Taro 端首次接入会有"包体积/构建速度/小程序兼容"等小坑,留 buffer。

### 2.6 Sprint B 验收

- Admin 端全功能走真 API;
- Parent/Child H5 双端"登录 + 进入主页"全跑通;
- pnpm + uv 一键起全栈(README 更新)。

---

## 3. Sprint C(2 周) — 三端核心 P0/P1 闭环

> 目标:把家长端/孩子端的核心路径补全,**达到对外可演示**。

### 3.1 家长端

- C-Parent-1(5): 创建任务(模板/AI/手动)表单 + 上传封面图。
- C-Parent-2(5): 任务列表/详情/编辑/删除。
- C-Parent-3(5): 审核页(看证据 + 5 星 + 评语 + 通过/驳回)。
- C-Parent-4(3): 孩子档案(等级/XP/币/今日/历史曲线)。
- C-Parent-5(5): 数据看板(家庭维度)。
- C-Parent-6(3): 通知中心(列表/已读/未读数/设置)。
- C-Parent-7(3): 模板库(浏览/搜索/应用/收藏)。
- C-Parent-8(3): 隐藏任务投放 + 列表。
- C-Parent-9(2): 个人中心(改昵称/头像)。

### 3.2 孩子端

- C-Child-1(3): Quest Board(按状态分组 + 主题色 + 角色卡)。
- C-Child-2(5): 接任务(押金提示) / 提交(多图/视频/音频) / 放弃(惩罚提示)。
- C-Child-3(3): 等级进度条 + 升级动画(可用 Lottie/SVG)。
- C-Child-4(3): 特权树(已解锁/未解锁灰显)。
- C-Child-5(2): 兑换记录(用一次特权)。
- C-Child-6(3): 通知中心(简化 UI,只显示任务审核/升级/赛季事件)。
- C-Child-7(3): 新手引导(3 步引导 + 完成后弹"正式任务已解锁")。
- C-Child-8(2): 隐藏任务惊喜弹窗。
- C-Child-9(2): 限时任务倒计时 / 超时回收提示。
- C-Child-10(1): 个人中心(改昵称/头像)。

### 3.3 公共

- C-Common-1(3): 主题切换(读 `/scn/seasons/active` + `scn_theme_style`,注入 CSS 变量)。
- C-Common-2(3): 错误/Loading/空状态统一组件。
- C-Common-3(2): 上传组件封装(对接 `/scn/uploads`)。
- C-Common-4(3): 联调测试 + 修 bug。
- C-Common-5(3): 体验打磨(动画/震动/音效 — 孩子端重点)。

### 3.4 Sprint C 总和

~70-80 故事点。**功能量大**,建议:
- 任务审核/数据看板可做"基础版",UI 美化放到后续;
- 孩子端的"升级动画"先用 CSS 过渡,Lottie 留到 Sprint D。

### 3.5 Sprint C 验收(对外演示级别)

- 演示完整链路:父母创建任务 → 孩子接 → 提交证据 → 父母审核 → 孩子升级 → 解锁特权;
- 演示隐藏任务投放与惊喜弹窗;
- 演示家长数据看板有真实数据(走 `scn_stats_daily`);
- 演示新手引导流程;
- H5 + 微信小程序两端一致(若已申请小程序 ID)。

---

## 4. Sprint D 及之后(V2.x)

> Sprint C 之后,本期 v2 范围基本交付。后续看用户反馈再排期。

- D-1: 智能任务推荐(P2 11.1)
- D-2: 考核/转职任务(P2 11.2)
- D-3: 成长记录时间线(P2 11.3)
- D-4: 微信模板消息稳定性 & 频控优化
- D-5: 性能 / 缓存 / 分页(若数据量上来)
- D-6: 国际化(若需要)

---

## 5. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| Taro 一码多端差异(尤其是 H5 动画) | 孩子端体验打折 | 关键动画提供"小程序"和"H5"两套实现,默认 H5 用 CSS |
| 微信模板消息需公众号资质 | 通知延迟上线 | Sprint A 先落地"站内通知"完整闭环,微信模板消息在配置缺失时降级 |
| LLM 调用费用/稳定性 | 任务 AI 文案可能 5xx | 后端加 2 次重试 + 兜底(返回"默认 lore"模板) |
| 指数 XP 曲线与产品预期不符 | 后期升级太难 | 数值集中在 `XpConfig`,通过环境变量调参,无需发版 |
| 多孩子并发(同时接任务) | 时间币并发扣款 | 借助 `SELECT ... FOR UPDATE` 或 Redis 锁(本期用 DB 行锁) |
| Taro 工程与 Vite admin 共享 TS 类型 | 维护成本 | 用 `openapi-typescript` 从后端 OpenAPI 自动生成 |
| 现有 mock 数据在切换真实 API 时漏改 | UI 报错 | B1.x 切一处跑一处,Sprint B 末统一扫一遍 |
| 孩子端"惊喜弹窗"易被家长绕过 | 隐藏任务失去意义 | 后端不返回 `is_hidden=true` 的列表项外的任何元数据 |

---

## 6. 度量指标(Sprint C 末对齐)

| 指标 | 目标 |
|---|---|
| 端到端 P95 任务创建-审核完成 | < 30s(去掉家长审核人工时间) |
| 孩子端首屏 | < 2s(H5)/ < 1.5s(小程序) |
| LLM 任务文案生成 P95 | < 4s(单次) |
| 时间币流水 100% 不漏(对账 0 差异) | 必达 |
| 通知发送成功率 | > 98% |
| Taro 包体积(微信小程序主包) | < 1.5MB |

---

## 7. 实施纪律(本轮新立)

1. **本轮不再改 Sprint 计划外的范围** — 任何新增需求进入 Backlog,不在 Sprint 内追加。
2. **每日站会** — 同步阻塞,只问"今天做什么 / 阻塞是什么 / 是否要调整"。
3. **PR 必须跑 CI** — 任何 push 都触发 lint + test,失败阻塞合并。
4. **本轮文档同步** — 任何代码变更导致文档失真,必须在 PR 里附 `docs/xx` 修订。
5. **跨端类型同步** — 后端改 OpenAPI,前端用 `openapi-typescript` 重新生成,禁止手抄字段。
