/**
 * 契约 DTO 类型定义（snake_case 直传，不做 camelCase 转换）
 *
 * 唯一事实来源：docs/08-后端API契约.md。
 * 本文件必须与 docs/08 保持同步提交（docs/09 §4.5）；后端 schema 变更 → 改契约文档 → 改本文件。
 * 禁用契约中标注的"兼容旧前端"字段：creator_id / target_user_id / assignee_id /
 * user_id / task_id / privilege_id / date（新代码不读不写）。
 */

// ---- 通用 ----

export interface ApiResponse<T> {
  code: number; // 0 = 成功
  data: T;
  msg: string;
}

export interface PageResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface PageQuery {
  page?: number; // >= 1
  page_size?: number; // 1-200
}

// ---- 枚举（docs/09 §1.5：值已一致，直接沿用；角色枚举名改 GUILD_MASTER/ADVENTURER）----

export type UserRole = 'GUILD_MASTER' | 'ADVENTURER';

export type TaskType = 'DAILY' | 'CHALLENGE' | 'CHAIN' | 'TIMED' | 'COOP';

export type TaskStatus =
  | 'AVAILABLE'
  | 'IN_PROGRESS'
  | 'PENDING_REVIEW'
  | 'COMPLETED'
  | 'EXPIRED';

export type TaskCategory = 'STUDY' | 'CHORE' | 'SPORT' | 'ART' | 'LIFE' | 'OTHER';

/** 模板触发规则类型（契约 §6A，DEV-35 块 A）；weekdays 0=周一..6=周日，cron 同 APScheduler 口径 */
export type TriggerKind = 'DAILY' | 'WEEKDAYS' | 'MONTHLY' | 'CRON' | 'ONCE';

/** 模板限时模式（契约 §6A）：决定实例 expire_at 的计算方式 */
export type TimedMode = 'NONE' | 'DEADLINE' | 'DURATION';

/** 实例池策略（契约 §6A，决策 D1） */
export type PoolPolicy = 'REUSE_UNTIL_CONSUMED' | 'NEW_EACH_PERIOD';

/** 模板叙事方式（docs/15 R24）：STATIC = 用模板原文；LLM = 实例化时结合当季背景调 LLM */
export type ContentMode = 'STATIC' | 'LLM';

/** 实例叙事来源（docs/15 R25）：TEMPLATE = 模板原文；LLM = 生成成功；FALLBACK = 失败回落 */
export type ContentSource = 'TEMPLATE' | 'LLM' | 'FALLBACK';

export type ThemeId = 'DEFAULT' | 'FROSTBOUND' | 'INFERNO' | 'SYLVAN' | 'CYBERPUNK';

export type UploadPurpose = 'avatar' | 'task_proof' | 'season_banner' | 'other';

export type CoinLogType =
  | 'DAILY_RESET'
  | 'TASK_DEPOSIT'
  | 'TASK_REFUND'
  | 'ABANDON_PENALTY'
  | 'MANUAL_ADJUST';

// ---- 认证 /sys/auth（契约 §2）----

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: 'Bearer';
  access_expires_in: number; // 秒
  refresh_expires_in: number; // 秒
}

