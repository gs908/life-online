import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../services/api';
import type { TaskTemplateRead, TaskTemplateRegenerateResult } from '../services/api';
import { CalendarClock, Plus, Search, X } from 'lucide-react';
import {
  categoryOf,
  describeRange,
  describeTimeWindow,
  describeTrigger,
  type TaskTemplateCategoryIntent,
} from './taskTemplateUtils';
import TaskTemplateDetailDrawer from './TaskTemplateDetailDrawer';
import { isScheduled, localToday } from '../utils/date';

/** 类别徽标（Miss.D §2：100 档底 × 700 档字，对比 ≥ 4.5:1；卡片本体保持中性底）。
 *  补遗 1 §1：列表无「一次性」类，无周期规则模板按 type 归入日常（categoryOf）。 */
const CATEGORY_BADGE: Record<Exclude<TaskTemplateCategoryIntent, 'once'> | 'deprecated', string> = {
  daily: 'bg-sky-100 text-sky-700',
  challenge: 'bg-amber-100 text-amber-700',
  timed: 'bg-rose-100 text-rose-700',
  deprecated: 'bg-slate-200 text-slate-600',
};

type FilterKey = 'all' | Exclude<TaskTemplateCategoryIntent, 'once'> | 'deprecated';

const FILTER_KEYS: FilterKey[] = ['all', 'daily', 'challenge', 'timed', 'deprecated'];

interface TaskTemplateManagerProps {
  /** 家庭 owner 才显示硬删（后端 DELETE 守卫口径：家庭 owner，docs/08 §6A） */
  canHardDelete: boolean;
  onToast: (title: string, msg: string) => void;
  onOpenCreate: () => void;
  onEditTemplate: (template: TaskTemplateRead) => void;
  /** 选模板 → 生成（契约 §6B）：模板行「生成」入口 */
  onOpenGenerate: (template: TaskTemplateRead) => void;
  /** App 层创建/编辑成功后递增，触发本组件重拉 */
  refreshSignal: number;
  /** 生成任务成功后递增 → 详情抽屉的「最近实例」跟着重拉 */
  instancesRefreshSignal?: number;
  /** 实例被 regenerate 终结 / delete 硬删后通知 App 重拉任务板 */
  onInstancesChanged?: () => void;
}

/** 管理端「任务模板」视图（DEV-35 块 A，Miss.D 设计规范 §4/§6）：
 *  与「特权模板」（PrivilegeTree 琥珀色）视觉区分——卡片一律中性底，颜色只出现在类型徽标。
 *
 * 契约 §6B：**模板不绑赛季**（可跨赛季复用）——
 * 列表不再按赛季过滤；`season_id` 只作「来源赛季」标签展示；
 * 无激活赛季时也能新建模板（原赛季闸门已去掉）。 */
