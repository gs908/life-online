import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../../services/api';
import type {
  SeasonRead,
  TaskGenerateRequest,
  TaskGenerateResult,
  TaskTemplateRead,
} from '../../services/api';
import { CalendarClock, Info, Sparkles, X } from 'lucide-react';
import TaskTuneFields, { type TuneField, type TuneValues } from '../TaskTuneFields';
import { TARGET_DATE_MAX_AHEAD_DAYS, addDays, localToday } from '../../utils/date';

interface GenerateTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** 从模板行进入时模板已定；`null` = 从任务板进入，先走「选模板」一步 */
  initialTemplate: TaskTemplateRead | null;
  /** 生成时的赛季背景取自**当前激活赛季**（不从模板带出）；null = 无进行中赛季 */
  activeSeason: SeasonRead | null;
  /** 成功（含 action='exists' 命中既有实例）→ 父层重拉任务板与模板视图 */
  onGenerated: (result: TaskGenerateResult) => void;
  onToast: (title: string, msg: string) => void;
}

const EMPTY_VALUES: TuneValues = { difficulty: null, time_deposit: 0, xp_reward: 0 };
const EMPTY_DIRTY: Record<TuneField, boolean> = {
  difficulty: false,
  time_deposit: false,
  xp_reward: false,
};

/**
 * 「选模板 → 生成（目标日期）→ 微调三项 → 提交」（契约 §6B）。
 *
 * 契约要点全部落在这里：
 * - 目标日期：默认今天，`min`=今天、`max`=今天+30 天，前端三道校验 + 服务端 422 兜底；
 * - 三个覆盖字段走 dirty tracking，**永不发 null**（快照语义，null 一律 422）；
 * - 无激活赛季 → 禁用提交并说明（实例必须归属一个赛季）；
 * - 目标日期越过赛季 `end_date` → **仅提示不阻止**（业主裁决第 5 项）；
 * - 该日期已有实例 → 中性提示「将直接使用该实例（不覆盖、不重建）」。
 */
