import React, { useState, useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { TaskRead } from '../../services/api';
import type { SeasonTheme } from '../../types';
import { ChevronLeft, ChevronRight, Calendar } from 'lucide-react';
import { localToday } from '../../utils/date';

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
  onAcceptAttempt: (id: string) => void;
  onSubmit: (id: string) => void;
  onAbandonCurrent: (id: string) => void;
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

function getStatusDot(status: string) {
  switch (status) {
    case 'AVAILABLE': return 'bg-green-400';
    case 'IN_PROGRESS': return 'bg-blue-400 animate-pulse';
    case 'PENDING_REVIEW': return 'bg-yellow-400';
    case 'COMPLETED': return 'bg-gray-400';
    case 'EXPIRED': return 'bg-red-300';
    default: return 'bg-slate-300';
  }
}

const WeeklyTaskView: React.FC<WeeklyTaskViewProps> = ({
  tasks,
  currentTheme,
  onAcceptAttempt,
  onSubmit,
  onAbandonCurrent,
}) => {
  const { t } = useTranslation();
  const today = localToday();
  const isLg = useIsLg();

  const [weekOffset, setWeekOffset] = useState(0);

  // Build week start (Monday) based on offset
  const weekStart = useMemo(() => {
    const todayDate = new Date();
    const dayOfWeek = todayDate.getDay(); // 0=Sun, 1=Mon
    // Adjust: get Monday of current week
    const monday = new Date(todayDate);
    monday.setDate(todayDate.getDate() - ((dayOfWeek + 6) % 7) + weekOffset * 7);
    return monday;
  }, [weekOffset]);

  const days: DayCell[] = useMemo(() => {
    const result: DayCell[] = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(weekStart);
      d.setDate(weekStart.getDate() + i);
      const dateStr = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
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

  // Group tasks by generated_for_date
  const tasksByDate = useMemo(() => {
    const map: Record<string, TaskRead[]> = {};
    for (const task of tasks) {
      const date = task.generated_for_date ?? today;
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
  }, [tasks, today]);

  // Assign tasks to day cells
  for (const day of days) {
    day.tasks = tasksByDate[day.date] ?? [];
  }

  const prevWeek = () => setWeekOffset(prev => prev - 1);
  const nextWeek = () => setWeekOffset(prev => prev + 1);
  const goToCurrentWeek = () => setWeekOffset(0);

  const isPastWeek = weekOffset < 0;

  return (
    <div className="space-y-4">
      {/* Week Header */}
      <div className="flex items-center justify-between">
        <h3 className={`text-lg font-bold flex items-center gap-2 ${currentTheme.textColor} drop-shadow-sm`}>
          <Calendar size={18} /> {t('weeklyView.title')}
        </h3>
        <div className="flex items-center gap-1">
          <button
            onClick={prevWeek}
            disabled={isPastWeek}
            className="p-1.5 rounded-lg hover:bg-white/20 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            aria-label={t('weeklyView.prevWeek')}
          >
            <ChevronLeft size={18} className={currentTheme.textColor} />
          </button>
          <button
            onClick={goToCurrentWeek}
            className={`px-2 py-1 text-xs font-bold rounded-lg transition-colors ${
              weekOffset !== 0
                ? 'bg-white/20 hover:bg-white/30 text-white'
                : 'opacity-50 cursor-default'
            }`}
          >
            {t('weeklyView.currentWeek')}
          </button>
          <button
            onClick={nextWeek}
            className="p-1.5 rounded-lg hover:bg-white/20 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            aria-label={t('weeklyView.nextWeek')}
          >
            <ChevronRight size={18} className={currentTheme.textColor} />
          </button>
        </div>
      </div>

      {/* Week Grid - desktop only: 7 columns, hidden on mobile */}
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
                <div className="text-sm">{new Date(day.date).getDate()}</div>
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
                        className={`rounded-lg border-l-2 p-1.5 text-xs cursor-default transition-all hover:scale-[1.02] ${getTypeBadgeColor(task.type)}`}
                        title={`${task.title} (${task.type})`}
                      >
                        <div className="flex items-center gap-1">
                          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${getStatusDot(task.status)}`} />
                          <span className="font-bold truncate flex-1 leading-tight">{task.title}</span>
                        </div>
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
            <span className="ml-auto flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-green-400" /> {t('taskStatus.AVAILABLE')}
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" /> {t('taskStatus.IN_PROGRESS')}
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-yellow-400" /> {t('taskStatus.PENDING_REVIEW')}
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-gray-400" /> {t('taskStatus.COMPLETED')}
            </span>
          </div>
        </div>
      ) : (
        /* Mobile: card view when grid is too cramped */
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
                      className={`rounded-lg border-l-3 p-2 text-xs ${getTypeBadgeColor(task.type)}`}
                    >
                      <div className="flex items-center gap-2">
                        <span className={`w-2 h-2 rounded-full shrink-0 ${getStatusDot(task.status)}`} />
                        <span className="font-bold flex-1">{task.title}</span>
                        <span className="text-[10px] opacity-60">{t(`taskType.${task.type}`)}</span>
                      </div>
                      {task.description && (
                        <p className="mt-1 opacity-75 truncate">{task.description}</p>
                      )}
                      {task.status === 'AVAILABLE' && (
                        <button
                          onClick={() => onAcceptAttempt(task.id)}
                          className="mt-1.5 w-full bg-blue-600 text-white text-xs font-bold py-1 rounded hover:bg-blue-700 active:scale-95 transition-all"
                        >
                          {t('questCard.accept')}
                        </button>
                      )}
                      {task.status === 'IN_PROGRESS' && (
                        <div className="flex gap-1 mt-1.5">
                          <button
                            onClick={() => onAbandonCurrent(task.id)}
                            className="flex-1 text-red-400 hover:text-red-600 text-xs font-bold py-1 rounded border border-red-200 hover:border-red-400 transition-colors"
                          >
                            {t('questCard.abandon')}
                          </button>
                          <button
                            onClick={() => onSubmit(task.id)}
                            className="flex-1 bg-green-600 text-white text-xs font-bold py-1 rounded hover:bg-green-700 active:scale-95 transition-all"
                          >
                            {t('questCard.submitProof')}
                          </button>
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
    </div>
  );
};

export default WeeklyTaskView;