const TaskTemplateManager: React.FC<TaskTemplateManagerProps> = ({
  canHardDelete,
  onToast,
  onOpenCreate,
  onEditTemplate,
  onOpenGenerate,
  refreshSignal,
  instancesRefreshSignal,
  onInstancesChanged,
}) => {
  const { t } = useTranslation();
  const today = localToday();
  const [templates, setTemplates] = useState<TaskTemplateRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<FilterKey>('all');

  // 操作态
  const [busyId, setBusyId] = useState<string | null>(null);
  const [deprecating, setDeprecating] = useState<TaskTemplateRead | null>(null);
  const [deprecateReason, setDeprecateReason] = useState('');
  const [regenerating, setRegenerating] = useState<TaskTemplateRead | null>(null);
  const [unconsumedCount, setUnconsumedCount] = useState<number | null>(null);
  /** 已排期到未来、regenerate 不会终结的条数（null = 数不出来 / 超一页） */
  const [scheduledKeptCount, setScheduledKeptCount] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<TaskTemplateRead | null>(null);
  const [deleteStep, setDeleteStep] = useState<1 | 2>(1);
  const [detailId, setDetailId] = useState<string | null>(null);
  /** regenerate 计数竞态守卫：resolve 时只回写仍属于当前弹窗模板的计数（Mars nit） */
  const regenerateIdRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // 列表不分页（契约 §6A）；is_active 不传 = 全部，筛选 chip 与「一次性」类别都在前端推导。
      // ⚠️ 不传 season_id：模板不绑赛季（契约 §6B），按赛季过滤会让上个赛季建的模板"消失"。
      const items = await api.taskTemplates.listTemplates();
      setTemplates(items);
    } catch (error) {
      onToast(t('toast.loadFailedTitle'), error instanceof ApiError ? error.message : t('taskTemplate.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [onToast, t]);

  useEffect(() => {
    load();
  }, [load, refreshSignal]);

  // 三个确认弹窗 Esc 关闭（Miss.D §7，对齐 AddTaskModal / 详情抽屉的既有模式）
  useEffect(() => {
    if (!deprecating && !regenerating && !deleting) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setDeprecating(null);
      setRegenerating(null);
      setDeleting(null);
      setDeleteStep(1);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [deprecating, regenerating, deleting]);

  const filtered = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return templates.filter(template => {
      if (keyword && !template.title.toLowerCase().includes(keyword)) return false;
      if (filter === 'all') return true;
      if (filter === 'deprecated') return !template.is_active;
      return template.is_active && categoryOf(template) === filter;
    });
  }, [templates, search, filter]);

  const counts = useMemo(() => {
    const result: Record<FilterKey, number> = {
      all: templates.length,
      daily: 0,
      challenge: 0,
      timed: 0,
      deprecated: 0,
    };
    for (const template of templates) {
      if (!template.is_active) {
        result.deprecated += 1;
        continue;
      }
      result[categoryOf(template)] += 1;
    }
    return result;
  }, [templates]);

  const FILTERS: Array<{ key: FilterKey; label: string }> = FILTER_KEYS.map(key => ({
    key,
    label: t(`taskTemplate.filter.${key}`),
  }));

  const withBusy = async (templateId: string, action: () => Promise<unknown>): Promise<boolean> => {
    setBusyId(templateId);
    try {
      await action();
      await load();
      return true;
    } catch (error) {
      onToast(t('toast.actionFailedTitle'), error instanceof ApiError ? error.message : t('taskTemplate.opFailed'));
      return false;
    } finally {
      setBusyId(null);
    }
  };

  const openRegenerate = async (template: TaskTemplateRead) => {
    setRegenerating(template);
    regenerateIdRef.current = template.id;
    setUnconsumedCount(null);
    setScheduledKeptCount(null);
    try {
      // 事前 N（DEV-50 审查 🟡5 后口径）：AVAILABLE + IN_PROGRESS 里**会被终结的**
      // 那部分 = 池内实例（`generated_for_date IS NULL OR <= 今天`）。
      // 已排期到未来的实例后端不终结，这里单独计数，文案点名"不受影响"——
      // 否则家长会以为"点一下把明天也清掉了"。
      // PENDING_REVIEW 仍不计入（保留审核机会），与后端一致。
      const [available, inProgress] = await Promise.all([
        api.tasks.listTasks({ template_id: template.id, status: 'AVAILABLE', page_size: 200 }),
        api.tasks.listTasks({ template_id: template.id, status: 'IN_PROGRESS', page_size: 200 }),
      ]);
      const rows = [...available.items, ...inProgress.items];
      const willTerminate = rows.filter(row => !isScheduled(row, today)).length;
      const scheduled = rows.filter(row => isScheduled(row, today)).length;
      // 超过一页时不写死数字（宁可给通用文案，也不报一个偏小的数）
      const truncated = available.total + inProgress.total > rows.length;
      if (regenerateIdRef.current === template.id) {
        setUnconsumedCount(truncated ? null : willTerminate);
        setScheduledKeptCount(truncated ? null : scheduled);
      }
    } catch {
      // 数不出来就不写死数字，文案给通用版
      if (regenerateIdRef.current === template.id) {
        setUnconsumedCount(null);
        setScheduledKeptCount(null);
      }
    }
  };

  /** regenerate 响应按 action 分支 toast（契约 §6A / Gin 注记）；
   *  契约外值兜底处理。任务板重拉不看 action：后端终结池内实例后即生成，
   *  因此只要 terminalized_instance_ids 非空（含 exists/skipped_expired 分支）板就已过期 */
  const regenerateToast = (result: TaskTemplateRegenerateResult) => {
    if (result.terminalized_instance_ids.length > 0) onInstancesChanged?.();
    // 消费响应里的 scheduled_kept_count（后端新增；旧响应可能没这个字段 → ?? 0 兜底）
    const scheduledKept = result.scheduled_kept_count ?? 0;
    const keptLine = scheduledKept > 0
      ? ' ' + t('taskTemplate.regenerateScheduledKept', { count: scheduledKept })
      : '';
    if (result.action === 'created') {
      onToast(t('toast.templateRegeneratedTitle'),
        t('toast.templateRegeneratedMsg', { count: result.terminalized_instance_ids.length }) + keptLine);
    } else if (result.action === 'kept') {
      onToast(t('toast.templateRegeneratedTitle'), t('toast.templateRegenerateKeptMsg') + keptLine);
    } else if (result.action === 'exists') {
      onToast(t('toast.templateRegeneratedTitle'), t('toast.templateRegenerateExistsMsg') + keptLine);
    } else {
      onToast(t('toast.templateRegeneratedTitle'), t('toast.templateRegenerateNoNewMsg') + keptLine);
    }
  };

  const detailTemplate = detailId ? templates.find(item => item.id === detailId) ?? null : null;

  return (
    <div data-testid="task-template-manager">
      {/* 头部（Miss.D §4：CalendarClock 蓝图标 + 标题/副标题 + 搜索 + 绿色新建） */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-sky-700 text-white flex items-center justify-center shrink-0">
            <CalendarClock size={20} aria-hidden />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-800">{t('taskTemplate.title')}</h2>
            <p className="text-xs text-slate-500">{t('taskTemplate.subtitle')}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" aria-hidden />
            <input
              type="search"
              value={search}
              onChange={event => setSearch(event.target.value)}
              placeholder={t('taskTemplate.searchPlaceholder')}
              aria-label={t('taskTemplate.searchPlaceholder')}
              className="border border-slate-200 bg-white rounded-lg pl-8 pr-3 py-2 text-sm w-44 focus:outline-none focus:border-sky-500"
            />
          </div>
          <button
            onClick={onOpenCreate}
            className="bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-1.5 hover:bg-green-700 transition-colors shadow-md shadow-green-600/20"
          >
            <Plus size={16} aria-hidden /> {t('taskTemplate.createTemplate')}
          </button>
        </div>
      </div>

      {/* 模板与赛季无关（契约 §6B）：无激活赛季也能维护模板库，故这里只做中性说明，不再禁用新建 */}
      <p className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-lg p-3 mt-3">
        {t('taskTemplate.seasonAgnosticHint')}
      </p>

      {/* 筛选 chips（Miss.D §4） */}
      <div className="flex flex-wrap gap-1.5 mt-4" role="group" aria-label={t('taskTemplate.title')}>
        {FILTERS.map(item => {
          const active = filter === item.key;
          return (
            <button
              key={item.key}
              type="button"
              aria-pressed={active}
              onClick={() => setFilter(item.key)}
              className={`text-xs px-3 py-1.5 rounded-full border font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600 ${
                active
                  ? 'bg-slate-900 text-white border-slate-900'
                  : 'bg-white border-slate-200 text-slate-600 hover:border-slate-400'
              }`}
            >
              {item.label} {counts[item.key]}
            </button>
          );
        })}
      </div>

      {/* 列表 */}
      <div className="mt-3">
        {loading ? (
          // skeleton 卡 ×3（Miss.D §6 列表加载）
          [0, 1, 2].map(i => (
            <div key={i} className="bg-white border border-slate-200 rounded-xl p-3.5 mb-2 animate-pulse" aria-hidden>
              <div className="h-4 bg-slate-100 rounded w-1/3 mb-2" />
              <div className="h-3 bg-slate-100 rounded w-2/3" />
            </div>
          ))
        ) : filtered.length === 0 ? (
          templates.length === 0 ? (
            // 真空态（Miss.D §6）
            <div className="bg-white border border-dashed border-slate-300 rounded-xl p-8 text-center">
              <div className="text-3xl mb-2" aria-hidden>🗓️</div>
              <p className="font-bold text-slate-700 text-sm">{t('taskTemplate.emptyTitle')}</p>
              <p className="text-xs text-slate-500 mt-1 mb-4">{t('taskTemplate.emptyHint')}</p>
              <button
                onClick={onOpenCreate}
                className="bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-green-700"
              >
                {t('taskTemplate.createTemplate')}
              </button>
            </div>
          ) : (
            // 筛选/搜索空（Miss.D §6）
            <div className="bg-white border border-dashed border-slate-300 rounded-xl p-6 text-center">
              <p className="text-sm text-slate-500">{t('taskTemplate.noMatchTitle')}</p>
              <button
                onClick={() => { setSearch(''); setFilter('all'); }}
                className="text-xs text-sky-700 font-bold underline mt-2"
              >
                {t('taskTemplate.clearFilters')}
              </button>
            </div>
          )
        ) : (
          filtered.map(template => {
            const category = categoryOf(template);
            const active = template.is_active;
            const busy = busyId === template.id;
            return (
              <div
                key={template.id}
                className={`bg-white border border-slate-200 rounded-xl p-3.5 mb-2 flex justify-between items-center gap-3 transition-opacity ${active ? '' : 'opacity-65'}`}
              >
                <button
                  type="button"
                  onClick={() => setDetailId(template.id)}
                  className="text-left flex-1 min-w-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600 rounded"
                  aria-label={t('taskTemplate.openDetail', { title: template.title })}
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${CATEGORY_BADGE[active ? category : 'deprecated']}`}>
                      {t(`taskTemplate.cat.${category}`)}
                    </span>
                    <span className="text-sm font-bold text-slate-800 truncate">{template.title}</span>
                    <span className="text-[11px] text-slate-400 shrink-0">
                      XP {template.xp_reward}
                      {template.difficulty ? ' · ' + '★'.repeat(template.difficulty) + '☆'.repeat(5 - template.difficulty) : ''}
                    </span>
                  </div>
                  <div className="text-xs text-slate-500 mt-1 truncate">
                    🕘 {template.triggers.length > 0
                      ? template.triggers.map(trigger => describeTrigger(trigger, t)).join(t('taskTemplate.listJoiner'))
                      : t('taskTemplate.noTriggers')}
                    {' · '}⏱ {describeTimeWindow(template, t)}
                    {/* 来源赛季标签（契约 §6B）：模板不绑赛季，这里只作溯源提示 */}
                    {template.season_name && (
                      ' · ' + t('taskTemplate.sourceSeason', { name: template.season_name })
                    )}
                    {!active && template.deprecated_at && (
                      ' · ' + t('taskTemplate.deprecatedInfo', {
                        date: template.deprecated_at.slice(0, 10),
                        reason: template.deprecated_reason || '',
                      })
                    )}
                  </div>
                </button>
                <div className="flex items-center gap-3 shrink-0">
                  <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${active ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500'}`}>
                    {active ? t('taskTemplate.statusActive') : t('taskTemplate.statusDeprecated')}
                  </span>
                  {active ? (
                    <>
                      <button disabled={busy} onClick={() => onEditTemplate(template)} className="text-xs font-semibold text-sky-700 hover:text-sky-800 disabled:opacity-50">
                        {t('taskTemplate.edit')}
                      </button>
                      {/* 选模板 → 生成（契约 §6B）：与「重新生成」（终结重建）语义不同。
                          ⚠️ CHAIN 第 2..N 步模板不显示：链实例由"链首投放 + 逐步解锁"产生，
                          手动生成会绕过解锁（今天生成会把 NULL 日期的链实例盖上今天，未来日期直接建平行实例）。
                          后端另有 409 守卫兜底（Mars 审查 🟡4）。 */}
                      {!(template.type === 'CHAIN' && template.chain_order > 1) && (
                        <button
                          disabled={busy}
                          onClick={() => onOpenGenerate(template)}
                          className="text-xs font-bold text-green-700 hover:text-green-800 disabled:opacity-50"
                        >
                          {t('taskTemplate.generate')}
                        </button>
                      )}
                      <button disabled={busy} onClick={() => openRegenerate(template)} className="text-xs text-slate-500 hover:text-slate-700 disabled:opacity-50">
                        {t('taskTemplate.regenerate')}
                      </button>
                      <button
                        disabled={busy}
                        onClick={() => { setDeprecating(template); setDeprecateReason(''); }}
                        className="text-xs text-red-700 hover:text-red-800 disabled:opacity-50"
                      >
                        {t('taskTemplate.deprecate')}
                      </button>
                    </>
                  ) : (
                    <>
                      {canHardDelete && (
                        <button disabled={busy} onClick={() => { setDeleting(template); setDeleteStep(1); }} className="text-xs text-red-700 hover:text-red-800 disabled:opacity-50">
                          {t('common.delete')}
                        </button>
                      )}
                      <button disabled={busy} onClick={() => withBusy(template.id, () => api.taskTemplates.activateTemplate(template.id))} className="text-xs font-semibold text-sky-700 hover:text-sky-800 disabled:opacity-50">
                        {t('taskTemplate.activate')}
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* 停用确认（原因必填，Miss.D §6） */}
      {deprecating && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label={t('taskTemplate.deprecateTitle')}>
          <div className="bg-white rounded-2xl w-full max-w-sm p-5 shadow-2xl">
            <div className="flex justify-between items-center mb-2">
              <h4 className="font-bold text-slate-800">{t('taskTemplate.deprecateTitle')}</h4>
              <button onClick={() => setDeprecating(null)} aria-label={t('common.close')}><X size={16} /></button>
            </div>
            <p className="text-xs text-slate-500 mb-3">{t('taskTemplate.deprecateHint')}</p>
            <label className="text-xs font-bold text-slate-600 block mb-1" htmlFor="deprecate-reason">
              {t('taskTemplate.deprecateReasonLabel')}
            </label>
            <textarea
              id="deprecate-reason"
              value={deprecateReason}
              onChange={event => setDeprecateReason(event.target.value)}
              placeholder={t('taskTemplate.deprecateReasonPlaceholder')}
              maxLength={128}
              className="w-full border border-slate-200 rounded-lg p-2 text-sm h-20"
            />
            {!deprecateReason.trim() && (
              <p className="text-[11px] text-slate-400 mt-1">{t('taskTemplate.deprecateReasonRequired')}</p>
            )}
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setDeprecating(null)} className="px-4 py-2 text-slate-600 font-bold text-sm hover:bg-slate-100 rounded">{t('common.cancel')}</button>
              <button
                disabled={!deprecateReason.trim() || busyId === deprecating.id}
                onClick={() => {
                  const target = deprecating;
                  setDeprecating(null);
                  withBusy(target.id, () => api.taskTemplates.deprecateTemplate(target.id, { reason: deprecateReason.trim() }))
                    .then(ok => { if (ok) onToast(t('toast.templateDeprecatedTitle'), t('toast.templateDeprecatedMsg', { title: target.title })); });
                }}
                className="px-4 py-2 bg-red-600 text-white font-bold text-sm rounded hover:bg-red-700 disabled:opacity-50"
              >
                {t('taskTemplate.deprecateConfirm')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 重新生成确认（红色确认，展示 N，Miss.D §6） */}
      {regenerating && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label={t('taskTemplate.regenerateTitle')}>
          <div className="bg-white rounded-2xl w-full max-w-sm p-5 shadow-2xl">
            <div className="flex justify-between items-center mb-2">
              <h4 className="font-bold text-slate-800">{t('taskTemplate.regenerateTitle')}</h4>
              <button onClick={() => setRegenerating(null)} aria-label={t('common.close')}><X size={16} /></button>
            </div>
            <p className="text-sm text-slate-600 mb-2">
              {unconsumedCount === null
                ? t('taskTemplate.regenerateBodyPlain', { title: regenerating.title })
                : t('taskTemplate.regenerateBody', { title: regenerating.title, count: unconsumedCount })}
            </p>
            {/* 已排期到未来的实例不在终结范围内（DEV-50 审查 🟡5）：必须点名，
                否则家长会以为"点一下把明天也清掉了"。数不出来时不显示，不瞎写数字。 */}
            {scheduledKeptCount !== null && scheduledKeptCount > 0 && (
              <p className="text-xs text-sky-700 bg-sky-50 border border-sky-200 rounded-lg p-2 mb-3">
                {t('taskTemplate.regenerateScheduledKept', { count: scheduledKeptCount })}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <button onClick={() => setRegenerating(null)} className="px-4 py-2 text-slate-600 font-bold text-sm hover:bg-slate-100 rounded">{t('common.cancel')}</button>
              <button
                disabled={busyId === regenerating.id}
                onClick={() => {
                  const target = regenerating;
                  setRegenerating(null);
                  const regenerateResult: TaskTemplateRegenerateResult[] = [];
                  withBusy(target.id, async () => {
                    regenerateResult.push(await api.taskTemplates.regenerateTemplate(target.id));
                  })
                    .then(ok => { if (ok && regenerateResult[0]) regenerateToast(regenerateResult[0]); });
                }}
                className="px-4 py-2 bg-red-600 text-white font-bold text-sm rounded hover:bg-red-700 disabled:opacity-50"
              >
                {t('taskTemplate.regenerateConfirm')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 硬删双重确认（仅家庭 owner 可见，Miss.D §6） */}
      {deleting && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label={t('taskTemplate.deleteTitle')}>
          <div className="bg-white rounded-2xl w-full max-w-sm p-5 shadow-2xl">
            <div className="flex justify-between items-center mb-2">
              <h4 className="font-bold text-slate-800">{t('taskTemplate.deleteTitle')}</h4>
              <button onClick={() => setDeleting(null)} aria-label={t('common.close')}><X size={16} /></button>
            </div>
            {deleteStep === 1 ? (
              <>
                <p className="text-sm text-slate-600 mb-4">{t('taskTemplate.deleteBody', { title: deleting.title })}</p>
                <div className="flex justify-end gap-2">
                  <button onClick={() => setDeleting(null)} className="px-4 py-2 text-slate-600 font-bold text-sm hover:bg-slate-100 rounded">{t('common.cancel')}</button>
                  <button onClick={() => setDeleteStep(2)} className="px-4 py-2 bg-slate-800 text-white font-bold text-sm rounded hover:bg-slate-900">
                    {t('taskTemplate.deleteNext')}
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="text-sm font-bold text-red-700 mb-4">{t('taskTemplate.deleteFinalBody')}</p>
                <div className="flex justify-end gap-2">
                  <button onClick={() => { setDeleting(null); setDeleteStep(1); }} className="px-4 py-2 text-slate-600 font-bold text-sm hover:bg-slate-100 rounded">{t('common.cancel')}</button>
                  <button
                    disabled={busyId === deleting.id}
                    onClick={() => {
                      const target = deleting;
                      setDeleting(null);
                      setDeleteStep(1);
                      withBusy(target.id, () => api.taskTemplates.deleteTemplate(target.id))
                        .then(ok => {
                          if (ok) {
                            onToast(t('toast.templateDeletedTitle'), t('toast.templateDeletedMsg', { title: target.title }));
                            onInstancesChanged?.();
                          }
                        });
                    }}
                    className="px-4 py-2 bg-red-600 text-white font-bold text-sm rounded hover:bg-red-700 disabled:opacity-50"
                  >
                    {t('taskTemplate.deleteConfirm')}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* 详情抽屉 */}
      <TaskTemplateDetailDrawer
        template={detailTemplate}
        refreshSignal={instancesRefreshSignal}
        onClose={() => setDetailId(null)}
        onEdit={(target) => { setDetailId(null); onEditTemplate(target); }}
      />
    </div>
  );
};

export default TaskTemplateManager;
