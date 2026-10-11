/**
 * 任务模板纯函数工具（DEV-35 块 A，Miss.D 设计规范 §2/§4/§5）
 *
 * - 触发规则/时间窗的「人话摘要」由前端从结构化字段拼装（Miss.D 规范确认点 2，后端只给结构化字段）
 * - 校验 V1-V8 镜像后端 422 语义（契约 §6A），提交前拦截；422 仍做兜底
 * - cron 口径：APScheduler 语义，day_of_week 0=周一（docs/08 §6A）
 */
import type { TFunction } from 'i18next';
import type {
  TaskTemplateRead,
  TaskTriggerCreate,
  TimedMode,
  TriggerKind,
} from '../services/api';

/** 管理端四类任务（Miss.D §2；CHAIN/COOP 本轮不做，避免死选项） */
export type TaskTemplateCategoryIntent = 'once' | 'daily' | 'challenge' | 'timed';

/** 触发规则编辑器的 kind 分段（Miss.D §3.1：每天/指定星期/每月/Cron） */
export type TriggerDraftKind = 'DAILY' | 'WEEKDAYS' | 'MONTHLY' | 'CRON';

export interface TriggerDraft {
  /** ONCE 仅编辑预填时出现（模板路径允许 ONCE 规则），分段控件此时追加渲染一次性段 */
  kind: TriggerDraftKind | 'ONCE';
  cron_expr: string;
  weekdays: number[]; // 0=周一..6=周日
  day_of_month: number;
  generate_at: string; // "HH:MM"
  starts_on: string; // "YYYY-MM-DD"，空 = 不限
  ends_on: string; // "YYYY-MM-DD"，空 = 长期
}

export const makeTriggerDraft = (patch: Partial<TriggerDraft> = {}): TriggerDraft => ({
  kind: 'DAILY',
  cron_expr: '',
  weekdays: [],
  day_of_month: 1,
  generate_at: '08:00',
  starts_on: '',
  ends_on: '',
  ...patch,
});

/**
 * 列表卡片徽标/筛选的类别推导（Miss.D 补遗 1 §1：模板列表不存在「一次性」类——
 * type 枚举无该值、一次性走 POST /scn/task-instances，无周期规则模板按 type 归入日常）。
 * 注意：本函数只用于列表/详情展示与编辑预填；AddTaskModal 新建的四类选择器不受影响。
 */
export const categoryOf = (
  template: TaskTemplateRead,
): Exclude<TaskTemplateCategoryIntent, 'once'> => {
  if (template.type === 'TIMED') return 'timed';
  if (template.type === 'CHALLENGE') return 'challenge';
  return 'daily';
};

/** 触发 weekdays(0=周一..6=周日) → i18n days.*（0=周日）的键序换算 */
const weekdayLabelKey = (weekday: number): string => `days.${(weekday + 1) % 7}`;

const formatTime = (time: string | null | undefined): string =>
  (time ?? '').slice(0, 5); // "HH:MM:SS" → "HH:MM"

/** 单条触发规则人话摘要，如「每天 08:00」「每周一、三 09:00」「每月 15 日 08:00」「Cron 0 8 * * 1-5」 */
export const describeTrigger = (trigger: TaskTriggerCreate, t: TFunction): string => {
  const at = t('taskTemplate.triggerAt', { time: formatTime(trigger.generate_at) });
  switch (trigger.kind) {
    case 'DAILY':
      return t('taskTemplate.triggerDailyShort', { at });
    case 'WEEKDAYS': {
      const names = (trigger.weekdays ?? [])
        .slice()
        .sort((a, b) => a - b)
        .map(w => t(weekdayLabelKey(w)));
      return t('taskTemplate.triggerWeekdaysShort', {
        days: names.join(t('taskTemplate.listJoiner')),
        at,
      });
    }
    case 'MONTHLY':
      return t('taskTemplate.triggerMonthlyShort', { day: trigger.day_of_month ?? 1, at });
    case 'CRON':
      return t('taskTemplate.triggerCronShort', { expr: trigger.cron_expr ?? '' });
    case 'ONCE':
      return t('taskTemplate.triggerOnceShort', { date: trigger.starts_on ?? '' });
    default:
      return trigger.kind;
  }
};

/** 生效区间摘要，「长期生效」/「2026-10-01 ~ 2026-12-31」/「2026-10-01 起」 */
export const describeRange = (trigger: TaskTriggerCreate, t: TFunction): string => {
  const start = trigger.starts_on ?? '';
  const end = trigger.ends_on ?? '';
  if (start && end) return t('taskTemplate.rangeBoth', { start, end });
  if (start) return t('taskTemplate.rangeFrom', { start });
  if (end) return t('taskTemplate.rangeUntil', { end });
  return t('taskTemplate.rangeForever');
};

/** 时间窗摘要，「无时间窗」/「当日 20:00 截止」/「16:30 起 45 分钟」 */
export const describeTimeWindow = (template: TaskTemplateRead, t: TFunction): string => {
  if (template.timed_mode === 'DEADLINE') {
    return t('taskTemplate.windowDeadlineShort', { time: formatTime(template.deadline_time) });
  }
  if (template.timed_mode === 'DURATION') {
    return t('taskTemplate.windowDurationShort', {
      start: formatTime(template.start_time),
      minutes: template.duration_minutes ?? 0,
    });
  }
  return t('taskTemplate.windowNone');
};