const GenerateTaskModal: React.FC<GenerateTaskModalProps> = ({
  isOpen,
  onClose,
  initialTemplate,
  activeSeason,
  onGenerated,
  onToast,
}) => {
  const { t } = useTranslation();
  const today = useMemo(() => localToday(), [isOpen]);
  const maxDate = useMemo(() => addDays(today, TARGET_DATE_MAX_AHEAD_DAYS), [today]);

  const [templates, setTemplates] = useState<TaskTemplateRead[] | null>(null);
  const [templateId, setTemplateId] = useState<string>('');
  const [targetDate, setTargetDate] = useState<string>(today);
  const [values, setValues] = useState<TuneValues>(EMPTY_VALUES);
  const [dirty, setDirty] = useState<Record<TuneField, boolean>>(EMPTY_DIRTY);
  const [fillingBack, setFillingBack] = useState<TuneField | null>(null);
  /** 目标日期是否已有实例（预检，中性提示，不是警示） */
  const [dateHasInstance, setDateHasInstance] = useState<boolean | null>(null);
  const [result, setResult] = useState<TaskGenerateResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const selected = useMemo(() => {
    if (initialTemplate) return initialTemplate;
    return templates?.find(item => item.id === templateId) ?? null;
  }, [initialTemplate, templates, templateId]);

  /** 切换模板 → 三项回到该模板当前值、清空 dirty（避免把上个模板的值带过去） */
  const applyTemplateDefaults = useCallback((template: TaskTemplateRead | null) => {
    if (!template) {
      setValues(EMPTY_VALUES);
    } else {
      setValues({
        difficulty: template.difficulty,
        time_deposit: template.time_deposit,
        xp_reward: template.xp_reward,
      });
    }
    setDirty(EMPTY_DIRTY);
  }, []);

  // 打开时重置；从任务板进入则拉一次模板列表（跨赛季全量，不传 season_id）
  useEffect(() => {
    if (!isOpen) return;
    setTargetDate(today);
    setResult(null);
    setFormError(null);
    setDateHasInstance(null);
    setFillingBack(null);
    applyTemplateDefaults(initialTemplate);
    setTemplateId(initialTemplate?.id ?? '');
    if (initialTemplate) {
      setTemplates(null);
      return;
    }
    let cancelled = false;
    setTemplates(null);
    api.taskTemplates
      .listTemplates()
      .then(items => {
        if (!cancelled) setTemplates(items.filter(item => item.is_active));
      })
      .catch(() => {
        if (!cancelled) setTemplates([]);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, initialTemplate, today, applyTemplateDefaults]);

  // 预检：该模板在目标日期是否已有实例（中性提示用）。列表接口无按日筛选，
  // 故按 template_id 取一批后在本地比对 generated_for_date。
  useEffect(() => {
    if (!isOpen || !selected || !targetDate) return;
    let cancelled = false;
    setDateHasInstance(null);
    api.tasks
      .listTasks({ template_id: selected.id, page_size: 200 })
      .then(page => {
        if (!cancelled) {
          setDateHasInstance(page.items.some(task => task.generated_for_date === targetDate));
        }
      })
      .catch(() => {
        if (!cancelled) setDateHasInstance(null); // 数不出来就不显示该行，不瞎猜
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, selected, targetDate]);

  // Esc 关闭
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  const dateError = useMemo<'min' | 'max' | null>(() => {
    if (!targetDate) return 'min';
    if (targetDate < today) return 'min';
    if (targetDate > maxDate) return 'max';
    return null;
  }, [targetDate, today, maxDate]);

  const beyondSeasonEnd = Boolean(
    activeSeason?.end_date && targetDate > activeSeason.end_date.slice(0, 10),
  );

  const changeField = (field: TuneField, next: number) => {
    setValues(prev => ({ ...prev, [field]: next }));
    setDirty(prev => ({ ...prev, [field]: true }));
  };

  /** 「按模板当前值填回」= 现取一次模板当前值再填（一次性取值，不是持续跟随） */
  const fillBack = async (field: TuneField) => {
    if (!selected) return;
    setFillingBack(field);
    try {
      const fresh = await api.taskTemplates.getTemplate(selected.id);
      const next =
        field === 'difficulty' ? fresh.difficulty ?? 0 : field === 'time_deposit' ? fresh.time_deposit : fresh.xp_reward;
      setValues(prev => ({ ...prev, [field]: next }));
      setDirty(prev => ({ ...prev, [field]: true }));
    } catch (error) {
      onToast(t('toast.actionFailedTitle'), error instanceof ApiError ? error.message : t('tune.fillBackFailed'));
    } finally {
      setFillingBack(null);
    }
  };

  const handleSubmit = async () => {
    if (!selected || dateError || !activeSeason) return;
    setFormError(null);
    setSubmitting(true);
    // 只提交用户改过的字段：未改动 = 不放进 body = 用模板当前值（快照）
    const body: TaskGenerateRequest = { target_date: targetDate };
    if (dirty.difficulty && values.difficulty !== null) body.difficulty = values.difficulty;
    if (dirty.time_deposit) body.time_deposit = values.time_deposit;
    if (dirty.xp_reward) body.xp_reward = values.xp_reward;
    try {
      const generated = await api.taskTemplates.generateTemplate(selected.id, body);
      setResult(generated);
      onGenerated(generated);
    } catch (error) {
      // 422（日期/取值越界）/ 409（模板停用、无激活赛季）等：原样透出后端人话文案
      setFormError(error instanceof ApiError ? error.message : t('generateTask.failed'));
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  const dateFieldError = dateError
    ? dateError === 'min'
      ? t('generateTask.errDateTooEarly')
      : t('generateTask.errDateTooFar', { days: TARGET_DATE_MAX_AHEAD_DAYS })
    : null;

  const resultActionCopy = (r: TaskGenerateResult): string => {
    switch (r.action) {
      case 'created':
        return t('generateTask.resultCreated');
      case 'exists':
        return t('generateTask.resultExists');
      case 'rolled_forward':
        return t('generateTask.resultRolled');
      case 'kept':
        return t('generateTask.resultKept');
      case 'skipped_expired':
        return t('generateTask.resultSkipped');
      default:
        return '';
    }
  };

  const isFuture = Boolean(result && result.generated_for_date > today);

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div
        className="bg-white rounded-2xl w-full max-w-xl shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200"
        role="dialog"
        aria-modal="true"
        aria-label={t('generateTask.title')}
      >
        <div className="bg-slate-900 text-white p-4 flex justify-between items-center">
          <h3 className="font-bold text-lg flex items-center gap-2">
            <Sparkles size={20} /> {t('generateTask.title')}
          </h3>
          <button onClick={onClose} aria-label={t('common.close')}>
            <X />
          </button>
        </div>

        <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          {/* 步骤 1：选模板（仅从任务板进入时出现） */}
          {!initialTemplate && (
            <div className="space-y-1.5">
              <label className="text-sm font-bold text-slate-700" htmlFor="generate-template">
                {t('generateTask.pickTemplate')}
              </label>
              {templates === null ? (
                <p className="text-xs text-slate-400 animate-pulse">{t('common.loading')}</p>
              ) : templates.length === 0 ? (
                <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3">
                  {t('generateTask.noTemplates')}
                </p>
              ) : (
                <select
                  id="generate-template"
                  value={templateId}
                  onChange={event => {
                    const next = templates.find(item => item.id === event.target.value) ?? null;
                    setTemplateId(event.target.value);
                    applyTemplateDefaults(next);
                    setResult(null);
                  }}
                  className="w-full border border-slate-200 rounded-lg p-2 text-sm bg-white"
                >
                  <option value="">{t('generateTask.pickTemplatePlaceholder')}</option>
                  {templates.map(item => (
                    <option key={item.id} value={item.id}>
                      {item.title}
                      {item.season_name ? ` · ${t('generateTask.sourceSeason', { name: item.season_name })}` : ''}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}

          {selected && (
            <>
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-bold text-slate-800">{selected.title}</span>
                <span className="text-[11px] text-slate-400">
                  {t(`taskType.${selected.type}`)}
                  {selected.difficulty !== null
                    ? ` · ${'★'.repeat(selected.difficulty)}${'☆'.repeat(5 - selected.difficulty)}`
                    : ` · ${t('tune.unrated')}`}
                </span>
              </div>

              {/* 赛季背景：只读，取自当前激活赛季（不来自模板） */}
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-3">
                <div className="text-xs font-bold text-slate-600 mb-1 flex items-center gap-1">
                  <CalendarClock size={13} aria-hidden /> {t('generateTask.seasonBackground')}
                </div>
                {activeSeason ? (
                  <>
                    <div className="text-sm font-bold text-slate-700">{activeSeason.name}</div>
                    {activeSeason.narrative_context && (
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        “{activeSeason.narrative_context.slice(0, 80)}
                        {activeSeason.narrative_context.length > 80 ? '…' : ''}”
                      </p>
                    )}
                    <p className="text-[11px] text-slate-400 mt-1">{t('generateTask.seasonBackgroundHint')}</p>
                  </>
                ) : (
                  <p className="text-xs text-amber-700">{t('generateTask.noActiveSeason')}</p>
                )}
              </div>

              {/* 目标日期 */}
              <div className="space-y-1.5">
                <label className="text-sm font-bold text-slate-700" htmlFor="generate-target-date">
                  {t('generateTask.targetDate')}
                </label>
                <input
                  id="generate-target-date"
                  type="date"
                  value={targetDate}
                  min={today}
                  max={maxDate}
                  onChange={event => {
                    setTargetDate(event.target.value);
                    setResult(null);
                  }}
                  aria-invalid={Boolean(dateError)}
                  aria-describedby="generate-target-date-hint"
                  className={`border rounded-lg p-2 text-sm ${
                    dateError ? 'border-red-400' : 'border-slate-200'
                  }`}
                />
                {dateFieldError ? (
                  <p className="text-xs text-red-600" aria-live="polite">{dateFieldError}</p>
                ) : (
                  <p id="generate-target-date-hint" className="text-[11px] text-slate-400">
                    {t('generateTask.dateHint', { days: TARGET_DATE_MAX_AHEAD_DAYS })}
                  </p>
                )}
                {beyondSeasonEnd && !dateError && (
                  <p className="text-[11px] text-amber-600 bg-amber-50 border border-amber-200 rounded-lg p-2" aria-live="polite">
                    {t('generateTask.beyondSeasonEnd', {
                      date: targetDate,
                      name: activeSeason?.name ?? '',
                      end: activeSeason?.end_date?.slice(0, 10) ?? '',
                    })}
                  </p>
                )}
                {dateHasInstance && !dateError && (
                  <p className="text-[11px] text-slate-600 bg-slate-50 border border-slate-200 rounded-lg p-2 flex items-start gap-1" aria-live="polite">
                    <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
                    <span>{t('generateTask.dateHasInstance', { date: targetDate })}</span>
                  </p>
                )}
              </div>

              {/* 三项微调（与微调表单共用组件） */}
              <div>
                <div className="text-xs font-bold text-slate-600 mb-1.5">{t('tune.sectionTitle')}</div>
                <TaskTuneFields
                  template={{
                    id: selected.id,
                    type: selected.type,
                    estimated_minutes: selected.estimated_minutes,
                  }}
                  value={values}
                  dirty={dirty}
                  onChange={changeField}
                  onFillBack={fillBack}
                  fillingBack={fillingBack}
                  previewDate={targetDate}
                  disabled={submitting}
                />
              </div>

              {/* 提交后回显 */}
              {result && (
                <div
                  className="bg-green-50 border border-green-200 rounded-xl p-3 space-y-1"
                  role="status"
                  aria-live="polite"
                >
                  <div className="text-sm font-bold text-green-800">
                    {isFuture
                      ? t('generateTask.scheduledFor', { date: result.generated_for_date })
                      : t('generateTask.deployedToday')}
                  </div>
                  <p className="text-xs text-green-700">{resultActionCopy(result)}</p>
                  <p className="text-[11px] text-slate-500">
                    {t('generateTask.resultValues', {
                      difficulty: result.difficulty ?? t('tune.unrated'),
                      deposit: result.time_deposit,
                      xp: result.xp_reward,
                    })}
                    {result.season_name ? ` · ${result.season_name}` : ''}
                    {` · ${t(`contentSource.${result.content_source}`)}`}
                  </p>
                </div>
              )}

              {formError && (
                <div role="alert" className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm font-bold">
                  {formError}
                </div>
              )}
            </>
          )}
        </div>

        <div className="p-4 bg-slate-50 border-t flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold hover:bg-slate-200 rounded">
            {t('common.close')}
          </button>
          <button
            onClick={handleSubmit}
            disabled={!selected || Boolean(dateError) || !activeSeason || submitting}
            title={!activeSeason ? t('generateTask.noActiveSeason') : undefined}
            className="px-4 py-2 bg-green-600 text-white font-bold rounded hover:bg-green-700 shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? t('common.loading') : t('generateTask.submit')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default GenerateTaskModal;