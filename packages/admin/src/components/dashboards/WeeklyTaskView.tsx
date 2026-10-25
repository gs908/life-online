import React, { useState, useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { TaskRead } from '../../services/api';
import type { SeasonTheme } from '../../types';
import { ChevronLeft, ChevronRight, Calendar } from 'lucide-react';
import { localToday, dateOnlyToMMDD, timestampToMMDD } from '../../utils/date';
import TaskDetailModal from '../modals/TaskDetailModal';

/** 多孩子模式下的孩子选项（家长端）：头像 + 名字用于区分任务归属 */
export interface WeeklyViewChild {
  childId: string;
  name: string;
  avatar: string;
}

function useIsLg() {
  const [isLg, setIsLg] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia('(min-width: 1024px)').matches : true
  );
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 1024px)');
    const handler = (e: MediaQueryListEvent) => setIsLg(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);
  return isLg;
}

interface WeeklyTaskViewProps {
  tasks: TaskRead[];
  currentTheme: SeasonTheme;
  /** 孩子端操作回调：家长端只读视图不传，此时不渲染接取/提交/放弃按钮 */
  onAcceptAttempt?: (id: string) => void;
  onSubmit?: (id: string) => void;
  onAbandonCurrent?: (id: string) => void;
  /** 家长端多孩子模式：孩子选项列表。传了则启用头像区分与筛选栏（孩子端不传，行为不变） */
  childOptions?: WeeklyViewChild[];
  /** 当前选中的孩子 ID；null = 显示全部 */
  selectedChildId?: string | null;
  onChildSelected?: (childId: string | null) => void;
  /**
   * 左右翻页的时间边界（赛季起止，YYYY-MM-DD 或 ISO 8601）。
   * 左箭头不早于 seasonStart 所在周，右箭头不晚于 seasonEnd 所在周；
   * 缺省（无激活赛季）= 该方向不设限，可自由翻页。跨赛季暂不支持。
   */
  seasonStart?: string | null;
  seasonEnd?: string | null;
  /**
   * 标题/翻页控件的配色上下文。
   * - 'themed'（默认，孩子端）：跟随赛季主题色，背景为深色主题底；
   * - 'light'（家长端）：白底卡片，用固定深色文字，避免浅色主题标题在白卡上不可见。
   */
  variant?: 'themed' | 'light';
}

type DayCell = {
  date: string; // YYYY-MM-DD
  label: string; // e.g. "周一"
  isToday: boolean;
  tasks: TaskRead[];
};

function getTimeSlot(task: TaskRead): string {
  if (task.type === 'TIMED' && task.required_start_time) {
    const hour = parseInt(task.required_start_time.split(':')[0], 10);
    if (hour < 12) return 'morning';
    if (hour < 18) return 'afternoon';
    return 'evening';
  }
  if (task.deadline) {
    const hour = new Date(task.deadline).getHours();
    if (hour < 12) return 'morning';
    if (hour < 18) return 'afternoon';
    return 'evening';
  }
  return 'anytime';
}

function getTypeBadgeColor(type: TaskRead['type']) {
  switch (type) {
    case 'CHALLENGE': return 'bg-red-100 text-red-700 border-red-200';
    case 'DAILY': return 'bg-blue-100 text-blue-700 border-blue-200';
    case 'TIMED': return 'bg-orange-100 text-orange-700 border-orange-200';
    case 'COOP': return 'bg-purple-100 text-purple-700 border-purple-200';
    case 'CHAIN': return 'bg-amber-100 text-amber-700 border-amber-200';
    default: return 'bg-slate-100 text-slate-700 border-slate-200';
  }
}

/** 驳回展示态（DEV-57 路线 2）：与任务板 QuestCard 同口径 —— 周视图同属孩子端，驳回需可见 */
function isRejectedTask(task: TaskRead): boolean {
  return task.status === 'IN_PROGRESS' && !!task.rejected;
}

/**
 * 已完成任务的完成日 MM-DD（DEV-65 块 B）：优先实际完成时间，回退逻辑日。
 * 同一模板的每日实例标题完全相同，带上完成日才能在周视图里区分。
 * 格式化口径统一在 utils/date（完成时间是时间戳，必须按本地分量取日）。
 */
