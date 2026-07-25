# 06. API 设计要点(P1 补足与扩展)

> 本章定位:把 v2.0 涉及的**新增 / 修改** API 列表化,作为前后端联调契约。
> 已有 API 不在此重复(见 `server/app/api/v1/` 与 OpenAPI `http://host:8000/docs`)。

---

## 0. 通用约定(沿用)

- 前缀: `/api/v1`
- 响应: `ApiResponse<T> = { ok: true, data: T }` / `{ ok: false, error: { code, message, details? } }`
- 鉴权: `Authorization: Bearer <access>`,refresh 走 `/sys/auth/refresh`
- 资源命名: `sys_*`(身份) / `scn_*`(业务)
- 列表: 默认分页 `?page=1&page_size=20`;`page_size <= 200`
- 错误码: 由 `app/common/exceptions.py` 集中定义;前端按 `code` 分类处理

## 1. 数值/任务增强

### 1.1 升级曲线查询(给前端展示用)

```
GET /api/v1/scn/levels/curve?upto=20
→ { ok: true, data: [{ level: 1, xp_required: 200, cumulative: 0 }, ...] }
```

> 前端做"距下一级 X / Y"显示,直接调此接口拉一份本地缓存。

### 1.2 任务 XP 预估

```
POST /api/v1/scn/task-instances/preview-xp
Body: { base_xp, rating, started_at, required_start_time, is_challenge, is_hidden, chain_index, chain_total }
→ { ok: true, data: { final_xp: 320, multiplier_breakdown: {...} } }
```

> 孩子端在提交前可看"按当前表现能拿多少 XP"。

### 1.3 限时任务超时回收(内部)

> 不暴露,worker 调度,见 `app/workers/scheduler.py`。

## 2. 任务模板库

### 2.1 列表/搜索

```
GET /api/v1/scn/template-library?category=STUDY&tag=math&keyword=...
→ { ok: true, data: PageResult<TemplateLibraryRead> }
```

### 2.2 详情 / 收藏 / 应用

```
GET    /api/v1/scn/template-library/{id}
POST   /api/v1/scn/template-library/{id}/favorite   (Parent)
POST   /api/v1/scn/template-library/{id}/apply      (Parent) → 创建任务 + 跳转
```

### 2.3 家庭自建(Parent)

```
POST   /api/v1/scn/template-library                  Body: TemplateLibraryCreate
GET    /api/v1/scn/template-library/mine             (Parent 自己的)
```

## 3. 隐藏任务

### 3.1 投放

```
POST /api/v1/scn/hidden-quests            (Parent/Admin) Body: HiddenQuestCreate
GET  /api/v1/scn/hidden-quests?status=active|inactive
GET  /api/v1/scn/hidden-quests/{id}
PATCH /api/v1/scn/hidden-quests/{id}     (停用/调整)
```

### 3.2 孩子端(只能看到"出现的新任务")

> 不暴露"隐藏任务"概念。前端调 `/scn/task-instances?status=AVAILABLE`,
> 当某条 `instance.template_id` 来自 `scn_hidden_quest` 时,
> 走"惊喜弹窗"特殊 UI(任务详情里加 `is_hidden: true` 字段由后端返回)。

## 4. 通知

### 4.1 列表 / 未读数

```
GET /api/v1/scn/notifications?unread=true&page=1&page_size=20
GET /api/v1/scn/notifications/unread-count
```

### 4.2 标记已读

```
POST  /api/v1/scn/notifications/{id}/read
POST  /api/v1/scn/notifications/read-all
```

### 4.3 通知设置(每个用户)

```
GET   /api/v1/scn/notifications/settings
PATCH /api/v1/scn/notifications/settings
Body: { channel_inapp: bool, channel_wechat: bool, type_overrides: { TASK_APPROVED: false, ... } }
```

### 4.4 微信模板消息发送(内部/后台)

> 在 `app/services/notification_service.py` 内部,
> `send_wechat_template(user, type, payload)` 走 `wechat.send_template_msg`,
> 失败回退站内。

### 4.5 通知管理(Admin)

```
GET   /api/v1/sys/notifications/config       (类型、模板、必达列表)
PATCH /api/v1/sys/notifications/config
```

## 5. 数据看板

### 5.1 孩子维度(Parent 端)

```
GET /api/v1/scn/stats/child/{child_id}?from=2026-07-01&to=2026-07-25
→ {
    ok: true,
    data: {
      quests_completed: 12,
      quests_submitted: 14,
      quests_rejected: 1,
      quests_abandoned: 0,
      avg_rating: 4.3,
      xp_earned: 1320,
      time_coins_earned: 130,     // 仅押金退还
      time_coins_spent: 110,      // 押金扣除
      minutes_active: 320,
      by_type: { DAILY: 9, CHALLENGE: 2, TIMED: 1 },
      by_category: { STUDY: 5, SPORT: 3, CHORE: 2, ... },
      daily: [{ date: "2026-07-20", completed: 2, xp: 250 }, ...]  // 来自 scn_stats_daily
    }
}
```

### 5.2 家庭维度(Parent/Admin)

```
GET /api/v1/scn/stats/family?from=...&to=...
```

### 5.3 全平台(Admin)

```
GET /api/v1/sys/stats/overview
```

## 6. 任务证据(多图/视频/音频)

### 6.1 上传(已实现,改字段)

```
POST /api/v1/scn/uploads
Body(form): { file, purpose=task_proof, task_instance_id? }
→ { ok: true, data: { object_key, public_url, proof_id } }
```

> 本轮把 `task_instance_id` 关联写入 `scn_task_proof`,返回 `proof_id`。
> 任务实例表上 `proof_object_key` 保留做"主图"展示。

### 6.2 列/删

