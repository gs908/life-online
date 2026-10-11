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

export interface TaskRead {
  id: string;
  family_id: string;
  season_id: string;
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
  /** 生成器产出实例的逻辑日（契约 §6A）；一次性手工任务为 null */
  generated_for_date: string | null;
  required_start_time: string | null; // "HH:MM:SS"
  proof_url: string | null; // 展示用
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
  season_id: string;
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
  time_deposit?: number; // 默认 10
  is_active?: boolean;
  // ---- 块 A：时间窗（timed_mode 与字段一致性 422，前端 V1-V3 镜像拦截）----
  timed_mode?: TimedMode; // 默认 NONE；DEADLINE 需 deadline_time；DURATION 需 start_time+duration_minutes；NONE 三者皆空
  deadline_time?: string; // "HH:MM"
  start_time?: string; // "HH:MM"
  duration_minutes?: number; // 15-480，15 的倍数（后端约束 >=1）
  pool_policy?: PoolPolicy; // 默认 REUSE_UNTIL_CONSUMED
  estimated_minutes?: number;
  difficulty?: number; // 1-5
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
  triggers?: TaskTriggerCreate[];
}

export interface TaskTemplateRead {
  id: string;
  family_id: string;
  season_id: string;
  creator_account_id: string | null;
  library_id: string | null;
  target_child_id: string | null;
  category: TaskCategory | null;
  title: string;
  description: string;
  lore_snippet: string | null;
  xp_reward: number;
  type: TaskType;
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

/** 创建任务 = 建模板 + 初始实例（「一次性」发布走本接口：不传 triggers 即立即生成、不重复） */
export interface TaskCreate extends TaskTemplateCreate {
  target_user_id?: string; // ⚠️ 仅兼容字段，新代码不写
  deadline?: string; // ⚠️ 仅兼容字段，新代码不写
  expire_at?: string; // ⚠️ 仅兼容字段，新代码不写
}

export interface TaskListQuery extends PageQuery {
  season_id?: string;
  status?: TaskStatus;
  assignee_child_id?: string;
  template_id?: string; // DEV-35：模板详情/重新生成确认数未消费实例
}

/** 提交证明：先 POST /sys/uploads(purpose=task_proof) 拿 object_key（不是 base64） */
export interface TaskSubmitRequest {
  proof_object_key: string;
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