function completedDateMMDD(task: TaskRead): string | null {
  return timestampToMMDD(task.completed_at) ?? dateOnlyToMMDD(task.generated_for_date);
}

function getStatusDot(task: TaskRead) {
  if (isRejectedTask(task)) return 'bg-red-500';
  switch (task.status) {
    case 'AVAILABLE': return 'bg-green-400';
    case 'IN_PROGRESS': return 'bg-blue-400 animate-pulse';
    case 'PENDING_REVIEW': return 'bg-yellow-400';
    case 'COMPLETED': return 'bg-gray-400';
    case 'EXPIRED': return 'bg-red-300';
    default: return 'bg-slate-300';
  }
}

/** 状态图例顺序（与状态点颜色一一对应），按「图例只列出当前视图实际出现过的状态」筛选 */
const STATUS_LEGEND: Array<{ key: string; dot: string }> = [
  { key: 'AVAILABLE', dot: 'bg-green-400' },
  { key: 'IN_PROGRESS', dot: 'bg-blue-400 animate-pulse' },
  { key: 'PENDING_REVIEW', dot: 'bg-yellow-400' },
  { key: 'COMPLETED', dot: 'bg-gray-400' },
  { key: 'EXPIRED', dot: 'bg-red-300' },
];

/** Date → YYYY-MM-DD（本地时区口径，与 utils/date 的 localToday 一致） */
function formatDay(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** 该日所在周的周一（YYYY-MM-DD）；入参接受 YYYY-MM-DD 或 ISO 8601，作为赛季起止的翻页边界 */
function mondayOf(day: string): string {
  const [y, m, d] = day.slice(0, 10).split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() - ((dt.getDay() + 6) % 7));
  return formatDay(dt);
}

