# 13. COOP「部分完成」状态机设计草案(DEV-36 块 F,待立项)

> 状态:**设计草案,未实现**。现有任务状态机是单人单线程
> (`AVAILABLE → IN_PROGRESS → PENDING_REVIEW → COMPLETED / EXPIRED`),
> COOP 多参与者协作需要一个表达"各参与者各自推进到哪一步"的维度。
> 本草案按 DEV-36 issue 约定先行成文,实现由独立 issue 立项后进行。

## 1. 问题

当前 COOP 实现(DEV-36 已落地部分)把协作任务当作"主接取人单线程推进":

- 主接取人(assignee_child_id / OWNER)一个人 start / submit,家长一次 approve;
- 其他参与者(MEMBER/PARENT)只登记与均摊押金,**没有自己的执行进度**;
- 任一参与者"做完了自己那份"在模型里无处安放。

"部分完成"要回答的问题:**部分参与者已交付、任务整体未交付时,系统处于什么状态、如何结算、如何推进**。

## 2. 设计原则

1. **不改动现有 `scn_task_instance.status`**——它是任务整体的进度,前端/结算/统计都依赖;参与者维度是**正交的新层**。
2. 复用 DEV-36 已落地的 `scn_task_participant`,只加列,不加表。
3. 结算规则尽量复用单人路径(押金按份额、XP 均摊、放弃惩罚)。

## 3. 参与者子状态(新增列 `participant_status`)

| 状态 | 含义 | 进入 |
|---|---|---|
| `JOINED` | 已确认加入(= 现有 `confirmed_at` 语义,可平滑迁移) | join / start |
| `WORKING` | 正在做(可选,弱状态,默认可省) | — |
| `SUBMITTED` | 本人份额已交付(上传了自己的证明) | 参与者各自 submit |
| `DONE` | 家长已确认本人份额 | approve(逐人) |
| `QUIT` | 中途退出,押金按放弃规则结算 | participant-abandon |

任务整体状态映射:

- 全员 `SUBMITTED` → 实例进入 `PENDING_REVIEW`(家长可整单 approve);
- 家长 approve 时若有人仍 `JOINED` → 允许"部分通过":
  - `SUBMITTED`/`DONE` 参与者:押金退份额、XP 均摊(交付者之间);
  - 仍 `JOINED` 的参与者:视为 `QUIT`,押金按放弃规则(60%/全额)结算,不计惩罚(需定稿确认);
- 全员 `QUIT` → 实例回 `AVAILABLE`(同现有 abandon 语义,参与者行清除)。

## 4. 新增/调整的接口(示意)

- `POST /scn/task-instances/{id}/submit` 扩展:任意参与者可为自己提交
  (`scn_task_proof` 已支持多记录;instance 的 `proof_object_key` 保留为主交付物);
- `POST /scn/task-instances/{id}/approve` 请求体可选 `child_id`:
  带 → 逐人确认(该参与者 `DONE`,押金/XP 即时结算);不带 → 整单通过(现行为);
- `POST /scn/task-instances/{id}/leave`:参与者退出(现有整体 abandon 保留给 OWNER)。

## 5. 结算矩阵(待定稿确认的默认值)

| 场景 | 押金 | XP |
|---|---|---|
| 整单通过 | 各退份额(已实现) | 均摊(已实现) |
| 部分通过 | 交付者退份额;未交付者按放弃规则 | 仅交付者间均摊 |
| 参与者退出 | 按该参与者当日放弃次数打折 | 无 |
| 过期 | 全员全额退份额(已实现) | 无 |

## 6. 待定稿的开放问题

1. 部分通过时未交付者的押金:全额退(善意)还是按放弃打折(防搭便车)?——默认建议打折,防"等队友做完自己白拿"。
2. `WORKING` 弱状态是否需要(前端是否要展示"谁开始了")?
3. 亲子协作中家长的 `SUBMITTED` 语义:家长交付是否也走 proof?
4. XP 均摊的分母:以"加入时人数"还是"最终交付人数"?(默认后者,见上表)
5. 与 DEV-35 池规则的交互:COOP 任务过期后是否可由池重投。

## 7. 实施依赖

- 迁移:`scn_task_participant` 加 `participant_status` 列(随本设计定稿出迁移);
- `docs/04` §8 的 XP 分摊已按"均摊"落地,本草案不改变该默认。
