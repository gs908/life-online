# 13. COOP「部分完成」状态机设计(定稿版)

> 状态:**已定稿,待实现**。原设计草案(MR #10)的 5 个开放问题已于
> 2026-10-12 由产品侧逐条裁决(裁决记录见 DEV-40 评论线程,PM-Gin 组织),
> 本文即定稿版——实现(MR 随 DEV-40)以本文为准,不再参照草案中的"待定稿"表述。
> 现有任务状态机是单人单线程
> (`AVAILABLE → IN_PROGRESS → PENDING_REVIEW → COMPLETED / EXPIRED`),
> COOP 多参与者协作需要一个表达"各参与者各自推进到哪一步"的维度。

## 1. 问题

当前 COOP 实现(DEV-36 已落地部分)把协作任务当作"主接取人单线程推进":

- 主接取人(assignee_child_id / OWNER)一个人 start / submit,家长一次 approve;
- 其他参与者(MEMBER/PARENT)只登记与均摊押金,**没有自己的执行进度**;
- 任一参与者"做完了自己那份"在模型里无处安放。

"部分完成"要回答的问题:**部分参与者已交付、任务整体未交付时,系统处于什么状态、如何结算、如何推进**。

## 2. 设计原则

1. **不改动现有 `scn_task_instance.status`**——它是任务整体的进度,前端/结算/统计都依赖;参与者维度是**正交的新层**。
2. 复用 DEV-36 已落地的 `scn_task_participant`,只加列,不加表。
3. 结算规则复用单人路径:押金按份额(`coop_service.per_participant_shares`)、XP 均摊、放弃惩罚(`coin_service.calculate_refund`)。

## 3. 参与者子状态(新增列 `participant_status`)

| 状态 | 含义 | 进入 |
|---|---|---|
| `JOINED` | 已确认加入(= 现有 `confirmed_at` 语义,迁移时回填) | join / start |
| `SUBMITTED` | 本人份额已交付(上传了自己的证明) | 参与者各自 submit |
| `DONE` | 家长已确认本人份额 | approve(逐人) |
| `QUIT` | 中途退出,押金按放弃规则结算 | leave / 部分通过判退 |

裁决 Q2:**不引入 `WORKING` 弱状态**。"谁开始了"当前无消费方(无展示位、结算不依赖);
将来确有诉求时,加一列默认 `JOINED` 的弱状态是纯增量迁移,随时可补。

任务整体状态映射:

- 全员 `SUBMITTED` → 实例进入 `PENDING_REVIEW`(家长可整单 approve);
- 全员 `QUIT` → 实例回 `AVAILABLE`(同现有 abandon 语义,参与者行清除);
- 全员 `DONE`(含逐人 approve 收尾)→ 实例聚合为 `COMPLETED`。

### 3.1 部分通过 / 逐人确认的触发前提(审查修订:定稿草案此节缺失)

草案把"approve 只发生在 PENDING_REVIEW"与"approve 时有人仍 JOINED"并列,两前提互斥
(进 PENDING_REVIEW 要求无人 JOINED,而 join 只允许 IN_PROGRESS),路径不可达。定稿明确:

- **逐人 approve(带 `child_id`)**:入口状态 = 实例 `IN_PROGRESS` **或** `PENDING_REVIEW`,
  守卫 = 该参与者为 `SUBMITTED`。孩子交一份、家长确认一份,实例停在 `IN_PROGRESS`,
  直到全员 `DONE`(聚合 COMPLETED)或家长主动收尾。
- **部分通过判退(提前收尾)**:入口状态 = 实例 `IN_PROGRESS`,守卫 = 存在至少一名
  `SUBMITTED` 参与者,且请求体带显式标志 `settle_partial: true`
  (不带标志的整单 approve 在 IN_PROGRESS 下 422 拒绝,提示家长逐人确认或等全员交齐——
  判退会真金白银打折退款,必须显式确认,不能靠漏传 `child_id` 误触)。效果:
  - `SUBMITTED`(及已 `DONE`)参与者:押金退份额,XP 按最终交付孩子数均摊(见 §5);
  - 仍 `JOINED` 的参与者:视为 `QUIT`,押金按放弃阶梯打折退(§5 裁决 Q1),**不递增当日放弃计数**;
  - 实例终结为 `COMPLETED`(部分通过即整单收尾,不再等待未交付者)。
- **整单 approve(不带 `child_id`)**:仅在 `PENDING_REVIEW`(全员已交)有效——现行为不变。
- **reject(整单驳回)**:仅 `PENDING_REVIEW` 有效(现守卫不变),实例回 `IN_PROGRESS`。
  对参与者子状态:未结算的 `SUBMITTED` → 回 `JOINED`,proof 行**保留**(审计链),
  重新提交产生新 proof 行,审核以最新一轮为准;已 `DONE` 的参与者**不受影响**
  (逐人确认即时结算后不回滚——若全员 `DONE` 则实例已聚合 COMPLETED,reject 无入口,
  不存在"已结算再驳回"的悬空态)。reject 不做任何押金/XP 动作。
- join 守卫(`coop_service.join_task` 仅 IN_PROGRESS)不变,与本节自洽:
  逐人确认与判退都发生在 IN_PROGRESS 期间,交卷未满员时其余参与者仍可加入。

## 4. 接口(定稿)

- `POST /scn/task-instances/{id}/submit` 扩展:任意参与者可为自己提交
  (`scn_task_proof` 已支持多记录;instance 的 `proof_object_key` 保留为主交付物);
  该参与者 `participant_status → SUBMITTED`。
- `POST /scn/task-instances/{id}/approve` 请求体可选 `child_id` / `settle_partial`:
  带 `child_id` → 逐人确认(该参与者 `DONE`,押金即时结算;XP 按 §6 延后到聚合终结时结算);
  不带 `child_id` + `settle_partial: true` → IN_PROGRESS 下部分通过判退收尾(守卫见 §3.1);
  都不带 → 整单通过(仅 PENDING_REVIEW,现行为)。
- `POST /scn/task-instances/{id}/leave`:参与者退出(现有整体 abandon 保留给 OWNER)。

### 裁决 Q3:家长交付同样走 proof

亲子协作中家长参与者的提交同样在 `scn_task_proof` 落行(`uploaded_by` = 家长账号),
`participant_status → SUBMITTED`。理由:证据表的意义是审计"这单任务凭什么通过",
家长那份不落证据会让部分通过的裁决失去依据;`scn_task_proof` 多记录通道已具备,无额外模型成本。
家长仍不占押金份额、不获 XP(`deposit_share` 恒 0,现状不变)。
**展示侧要求**:家长代交的证据需标注"家长代交",避免孩子侧混淆(实现期补充要求,随本 MR 的
`TaskRead.proofs` 读取侧落地——`uploaded_by` 已能区分,前端/序列化层透出该标注)。

## 5. 结算矩阵(定稿)

| 场景 | 押金 | XP |
|---|---|---|
| 整单通过 | 各退份额(已实现) | 按**最终交付的孩子参与者数**均摊(⚠️ 是对现行为的**修改**,见下) |
| 部分通过判退 | 交付者退份额;未交付者 `calculate_refund(deposit_share, 其当日放弃次数)` 打折退,**不递增**当日放弃计数 | 仅交付者间均摊(分母=最终交付的**孩子**参与者数,裁决 Q4) |
| 参与者退出(leave) | 按该参与者当日放弃次数打折(`calculate_refund`),**递增**其当日放弃计数(主动放弃行为) | 无 |
| 过期 | 全员全额退份额(已实现;与单人 D4 的口径差异见下注) | 无 |

**Q4 分母细化(审查修订)**:分母 = 最终交付的**孩子**参与者数;家长参与者(PARENT)即使
`SUBMITTED` 也**不入分母**(家长无 XP 账户,计入会让"1 家长 + 1 孩子"的家庭对半分掉孩子应得
的全部 XP)。且此分母是**对现行为的修改而非确认**:现网 `approve_task` 的分母是
`len(wallet_participants)`(`task_service.py:432`——全部已确认孩子参与者,含从未提交者;
单人单线程下整单提交即全员视同交付,两者无差别,COOP 部分完成后有差别)。实现按本定稿改为
交付孩子数,并在 §8 测试中覆盖"从未提交者不分 XP"。

**过期口径注(审查修订)**:COOP 过期全额退份额为块 F 已过审口径;与单人路径 D4
"IN_PROGRESS 退 50%/扣罚 50%"的差异为**已知待议项**(`task_service.py:673` 代码注释同文),
实现不得单方面统一两口径。若产品后续裁决"COOP 过期也退半",按变更请求记录并重估本矩阵。

### 裁决 Q1:部分通过时未交付者的押金

**按放弃规则打折退,不递增当日放弃计数。**

- 退款额复用 `coin_service.calculate_refund`——孩子和家长不需要学第二套退款规则,规则唯一;
- 不递增 `daily_abandon_count`:该计数语义是"主动放弃行为",被部分通过"判退"的孩子没有
  发起放弃,递增会造成一次行为双重惩罚;
- 否决善意方案(全额退):留下"等队友做完自己白拿全额退款"的搭便车口子。

**体验配套(实现期补充要求)**:退款通知/流水要让孩子能看懂"为什么退少了"——
退款通知与 `coin_service.record_transaction` 的 `note` 需写明
"部分通过判退 + 当日已放弃 N 次,按 X% 退还",否则 60% 折扣会变成客诉源。
两点审查补充:**① 首次判退 = 全额退**(阶梯仅当日放弃 ≥3 次才打 6 折),note 模板须兼容
100% 场景——全额时换中性文案(如"部分通过,押金份额已全额退还"),避免"按 100% 退还"
读起来像处罚;**② 判退 vs 主动放弃在流水 note 上以前缀区分**
(判退前缀 `[部分通过判退]`、主动放弃前缀 `[放弃]`,共用现有 `TASK_REFUND`/`ABANDON_PENALTY`
类型不新增枚举),保证审计侧可区分两条路径。

### 裁决 Q4:XP 均摊分母 = 最终交付的孩子参与者数

按"加入时人数"均摊意味着队友掉线时交付者被连坐少拿 XP,惩罚错人;按交付人数分,
掉线者拿不到 XP 已是全部代价(押金侧由 Q1 处理)。边界:仅 OWNER 一人交付 → OWNER 得全额 XP,可接受。
**注意这是对现行为分母(`len(wallet_participants)`)的修改**(见 §5),docs/04 §8"孩子参与者间
均摊"的总口径不变,分母定义随本定稿细化。

## 6. 聚合与通知

- **结算时序(审查修订:与 Q4 分母配套)**:**押金逐人即时结算**(退份额无歧义,逐人 approve
  时即退);**XP 延后到实例聚合终结时一次性结算**——分母是"最终交付的孩子数",逐人 approve
  时点无法预知(后来者还会交,分母会变),提前落账必然算错比例需 clawback。聚合终结的三种
  形态(整单通过 / 部分通过判退收尾 / 全员 `DONE`)共用同一套 XP 结算代码,分母、份额一次算清。
- **聚合**:逐人 approve 使参与者各自 `DONE`;全员 `DONE` → 实例 `COMPLETED`(此时执行上述
  XP 一次性结算,再翻实例状态)。
- **通知**(新增 `NotificationType`):
  - `COOP_PARTIAL_SUBMITTED`:任一参与者 `SUBMITTED` 且尚有未交付者 →
    通知主接取人(OWNER)与未交付参与者;
  - `COOP_PARTIAL_SETTLED`:部分通过判退结算 → 通知被判退者(内容含 §5 Q1 的退款解释)。

## 7. 裁决 Q5:过期后重投 = 新实例,不复活旧实例

EXPIRED 实例 = 该周期终结、不顺延(与 D1/D2 已锁定的消费语义一致),下个触发周期由
生成器出**新实例**(新参与者重新加入、重新均摊)。全员 QUIT → 回 AVAILABLE 顺延复用。
旧实例上已清算的押金流水与参与者记录保持不可变——复活会破坏审计链。

## 8. 实施清单(随 DEV-40 实现 MR)

- 迁移:`scn_task_participant` 加 `participant_status`(String, default `JOINED`,
  存量已确认行回填 `JOINED`);迁移 `down_revision` 接 develop 上 DEV-41 合入后的链头。
- `app/models/enums.py`:`TaskParticipantStatus`(JOINED/SUBMITTED/DONE/QUIT)、
  两个新 `NotificationType`。
- `coop_service`:参与者子状态迁移与守卫;部分通过结算(§5 矩阵);聚合完成判定。
- `task_service`:`submit_task` 扩展任意参与者提交(含家长,proof 落 `uploaded_by`);
  `approve_task` 支持逐人 `child_id` 与 `settle_partial` 判退收尾(守卫见 §3.1);
  `approve_task` XP 分母由 `len(wallet_participants)` 改为交付孩子数(§5,行为修改);
  新增 `leave_task`(OWNER 走现有整体 abandon)。reject 按 §3.1 定义子状态回退(JOINED)、proof 保留。
- 通知/流水:判退 note 前缀 `[部分通过判退]`、放弃前缀 `[放弃]`(§5 Q1),全额退场景中性文案。
- 结算与 join/整单 settle 同一把实例行锁(`get_task_for_update`,MR #10 审查修复既定)。
- 文档同步:`docs/06`(状态机:参与者子状态层与聚合规则)、`docs/05`(COOP 能力矩阵补部分完成)、
  `docs/04` §4.1(部分通过结算口径)。
- 测试 `test_coop_partial_completion.py`:子状态迁移全路径;部分结算(Q1 阶梯退款不计数 /
  Q4 交付孩子数分母——含"从未提交者不分 XP"与"家长 SUBMITTED 不入分母");全员 DONE 聚合 COMPLETED
  (XP 聚合终结时一次结算);家长 proof 提交;leave 语义(递增计数 vs 判退不递增);§3.1 守卫
  (IN_PROGRESS 无 `settle_partial` 的整单 approve 422;无 SUBMITTED 者时判退拒绝);reject 路径
  (SUBMITTED 回 JOINED、proof 保留、DONE 不受影响);过期全退不复活。

> 改判机制:若家长侧对任一条有异议,可在实现 MR 合入前改判——改判按变更请求记录并
> 重新评估结算矩阵影响。