// ---- 校验（V1-V8，Miss.D §5）----

/** 5 段 cron 的前端粗校验（双保险；后端用 APScheduler CronTrigger 精校验） */
export const isValidCronExpr = (expr: string): boolean => {
  const fields = expr.trim().split(/\s+/);
  if (fields.length !== 5) return false;
  return fields.every(field => /^[0-9*,/\-]+$/.test(field) && field.length > 0);
};

const isValidHHMM = (value: string): boolean => /^([01]\d|2[0-3]):[0-5]\d$/.test(value);

export interface TemplateFormErrors {
  title?: boolean; // V8
  xp?: boolean; // V8
  timed?: 'V1' | 'V2' | null; // deadline_time 缺失 / start_time+duration 缺失或越界
  range?: boolean; // V7
  /** 按规则下标给 V4/V5/V6 错误 */
  triggers: Record<number, 'V4' | 'V5' | 'V6' | undefined>;
}

/** minutes 步进/范围（Miss.D §3.2：15 步进，15-480） */
export const DURATION_STEP = 15;
export const DURATION_MIN = 15;
export const DURATION_MAX = 480;

export const validateTriggerDraft = (draft: TriggerDraft): 'V4' | 'V5' | 'V6' | undefined => {
  if (draft.kind === 'WEEKDAYS' && draft.weekdays.length === 0) return 'V4';
  if (draft.kind === 'MONTHLY' && (draft.day_of_month < 1 || draft.day_of_month > 31)) return 'V5';
  if (draft.kind === 'CRON' && !isValidCronExpr(draft.cron_expr)) return 'V6';
  return undefined;
};

/** 表单整体校验；返回 null = 通过 */
export const validateTemplateForm = (form: {
  title: string;
  xp: number;
  timed_mode: TimedMode;
  deadline_time: string;
  start_time: string;
  duration_minutes: number;
  triggers: TriggerDraft[];
}): TemplateFormErrors | null => {
  const errors: TemplateFormErrors = { triggers: {} };
  if (!form.title.trim()) errors.title = true; // V8
  if (!Number.isFinite(form.xp) || form.xp < 0) errors.xp = true; // V8

  if (form.timed_mode === 'DEADLINE' && !isValidHHMM(form.deadline_time)) {
    errors.timed = 'V1'; // V1
  }
  if (
    form.timed_mode === 'DURATION' &&
    (!isValidHHMM(form.start_time) ||
      form.duration_minutes < DURATION_MIN ||
      form.duration_minutes > DURATION_MAX ||
      form.duration_minutes % DURATION_STEP !== 0)
  ) {
    errors.timed = 'V2'; // V2
  }

  form.triggers.forEach((draft, index) => {
    const triggerError = validateTriggerDraft(draft);
    if (triggerError) errors.triggers[index] = triggerError;
    if (draft.starts_on && draft.ends_on && draft.ends_on < draft.starts_on) errors.range = true; // V7
  });

  const hasError =
    errors.title || errors.xp || errors.timed || errors.range || Object.keys(errors.triggers).length > 0;
  return hasError ? errors : null;
};

/** 编辑预填：TaskTriggerRead → TriggerDraft */
export const triggerToDraft = (trigger: TaskTriggerCreate): TriggerDraft =>
  makeTriggerDraft({
    kind: trigger.kind,
    cron_expr: trigger.cron_expr ?? '',
    weekdays: [...(trigger.weekdays ?? [])],
    day_of_month: trigger.day_of_month ?? 1,
    generate_at: formatTime(trigger.generate_at) || '00:00',
    starts_on: trigger.starts_on ?? '',
    ends_on: trigger.ends_on ?? '',
  });

/** TriggerDraft → TaskTriggerCreate payload（按 kind 只带相关字段） */
export const draftToTriggerPayload = (draft: TriggerDraft): TaskTriggerCreate => {
  const base: TaskTriggerCreate = {
    kind: draft.kind,
    generate_at: draft.generate_at,
  };
  if (draft.starts_on) base.starts_on = draft.starts_on;
  if (draft.ends_on) base.ends_on = draft.ends_on;
  if (draft.kind === 'WEEKDAYS') base.weekdays = [...draft.weekdays].sort((a, b) => a - b);
  if (draft.kind === 'MONTHLY') base.day_of_month = draft.day_of_month;
  if (draft.kind === 'CRON') base.cron_expr = draft.cron_expr.trim();
  return base;
};

/**
 * W1 软警告（不阻断）：DEADLINE ≤ 任一规则 generate_at 时提示可能生成即过期
 */
export const deadlineEarlierThanGenerate = (form: {
  timed_mode: TimedMode;
  deadline_time: string;
  triggers: TriggerDraft[];
}): boolean => {
  if (form.timed_mode !== 'DEADLINE' || !isValidHHMM(form.deadline_time)) return false;
  return form.triggers.some(
    draft => isValidHHMM(draft.generate_at) && draft.generate_at <= form.deadline_time,
  );
};