const WeeklyTaskView: React.FC<WeeklyTaskViewProps> = ({
  tasks,
  currentTheme,
  onAcceptAttempt,
  onSubmit,
  onAbandonCurrent,
  childOptions,
  selectedChildId,
  onChildSelected,
  variant = 'themed',
  seasonStart,
  seasonEnd,
}) => {
  const { t, i18n } = useTranslation();
  const today = localToday();
  const isLg = useIsLg();

  const [weekOffset, setWeekOffset] = useState(0);
  /** 点击任务 chip / 移动端卡片后展示的只读详情（孩子端/家长端共用） */
  const [selectedTask, setSelectedTask] = useState<TaskRead | null>(null);

  // 家长端白底卡片用固定深色文字；孩子端跟随赛季主题色（深色主题底）
  const isLight = variant === 'light';
  const headerTextClass = isLight ? 'text-slate-800' : currentTheme.textColor;
  const navIconClass = isLight ? 'text-slate-600' : currentTheme.textColor;
  const navBtnClass = isLight ? 'hover:bg-slate-100' : 'hover:bg-white/20';
  const currentWeekBtnClass = isLight
    ? weekOffset !== 0
      ? 'bg-slate-200 hover:bg-slate-300 text-slate-700'
      : 'opacity-50 cursor-default'
    : weekOffset !== 0
      ? 'bg-white/20 hover:bg-white/30 text-white'
      : 'opacity-50 cursor-default';

  // 多孩子模式：家长端传入 childOptions 列表 + onChildSelected 时启用
  const multiChild = Boolean(childOptions && childOptions.length > 0 && onChildSelected);
  const activeChildId = multiChild ? (selectedChildId ?? null) : null;

  const childMap = useMemo(() => {
    const map: Record<string, WeeklyViewChild> = {};
    for (const c of childOptions ?? []) map[c.childId] = c;
    return map;
  }, [childOptions]);

  /** 任务归属的孩子（接取者优先，其次指派对象）；无归属或非多孩子模式返回 null */
  const childOf = (task: TaskRead): WeeklyViewChild | null => {
    if (!multiChild) return null;
    const id = task.assignee_child_id ?? task.target_child_id;
    return id ? (childMap[id] ?? null) : null;
  };

  // 多孩子模式下按 selectedChildId 在组件内过滤；孩子端（非多孩子）原样展示。
  // 过滤口径与头像归属口径**保持一致**（assignee 优先、回退 target），
  // 否则会出现「按 B 筛选，却带出一条挂 A 头像的任务」。
  const visibleTasks = useMemo(() => {
    if (!multiChild || activeChildId === null) return tasks;
    return tasks.filter(
      (task) => (task.assignee_child_id ?? task.target_child_id) === activeChildId,
    );
  }, [tasks, multiChild, activeChildId]);

  // Build week start (Monday) based on offset
  const weekStart = useMemo(() => {
    const todayDate = new Date();
    const dayOfWeek = todayDate.getDay(); // 0=Sun, 1=Mon
    // Adjust: get Monday of current week
    const monday = new Date(todayDate);
    monday.setDate(todayDate.getDate() - ((dayOfWeek + 6) % 7) + weekOffset * 7);
    return monday;
  }, [weekOffset]);

  // 周范围（含月份）：跨月周只看日头数字看不出月份，标题区必须给出完整区间
  const weekRangeLabel = useMemo(() => {
    const end = new Date(weekStart);
    end.setDate(weekStart.getDate() + 6);
    const fmt = (d: Date) => d.toLocaleDateString(i18n.language, { month: 'long', day: 'numeric' });
    return t('weeklyView.weekRange', { start: fmt(weekStart), end: fmt(end) });
  }, [weekStart, i18n.language, t]);

  const days: DayCell[] = useMemo(() => {
    const result: DayCell[] = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(weekStart);
      d.setDate(weekStart.getDate() + i);
      const dateStr = formatDay(d);
      const dayLabels = [t('days.0'), t('days.1'), t('days.2'), t('days.3'), t('days.4'), t('days.5'), t('days.6')];
      result.push({
        date: dateStr,
        label: dayLabels[d.getDay()],
        isToday: dateStr === today,
        tasks: [], // populated below
      });
    }
    return result;
  }, [weekStart, today, t]);

  // Group tasks by their effective date.
  // 优先 generated_for_date（生成器产出的逻辑日）；为 null（手工一次性任务、链式实例）时，
  // 已终结任务（COMPLETED/EXPIRED）回退到 completed_at 的归属日（实际完成日），
  // 未终结任务回退到 created_at（实际投放日），最终回退 today。
  // 否则所有 null 日期的历史任务会被 ?? today 堆到「今天」列。
  const tasksByDate = useMemo(() => {
    const toDate = (ts: string | null | undefined): string | null =>
      ts ? ts.slice(0, 10) : null; // ISO 8601 → YYYY-MM-DD
    const map: Record<string, TaskRead[]> = {};
    for (const task of visibleTasks) {
      let date = task.generated_for_date;
      if (!date) {
        if (task.status === 'COMPLETED' || task.status === 'EXPIRED') {
          date = toDate(task.completed_at);
        }
        if (!date) date = toDate(task.created_at);
      }
      if (!date) date = today;
      if (!map[date]) map[date] = [];
      map[date].push(task);
    }
    // Sort each day's tasks by time slot then status priority
    const statusOrder: Record<string, number> = {
      IN_PROGRESS: 0,
      AVAILABLE: 1,
      PENDING_REVIEW: 2,
      COMPLETED: 3,
      EXPIRED: 4,
    };
    for (const date of Object.keys(map)) {
      map[date].sort((a, b) => {
        const slotDiff = getTimeSlot(a).localeCompare(getTimeSlot(b));
        if (slotDiff !== 0) return slotDiff;
        return (statusOrder[a.status] ?? 9) - (statusOrder[b.status] ?? 9);
      });
    }
    return map;
  }, [visibleTasks, today]);

  // Assign tasks to day cells
  for (const day of days) {
    day.tasks = tasksByDate[day.date] ?? [];
  }

  const prevWeek = () => setWeekOffset(prev => prev - 1);
  const nextWeek = () => setWeekOffset(prev => prev + 1);
  const goToCurrentWeek = () => setWeekOffset(0);

  // 左右翻页边界：不早于赛季开始所在周、不晚于赛季结束所在周。
  // 历史/未来两方向都可一直翻，只是到赛季边界为止（跨赛季暂不支持）；
  // 边界缺省（无激活赛季 / 赛季无结束日）则该方向不设限。
  const weekStartStr = formatDay(weekStart);
  const seasonStartWeek = useMemo(() => (seasonStart ? mondayOf(seasonStart) : null), [seasonStart]);
  const seasonEndWeek = useMemo(() => (seasonEnd ? mondayOf(seasonEnd) : null), [seasonEnd]);
  const canGoPrev = seasonStartWeek === null || weekStartStr > seasonStartWeek;
  const canGoNext = seasonEndWeek === null || weekStartStr < seasonEndWeek;

  // 图例只列出当前视图实际出现过的状态，避免只读视图里出现永远不出现的死条目
  const presentStatuses = useMemo(
    () => new Set(visibleTasks.map((task) => task.status)),
    [visibleTasks],
  );

  /** 多孩子模式下任务归属的小头像（16px），单孩子模式返回 null */
  const renderChildBadge = (task: TaskRead) => {
    const child = childOf(task);
    if (!child) return null;
    return (
      <span className="shrink-0 text-[10px] leading-none" title={child.name}>
        {child.avatar}
      </span>
    );
  };

  return (
    <div className="space-y-4">
      {/* Week Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h3 className={`text-lg font-bold flex items-center gap-2 ${headerTextClass} drop-shadow-sm`}>
            <Calendar size={18} /> {t('weeklyView.title')}
          </h3>
          <p className={`text-xs mt-0.5 ${headerTextClass} opacity-80`}>{weekRangeLabel}</p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={prevWeek}
            disabled={!canGoPrev}
            className={`p-1.5 rounded-lg ${navBtnClass} disabled:opacity-30 disabled:cursor-not-allowed transition-colors`}
            aria-label={t('weeklyView.prevWeek')}
          >
            <ChevronLeft size={18} className={navIconClass} />
          </button>
          <button
            onClick={goToCurrentWeek}
            className={`px-2 py-1 text-xs font-bold rounded-lg transition-colors ${currentWeekBtnClass}`}
          >
            {weekOffset === 0 ? t('weeklyView.currentWeek') : t('weeklyView.backToCurrentWeek')}
          </button>
          <button
            onClick={nextWeek}
            disabled={!canGoNext}
            className={`p-1.5 rounded-lg ${navBtnClass} disabled:opacity-30 disabled:cursor-not-allowed transition-colors`}
            aria-label={t('weeklyView.nextWeek')}
          >
            <ChevronRight size={18} className={navIconClass} />
          </button>
        </div>
      </div>

      {/* 多孩子筛选栏（家长端）：全部 + 每个孩子头像，点击筛选，再次点击取消 */}
      {multiChild && (
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t('weeklyView.filterByChild')}>
          <button
            onClick={() => onChildSelected?.(null)}
            aria-pressed={activeChildId === null}
            className={`px-3 py-1.5 rounded-full text-xs font-bold transition-all ${
              activeChildId === null
                ? 'bg-slate-800 text-white shadow'
                : 'bg-white/70 text-slate-600 hover:bg-white'
            }`}
          >
            {t('weeklyView.allChildren')}
          </button>
          {childOptions!.map((c) => {
            const selected = activeChildId === c.childId;
            return (
              <button
                key={c.childId}
                onClick={() => onChildSelected?.(selected ? null : c.childId)}
                aria-pressed={selected}
                title={c.name}
                className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-bold transition-all ${
                  selected
                    ? 'bg-slate-800 text-white shadow ring-2 ring-sky-400 scale-105'
                    : 'bg-white/70 text-slate-600 hover:bg-white'
                }`}
              >
                <span className="text-sm leading-none">{c.avatar}</span>
                <span>{c.name}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Week Grid - desktop only: 7 columns, conditional render */}
      {isLg ? (
      <div className="bg-white/95 backdrop-blur-sm rounded-2xl shadow-lg border-2 border-slate-200 overflow-hidden">
        {/* Day Headers */}
        <div className="grid grid-cols-7 border-b-2 border-slate-200">
          {days.map((day) => (
            <div
              key={day.date}
              className={`py-2 text-center border-r last:border-r-0 ${
                day.isToday
                  ? `${currentTheme.primaryColor} text-white font-bold`
                  : 'bg-slate-50 text-slate-600 font-medium'
              }`}
            >
              <div className="text-xs opacity-75">{day.label}</div>
              <div className="text-sm">{day.date.slice(5).replace('-', '/')}</div>
            </div>
          ))}
        </div>

        {/* Task Rows per Day */}
        <div className="grid grid-cols-7 min-h-[200px]">
          {days.map((day) => (
            <div
              key={day.date}
              className={`border-r last:border-r-0 border-b last:border-b-0 p-1.5 min-h-[120px] ${
                day.isToday ? `${currentTheme.primaryColor}/10` : 'bg-white'
              }`}
            >
              {day.tasks.length === 0 ? (
                <div className="h-full flex items-center justify-center opacity-30">
                  <Calendar size={20} />
                </div>
              ) : (
                <div className="space-y-1">
                  {day.tasks.map((task) => (
                    <div
                      key={task.id}
                      role="button"
                      tabIndex={0}
                      onClick={() => setSelectedTask(task)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setSelectedTask(task);
                        }
                      }}
                      aria-label={t('taskDetail.openLabel', { title: task.title })}
                      className={`rounded-lg border-l-2 p-1.5 text-xs cursor-pointer transition-all hover:scale-[1.02] ${getTypeBadgeColor(task.type)}`}
                      title={`${task.title} (${task.type})`}
                    >
                      <div className="flex items-center gap-1">
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${getStatusDot(task)}`} />
                        {renderChildBadge(task)}
                        <span className="font-bold truncate flex-1 leading-tight">{task.title}</span>
                        {task.status === 'COMPLETED' && completedDateMMDD(task) && (
                          <span className="shrink-0 text-[9px] font-bold opacity-70">{completedDateMMDD(task)}</span>
                        )}
                        {isRejectedTask(task) && (
                          <span className="shrink-0 text-[9px] font-bold text-red-700 bg-red-100 rounded px-1">
                            {t('taskStatus.REJECTED')}
                          </span>
                        )}
                      </div>
                      {isRejectedTask(task) && task.review_comment && (
                        <div className="mt-0.5 text-[9px] text-red-700 truncate" title={task.review_comment}>
                          <span className="font-bold">{t('questCard.rejectReasonLabel')}</span>
                          {task.review_comment}
                        </div>
                      )}
                      {task.status === 'COMPLETED' && task.rating && (
                        <div className="flex items-center gap-0.5 mt-0.5">
                          {[...Array(5)].map((_, i) => (
                            <span key={i} className={`text-[8px] ${i < task.rating! ? 'text-yellow-500' : 'text-slate-300'}`}>★</span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Legend */}
        <div className="flex flex-wrap gap-3 px-4 py-2 bg-slate-50 border-t border-slate-200 text-xs text-slate-600">
          <span className="font-bold">{t('weeklyView.legend')}:</span>
          {(['DAILY', 'CHALLENGE', 'TIMED', 'CHAIN', 'COOP'] as const).map((type) => (
            <span key={type} className={`px-1.5 py-0.5 rounded border ${getTypeBadgeColor(type)}`}>
              {t(`taskType.${type}`)}
            </span>
          ))}
          <span className="ml-auto flex flex-wrap items-center gap-3">
            {STATUS_LEGEND.filter(({ key }) => presentStatuses.has(key)).map(({ key, dot }) => (
              <span key={key} className="flex items-center gap-1">
                <span className={`w-2 h-2 rounded-full ${dot}`} /> {t(`taskStatus.${key}`)}
              </span>
            ))}
          </span>
        </div>
      </div>
      ) : (
      /* Mobile: card view when viewport < 1024px */
      <div className="space-y-3">
        {days.map((day) => (
          <div key={day.date} className={`rounded-xl border-2 p-3 ${day.isToday ? `${currentTheme.primaryColor} border-transparent text-white` : 'bg-white/95 border-slate-200 text-slate-800'}`}>
            <div className="flex items-center justify-between mb-2">
              <span className="font-bold text-sm">
                {day.label} · {day.date}
                {day.isToday && <span className="ml-1 text-xs opacity-75">({t('weeklyView.today')})</span>}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full ${day.isToday ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-500'}`}>
                {day.tasks.length} {t('weeklyView.tasks')}
              </span>
            </div>
            {day.tasks.length === 0 ? (
              <p className="text-xs opacity-50 text-center py-2">{t('weeklyView.noTasks')}</p>
            ) : (
              <div className="space-y-1.5">
                {day.tasks.map((task) => (
                  <div
                    key={task.id}
                    onClick={() => setSelectedTask(task)}
                    className={`rounded-lg border-l-3 p-2 text-xs cursor-pointer ${getTypeBadgeColor(task.type)}`}
                  >
                    {/* 标题行是真按钮：整卡可点（鼠标），键盘也能聚焦到这一条打开详情 */}
                    <button
                      type="button"
                      onClick={() => setSelectedTask(task)}
                      aria-label={t('taskDetail.openLabel', { title: task.title })}
                      className="flex w-full items-center gap-2 text-left"
                    >
                      <span className={`w-2 h-2 rounded-full shrink-0 ${getStatusDot(task)}`} />
                      {renderChildBadge(task)}
                      <span className="font-bold flex-1">{task.title}</span>
                      {task.status === 'COMPLETED' && completedDateMMDD(task) && (
                        <span className="shrink-0 text-[10px] font-bold opacity-60">{completedDateMMDD(task)}</span>
                      )}
                      {isRejectedTask(task) && (
                        <span className="shrink-0 text-[10px] font-bold text-red-700 bg-red-100 rounded px-1.5">
                          {t('taskStatus.REJECTED')}
                        </span>
                      )}
                      <span className="text-[10px] opacity-60">{t(`taskType.${task.type}`)}</span>
                    </button>
                    {isRejectedTask(task) && task.review_comment && (
                      <div className="mt-1 text-red-700">
                        <span className="font-bold">{t('questCard.rejectReasonLabel')}</span>
                        {task.review_comment}
                        <span className="block mt-0.5 opacity-80">{t('questCard.rejectResubmitHint')}</span>
                      </div>
                    )}
                    {task.description && (
                      <p className="mt-1 opacity-75 truncate">{task.description}</p>
                    )}
                    {task.status === 'AVAILABLE' && onAcceptAttempt && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onAcceptAttempt(task.id); }}
                        className="mt-1.5 w-full bg-blue-600 text-white text-xs font-bold py-1 rounded hover:bg-blue-700 active:scale-95 transition-all"
                      >
                        {t('questCard.accept')}
                      </button>
                    )}
                    {task.status === 'IN_PROGRESS' && (onAbandonCurrent || onSubmit) && (
                      <div className="flex gap-1 mt-1.5">
                        {onAbandonCurrent && (
                          <button
                            onClick={(e) => { e.stopPropagation(); onAbandonCurrent(task.id); }}
                            className="flex-1 text-red-400 hover:text-red-600 text-xs font-bold py-1 rounded border border-red-200 hover:border-red-400 transition-colors"
                          >
                            {t('questCard.abandon')}
                          </button>
                        )}
                        {onSubmit && (
                          <button
                            onClick={(e) => { e.stopPropagation(); onSubmit(task.id); }}
                            className="flex-1 bg-green-600 text-white text-xs font-bold py-1 rounded hover:bg-green-700 active:scale-95 transition-all"
                          >
                            {t('questCard.submitProof')}
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      )}

      {/* 只读任务详情（孩子端/家长端共用）：桌面 chip 与移动卡片共用同一 selectedTask */}
      <TaskDetailModal
        isOpen={selectedTask !== null}
        onClose={() => setSelectedTask(null)}
        task={selectedTask}
      />
    </div>
  );
};

export default WeeklyTaskView;