export interface WechatJscodeRequest {
  code: string;
  nickname?: string;
  avatar_url?: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

/** 开发期非微信登录（docs/08 §2）：仅后端 DEV_LOGIN_ENABLED=true 时可用，生产禁用 */
export interface DevLoginRequest {
  role?: UserRole; // 默认 ADVENTURER
  name?: string; // 仅首次创建冒险者账号时生效
}

// ---- 用户 UserRead（契约 §3，后端用户唯一形状）----

export interface UserRead {
  id: string; // 账号 ID
  family_id: string;
  role: UserRole;
  name: string;
  avatar: string;
  locale: string;
  child_id: string | null; // 冒险者扩展档案 ID（父母为 null）；任务指派用这个，不是 id
  level: number;
  xp: number;
  time_coins: number;
  daily_abandon_count: number;
  last_login_date: string | null; // YYYY-MM-DD
  current_season_id: string | null;
  privileges_unlocked: string[]; // 特权模板 ID 列表（不是等级）
  created_at: string;
  updated_at: string;
}

export interface UserUpdate {
  name?: string;
  avatar?: string;
  locale?: string;
  time_coins?: number;
  level?: number;
  xp?: number;
  current_season_id?: string | null;
}

export interface AdventurerCreate {
  name: string;
  avatar?: string; // 默认 "⚔️"
}

// ---- 家庭 /sys/families（契约 §4）----

export interface FamilyRead {
  id: string;
  name: string;
  owner_id: string;
  created_at: string;
}

export interface FamilyMembersRead {
  family: FamilyRead;
  guild_masters: UserRead[];
  adventurers: UserRead[];
}

export interface FamilyJoinRequest {
  code: string;
  nickname: string;
  avatar?: string;
  openid: string;
  unionid?: string;
}

// ---- 赛季 /scn/seasons（契约 §5）----

export interface SeasonRead {
  id: string;
  family_id: string;
  name: string;
  theme_id: ThemeId;
  narrative_context: string;
  start_date: string; // ISO 8601
  end_date: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SeasonCreate {
  name: string;
  theme_id?: ThemeId;
  narrative_context?: string;
  start_date: string;
  end_date?: string;
}

export interface SeasonUpdate {
  name?: string;
  theme_id?: ThemeId;
  narrative_context?: string;
  end_date?: string;
  is_active?: boolean;
}

export interface SeasonHistoryItem {
  season: SeasonRead;
  total_tasks: number;
  completed_tasks: number;
  /** 联调补充（docs/09 §5 D1）：后端实际返回、契约 §5 暂未成文 */
  total_xp: number;
}

// ---- 任务 /scn/task-instances（契约 §6）----

export type ProofKind = 'IMAGE' | 'VIDEO' | 'AUDIO';

/** 任务证据（DEV-33 块 E）：scn_task_proof 行读取形状，url 与 UploadRead.access_url 同口径 */
export interface TaskProofRead {
  id: string;
  task_instance_id: string;
  kind: ProofKind;
  url: string | null;
  size: number;
  content_type: string;
  created_at: string | null;
}

export interface TaskRead {
  id: string;
  family_id: string;
  season_id: string;
  /** 实例所属赛季名（契约 §6B）：模板跨赛季后，实例列表靠它分辨归属赛季 */
  season_name: string | null;
  template_id: string | null;
  creator_account_id: string | null;
  target_child_id: string | null; // 指派对象（child_id），null=可任接
  assignee_child_id: string | null; // 实际接取的孩子（child_id）
  category: TaskCategory | null;
  title: string;
  description: string;
  lore_snippet: string | null;
  xp_reward: number;
  type: TaskType;
  status: TaskStatus;
  deadline: string | null;
  expire_at: string | null;
  /** 生成器产出实例的逻辑日（契约 §6A）；一次性手工任务为 null。
   *  > 今天 = 已排期（孩子端不可见、不可接取），任务板按它加角标 */
  generated_for_date: string | null;
  /** 实例快照难度（契约 §6B）；null = 生成时模板未评星 */
  difficulty: number | null;
  required_start_time: string | null; // "HH:MM:SS"
  proof_url: string | null; // 展示用（过渡：= proofs[0].url，读取以 proofs 为准）
  proofs: TaskProofRead[]; // 全部证据（DEV-33 块 E）
  rating: number | null; // 1-5
  review_comment: string | null;
  xp_awarded: number | null;
  coin_delta: number;
  abandon_count_at_submit: number;
  started_at: string | null;
  submitted_at: string | null;
  completed_at: string | null;
  reminder_message: string | null;
  reminder_minutes_before: number;
  time_deposit: number;
  created_at: string;
  updated_at: string;
}

// ---- 任务模板 /scn/task-templates（契约 §6A，DEV-35 块 A）----

export interface TaskTriggerCreate {
  kind: TriggerKind;
  cron_expr?: string; // CRON 必填：5 段（分 时 日 月 周），day_of_week 0=周一（APScheduler 口径）
  weekdays?: number[]; // WEEKDAYS 必填：非空，0=周一..6=周日
  day_of_month?: number; // MONTHLY 必填：1-31，月末不足取当月最后一天
  generate_at?: string; // "HH:MM"，默认 00:00
  starts_on?: string; // "YYYY-MM-DD"；ONCE 必填（该日生成一次）
  ends_on?: string; // 留空 = 长期
  is_active?: boolean; // 默认 true
}

export interface TaskTriggerRead extends TaskTriggerCreate {
  id: string;
  template_id: string;
  generate_at: string; // Read 必返
  created_at: string;
  updated_at: string;
}

export interface TaskTemplateCreate {
  /** 来源赛季标签（契约 §6B）：**可选**。有激活赛季时带上、没有则省略 ——
   *  模板不绑赛季（可跨赛季复用），该字段只作溯源展示，不参与生成。 */
  season_id?: string;
  library_id?: string;
  category?: TaskCategory;
  title: string;
  description?: string;
  lore_snippet?: string;
  xp_reward?: number; // 默认 50，>=0
  type?: TaskType; // 默认 DAILY
  target_child_id?: string;
  required_start_time?: string; // "HH:MM:SS"
  reminder_message?: string;
  reminder_minutes_before?: number; // 默认 15
  difficulty?: number; // 默认 2（倍率 1.0）；只影响 XP，不影响押金
  estimated_minutes?: number; // 预计耗时（分钟），押金耗时驱动的输入；缺省走类型默认
  time_deposit?: number; // 缺省时后端按耗时/类型解析落库；显式 0 = 免押金
  is_active?: boolean;
  // ---- 块 A：时间窗（timed_mode 与字段一致性 422，前端 V1-V3 镜像拦截）----
  timed_mode?: TimedMode; // 默认 NONE；DEADLINE 需 deadline_time；DURATION 需 start_time+duration_minutes；NONE 三者皆空
  deadline_time?: string; // "HH:MM"
  start_time?: string; // "HH:MM"
  duration_minutes?: number; // 15-480，15 的倍数（后端约束 >=1）
  pool_policy?: PoolPolicy; // 默认 REUSE_UNTIL_CONSUMED
  // ---- 任务内容生成（docs/15 R24）：模板只存与赛季无关的任务实质 ----
  content_mode?: ContentMode; // 叙事方式；后端默认 LLM（新口径：生成时结合赛季背景）
  content_brief?: string | null; // 任务要点：LLM 叙事的输入；留空回落 description（R19）
  /** 缺省时后端按类型补默认规则（DAILY/TIMED→DAILY@00:00，CHALLENGE→每周一 CRON）；一次性不传 */
  triggers?: TaskTriggerCreate[];
}

/** PATCH 部分更新；triggers 传则整组替换 */
export interface TaskTemplateUpdate {
  title?: string;
  description?: string;
  lore_snippet?: string | null;
  xp_reward?: number;
  type?: TaskType;
  category?: TaskCategory | null;
  target_child_id?: string | null;
  required_start_time?: string | null;
  reminder_message?: string | null;
  reminder_minutes_before?: number;
  time_deposit?: number;
  is_active?: boolean;
  timed_mode?: TimedMode;
  deadline_time?: string | null;
  start_time?: string | null;
  duration_minutes?: number | null;
  pool_policy?: PoolPolicy;
  estimated_minutes?: number | null;
  difficulty?: number | null;
  content_mode?: ContentMode;
  content_brief?: string | null;
  triggers?: TaskTriggerCreate[];
}

export interface TaskTemplateRead {
  id: string;
  family_id: string;
  /** 来源赛季标签；null = 创建时无激活赛季（模板不绑赛季，可跨赛季复用） */
  season_id: string | null;
  /** 来源赛季名（契约 §6B）：列表弱提示用，避免前端自建赛季映射 */
  season_name: string | null;
  creator_account_id: string | null;
  library_id: string | null;
  target_child_id: string | null;
  category: TaskCategory | null;
  title: string;
  description: string;
  lore_snippet: string | null;
  xp_reward: number;
  type: TaskType;
  // CHAIN 链式（DEV-36 块 F）：第 2..N 步模板不该有手动生成入口
  //（实例由"链首投放 + 逐步解锁"产生），故列表按 chain_order 隐藏「生成」。
  chain_key: string | null;
  chain_order: number;
  chain_total: number;
  required_start_time: string | null;
  reminder_message: string | null;
  reminder_minutes_before: number;
  time_deposit: number;
  is_active: boolean;
  timed_mode: TimedMode;
  deadline_time: string | null;
  start_time: string | null;
  duration_minutes: number | null;
  pool_policy: PoolPolicy;
  estimated_minutes: number | null;
  difficulty: number | null;
  content_mode: ContentMode;
  content_brief: string | null;
  deprecated_at: string | null;
  deprecated_reason: string | null;
  triggers: TaskTriggerRead[];
  created_at: string;
  updated_at: string;
}

export interface TaskTemplateListQuery {
  season_id?: string;
  is_active?: boolean;
  type?: TaskType;
}

export interface TaskTemplateDeprecateRequest {
  reason?: string; // <=128，前端按必收设计（Miss.D §6）
}

/** regenerate 响应（契约 §6A，e278c3e）：终结范围 AVAILABLE+IN_PROGRESS，PENDING_REVIEW 保留 */
export type TaskTemplateRegenerateAction =
  | 'created' // 正常：终结旧实例并生成新实例（new_instance 非空）
  | 'kept' // 已终结旧实例；有待审核实例占用槽位，本轮不新建
  | 'exists' // 已有当日实例，未重复生成
  | 'rolled_forward' // 顺延既有实例（生成器内部路径，regenerate 后不应出现）
  | 'not_due' // 模板停用/无命中规则，未生成
  | 'skipped_expired'; // 限时任务"生成即过期"守卫，跳过当日生成

export interface TaskTemplateRegenerateResult {
  template_id: string;
  /** 被终结（置 EXPIRED、押金退还）的实例 id 列表；PENDING_REVIEW 不在其中，
   *  已排期到未来的实例自 DEV-50 审查 🟡5 起也不在其中 */
  terminalized_instance_ids: string[];
  /** 已排期到未来、本次**不受影响**的实例（后端新增）。
   *  声明为可选：旧响应没有这两个字段时前端按 0 / [] 兜底，合并先后顺序不影响可用性。 */
  scheduled_kept_instance_ids?: string[];
  scheduled_kept_count?: number;
  action: TaskTemplateRegenerateAction;
  /** 仅 action='created' 时非空 */
  new_instance: { id: string; generated_for_date: string; status: TaskStatus } | null;
}

/** 创建任务 = 建模板 + 初始实例（「一次性」发布走本接口：不传 triggers 即立即生成、不重复）。
 *
 * `ephemeral: true`（DEV-58）= **只建实例、不落模板**：用于「创建新任务」里未选模板的临时任务，
 * 创建后 `scn_task_template` 不新增行。 */
export interface TaskCreate extends TaskTemplateCreate {
  target_user_id?: string; // ⚠️ 仅兼容字段，新代码不写
  deadline?: string; // ⚠️ 仅兼容字段，新代码不写
  expire_at?: string; // ⚠️ 仅兼容字段，新代码不写
  ephemeral?: boolean;
}

/** 管理端表单实时预览押金（DEV-34 块 C；难度不影响押金，仅为表单完整性透传） */
export interface TaskDepositPreviewRequest {
  type: TaskType;
  estimated_minutes?: number; // 1–1440
  time_deposit?: number; // 显式押金，0 = 免押
  difficulty?: number; // 1–5（不影响押金，仅为表单完整性透传）
  /** 押金封顶依赖「当日配额」，而配额按星期几不同（time_config.exceptions）：
   *  生成到未来日期时用今天算会失真，故必须带上目标日期（契约 §6B） */
  for_date?: string; // YYYY-MM-DD，缺省 = 后端按当天
}

export interface TaskDepositPreviewResponse {
  time_deposit: number;
  daily_allowance: number;
  capped_by_allowance: boolean;
}

/** 选模板 → 生成（契约 §6B，`POST /scn/task-templates/{id}/generate`）
 *
 * 三条硬规则，前端必须遵守：
 * - 三个覆盖字段**未传 = 用模板当前值**（生成即快照）；
 * - **任何字段显式传 `null` 一律 422** —— 生成路径不存在"清除覆盖"的动作；
 * - 只提交用户真的改过的字段（dirty tracking），没动过的不要放进 body。 */
export interface TaskGenerateRequest {
  target_date?: string; // YYYY-MM-DD；缺省 = 家庭本地时区今天
  difficulty?: number; // 1-5
  time_deposit?: number; // >= 0
  xp_reward?: number; // >= 0
  target_child_id?: string;
}

/** 手工生成的动作枚举（契约 §6B）。未来实例不入池，重复生成同一未来日期走 exists */
export type TaskGenerateAction =
  | 'created'
  | 'exists'
  | 'rolled_forward'
  | 'kept'
  | 'skipped_expired';

export interface TaskGenerateResult {
  /** 命中/新建的实例 id；`skipped_expired` 等**无产物动作时为 null** */
  instance_id: string | null;
  action: TaskGenerateAction;
  /** ⚠️ 无产物动作（`skipped_expired`）时后端该分支 8 个字段全为 null ——
   *  类型必须如实可空，否则前端会算出 "已排期到 null" 这种句子 */
  generated_for_date: string | null;
  status: TaskStatus | null;
  /** 三个字段的生效值（快照）；无产物时为 null */
  difficulty: number | null;
  time_deposit: number | null;
  xp_reward: number | null;
  content_source: ContentSource | null;
  season_name: string | null;
  /** **只有 `created` 才真正写入覆盖值**；其余动作复用既有实例，覆盖值不会被应用。
   *  后端显式回传，前端据此把用户引导到 `PATCH /scn/task-instances/{id}`。 */
  overrides_applied: boolean;
}

/** 微调实例（契约 §6B，`PATCH /scn/task-instances/{id}`）
 *
 * 三个字段**都是快照**：未提供 = 保持不变；**显式 `null` 一律 422**（已无「跟随模板」语义）。
 * 「恢复默认」= 前端取模板当前值后提交具体数字。实例 `season_id` 不可改。 */
export interface TaskInstancePatch {
  difficulty?: number; // 1-5
  time_deposit?: number; // >= 0
  xp_reward?: number; // >= 0
}

export interface TaskListQuery extends PageQuery {
  season_id?: string;
  status?: TaskStatus;
  assignee_child_id?: string;
  template_id?: string; // DEV-35：模板详情/重新生成确认数未消费实例
  /** 管理端可选的显式筛选；孩子端由**服务端按角色强制**附加，不靠前端传参（契约 §6B） */
  generated_for_date_lte?: string; // YYYY-MM-DD
}

/** 提交证明（DEV-33 块 E 多证据）：先逐个 POST /sys/uploads(purpose=task_proof) 拿 object_key */
export interface TaskSubmitRequest {
  proof_object_keys: string[];
  /** 过渡：旧客户端单值字段，新代码不传 */
  proof_object_key?: string;
}

export interface TaskApproveRequest {
  rating: number; // 1-5 必填
  comment?: string;
}

// ---- 时间币 /scn/time-coin-logs、/scn/time-configs（契约 §8、§11）----

export interface CoinTransactionRead {
  id: string;
  family_id: string;
  child_id: string;
  season_id: string | null;
  task_instance_id: string | null;
  type: CoinLogType;
  amount: number; // 正加负减
  balance_after: number;
  note: string | null;
  created_at: string;
}

export interface CoinLogQuery extends PageQuery {
  child_id?: string;
}

export interface CoinAdjustRequest {
  child_id?: string;
  amount: number; // 必填，正加负减
  note?: string;
}

export interface TimeConfigRead {
  family_id: string;
  default_daily_allowance: number;
  /** 数组而非字典（docs/09 C1）；day_of_week: 0=周日…6=周六 */
  exceptions: Array<{ day_of_week: number; coin_amount: number }>;
}

/** PUT 整体替换（docs/09 C3）：保存时必须提交完整 exceptions 数组 */
export interface TimeConfigUpdate {
  default_daily_allowance?: number;
  exceptions?: TimeConfigRead['exceptions'];
}

// ---- 特权 /scn/privileges、/scn/privilege-uses（契约 §9、§10）----

export interface PrivilegeRead {
  id: string;
  family_id: string;
  season_id: string | null;
  level_required: number;
  title: string;
  description: string;
  icon: string;
  is_system: boolean;
  is_active: boolean;
}

export interface UserPrivilegeRead {
  id: string;
  family_id: string;
  child_id: string;
  season_id: string | null;
  privilege_template_id: string;
  privilege: PrivilegeRead;
  unlocked_at: string;
  used_count: number;
  last_used_at: string | null;
}

export interface RedemptionRead {
  id: string;
  family_id: string;
  child_id: string;
  season_id: string | null;
  privilege_template_id: string;
  privilege_title: string;
  cost: string | null;
  used_at: string; // ISO 8601（不是 Mock 里的 date 自由文本）
}

export interface RedemptionCreate {
  child_id?: string;
  privilege_template_id?: string;
  privilege_id?: string; // ⚠️ 仅兼容字段场景；新代码优先 privilege_template_id
  privilege_title?: string; // 自由文本特权
  cost?: string;
}

// ---- 上传 /sys/uploads（契约 §12）----

export interface UploadRead {
  id: string;
  family_id: string;
  uploader_account_id: string;
  storage_provider: string;
  object_key: string; // 任务提交用
  bucket: string;
  public_url: string;
  content_type: string;
  size: number;
  purpose: UploadPurpose;
  access_url: string; // 展示用
  created_at: string;
}

// ---- AI /scn/ai（契约 §13）----

export interface GenerateQuestRequest {
  topic: string; // 1-500
  child_level?: number; // 默认 1，1-200
  narrative_context?: string;
}

/** LLM 生成，data 无静态 schema 强约束，运行时自行校验关键字段 */
export interface GeneratedQuest {
  title: string;
  description: string;
  lore_snippet: string;
  xp_reward: number;
  type: TaskType;
  reminder_message?: string;
}

export interface EvaluateProofRequest {
  task_title: string;
  image_data_url: string;
  // ⚠️ 后端当前为纯文本评分（未把图送入模型），评分仅供参考
}

export interface EvaluateProofResult {
  rating: number; // 1-5
  comment: string;
}