```
GET    /api/v1/scn/task-instances/{id}/proofs
DELETE /api/v1/scn/task-proofs/{proof_id}    (Parent 或 owner child,24h 内允许)
```

### 6.3 清理

```
GET   /api/v1/scn/evidence/purge-preview?older_than_days=180
      → { ok: true, data: { will_delete: 23, total_size_mb: 145.2, items: [...] } }

POST  /api/v1/scn/evidence/purge
Body: { older_than_days: 180, proof_ids?: [..], hard_delete?: false }
      → 软删/真删
```

## 7. 任务分类(本期 P1 末,字段先行)

```
GET /api/v1/scn/task-categories
→ { ok: true, data: [{ code: "STUDY", name: "学习", icon: "📚" }, ...] }
```

> 表由管理后台维护,本轮只需要在 `scn_task_template` 字段里能存 `category` 即可。

## 8. 新手引导

### 8.1 孩子端(看自己进度)

```
GET /api/v1/scn/onboarding/me
→ { ok: true, data: { path: {...}, current_step: {...}, completed_steps: 1, total_steps: 3 } }
```

### 8.2 完成任务步骤

```
POST /api/v1/scn/onboarding/steps/{step_id}/complete
```

### 8.3 父母/后台管理

```
GET/POST/PATCH/DELETE /api/v1/scn/onboarding/paths       (Parent 自建 / Admin 系统)
GET/POST/PATCH/DELETE /api/v1/scn/onboarding/paths/{id}/steps
```

## 9. 账号

### 9.1 注销(本轮补)

```
POST /api/v1/sys/accounts/me/deactivate      (Parent/Child)
Body: { confirm: true }
→ 30 天软注销,期间可恢复;超期物理删除(留审计日志)
```

### 9.2 退出家庭

```
POST /api/v1/sys/accounts/me/leave-family   (Parent 不能退出自己创建的家庭;Child 可退出)
```

## 10. 主题与赛季补充

### 10.1 赛季切换(Parent)

```
POST /api/v1/scn/seasons/{id}/activate    (Parent/Admin)
```

> 已实现。

### 10.2 主题 AI 生成(已实现 + 增强)

```
POST /api/v1/scn/themes/generate
Body: { scene_prompt, name?, activate? }
```

> 已实现,本轮把 `family_id` 隔离做好(只能为自己家庭生成)。

## 11. 任务状态机(本轮增强)

新增事件/状态:

```
status: AVAILABLE
  → IN_PROGRESS         (孩子接取,扣押金)
  → EXPIRED             (限时任务超时,worker 触发,扣 50% 押金)
status: IN_PROGRESS
  → PENDING_REVIEW      (孩子提交,附 proof)
  → AVAILABLE           (孩子放弃,按规则退押金)
status: PENDING_REVIEW
  → COMPLETED           (Parent 通过,发 XP,退押金)
  → IN_PROGRESS         (Parent 驳回,孩子重新提交)
```

```
POST /api/v1/scn/task-instances/{id}/expire     (内部 worker 调;Admin 手动)
```

## 12. 时间币补充

### 12.1 强制重置(Admin)

```
POST /api/v1/scn/coins/reset
Body: { child_id, reason }
```

### 12.2 流水(已实现)

```
GET /api/v1/scn/coins/transactions?child_id=&from=&to=
```

> 已在 `coin_service.list_transactions`。

## 13. 错误码扩展

| 场景 | code |
|---|---|
| 时间币不足 | `INSUFFICIENT_TIME_COIN` |
| 任务已过期 | `TASK_EXPIRED` |
| 任务状态非法 | `INVALID_TASK_STATUS` |
| 跨家庭操作 | `CROSS_FAMILY_DENIED` |
| 等级不足 | `LEVEL_REQUIRED` |
| 模板已下架 | `TEMPLATE_RETIRED` |
| 通知已发 | `NOTIFICATION_ALREADY_SENT` |
| LLM 调用失败 | `LLM_UNAVAILABLE` |
| 微信模板消息发送失败 | `WECHAT_TMPL_FAILED` |

## 14. OpenAPI 维护约定

- 所有路由必须写 `summary` / `description`;
- 路径参数 + Query + Body + Response 全部声明 Pydantic model;
- 任何**破坏性**变更(删除/重命名字段、改 URL)必须:
  1. 先在 PR 里写"API 变更说明";
  2. 在 OpenAPI 的 `description` 顶部加 deprecation 标记;
  3. 与前端协调过渡期(>=1 Sprint)。

## 15. 本轮 P1 新增 API 一览(快速清单)

| 模块 | 新接口 |
|---|---|
| 等级 | `GET /scn/levels/curve`, `POST /scn/task-instances/preview-xp` |
| 模板库 | `GET/POST /scn/template-library`, `POST .../{id}/apply`, `POST .../{id}/favorite` |
| 隐藏任务 | `CRUD /scn/hidden-quests` |
| 通知 | `GET /scn/notifications`, `POST .../read`, `CRUD /scn/notifications/settings`, `GET/PATCH /sys/notifications/config` |
| 看板 | `GET /scn/stats/child/{id}`, `GET /scn/stats/family`, `GET /sys/stats/overview` |
| 证据 | `GET /scn/task-instances/{id}/proofs`, `DELETE /scn/task-proofs/{id}`, `GET/POST /scn/evidence/purge(-preview)` |
| 分类 | `GET /scn/task-categories` |
| 新手 | `GET /scn/onboarding/me`, `POST /scn/onboarding/steps/{id}/complete`, `CRUD /scn/onboarding/paths(/...)` |
| 账号 | `POST /sys/accounts/me/deactivate`, `POST /sys/accounts/me/leave-family` |
| 任务 | `POST /scn/task-instances/{id}/expire` |
| 时间币 | `POST /scn/coins/reset` |
