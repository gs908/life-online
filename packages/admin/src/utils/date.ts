/**
 * 日期工具（契约 §6B）：目标日期与「已排期」判断的唯一口径。
 *
 * ⚠️ 一律用浏览器本地日期分量拼 YYYY-MM-DD，**不要用 `toISOString().slice(0,10)`** ——
 * 那是 UTC 口径，北京时间 00:00–08:00 之间会差一天，而后端一律用 `today_bj()`
 * （Asia/Shanghai）比较。家庭时区当前固定 Asia/Shanghai，与后端同源。
 */

/** 本地时区的今天，YYYY-MM-DD */
export function localToday(now: Date = new Date()): string {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** 在 YYYY-MM-DD 上加减天数（用于目标日期上限 = 今天 + 30 天） */
export function addDays(date: string, days: number): string {
  const [y, m, d] = date.split('-').map(Number);
  const base = new Date(y, m - 1, d + days);
  return localToday(base);
}

/** 生成时后台默认的「可提前天数」上限（契约 §2.1：> 今天 + 30 天 → 422） */
export const TARGET_DATE_MAX_AHEAD_DAYS = 30;

/**
 * 该实例是否为「已排期」（生成给未来某天，尚未投放）。
 * `generated_for_date` 为 NULL = 旧一次性任务路径，永远不算排期。
 */
export function isScheduled(
  task: { generated_for_date: string | null },
  today: string = localToday(),
): boolean {
  return task.generated_for_date !== null && task.generated_for_date > today;
}