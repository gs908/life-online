import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../services/api';
import type { TaskDepositPreviewResponse, TaskType } from '../services/api';
import { AlertTriangle, Coins, Info, RefreshCw } from 'lucide-react';

/**
 * 难度 / 时间币押金 / 经验值 三字段的微调控件（契约 §6B）。
 *
 * 生成表单（GenerateTaskModal）与微调表单（TuneTaskModal）**共用本组件**，
 * 两边的差异只在默认值来源与提交目标，字段与校验完全一致。
 *
 * 三条写死的契约规则：
 * 1. **三个字段都是快照**，没有「跟随模板」这回事；`null` 一律 422，本组件**永不产出 null**。
 * 2. **未动过的字段不提交**（dirty tracking）—— 否则会把"看一眼"的字段写进 body。
 * 3. 「恢复默认」= **取模板当前值填回**（一次性取值），不是持续跟随；副文案已写明。
 */

export type TuneField = 'difficulty' | 'time_deposit' | 'xp_reward';

export interface TuneValues {
  difficulty: number | null;
  time_deposit: number;
  xp_reward: number;
}

/** 押金预览与「填回」所需的模板侧输入 */
export interface TuneTemplateSource {
  /** `null` = 实例的模板已被硬删（FK 走 SET NULL），「填回」无值可取 */
  id: string | null;
  type: TaskType;
  estimated_minutes: number | null;
}

interface TaskTuneFieldsProps {
  template: TuneTemplateSource;
  value: TuneValues;
  /** 每个字段用户是否改动过（未改动的不会进入请求体） */
  dirty: Record<TuneField, boolean>;
  /** `next` 永远不是 null：难度也无法被清空（清空 = 传 null = 422） */
  onChange: (field: TuneField, next: number) => void;
  /** 「按模板当前值填回」：父组件拉一次模板当前值后回填并标记脏 */
  onFillBack: (field: TuneField) => void;
  fillingBack?: TuneField | null;
  /**
   * 按字段置灰「填回」。**难度必须用**：模板未评星时 `difficulty` 是 null，
   * "填回"没有任何值可填 —— 写 0 会被后端 `ge=1` 直接 422（这是正常点击可达的路径）。
   */
  fillBackDisabled?: Partial<Record<TuneField, boolean>>;
  /** 押金预览的日期基准（生成表单 = 目标日期；微调表单 = 实例归属日） */
  previewDate: string;
  disabled?: boolean;
}

const TaskTuneFields: React.FC<TaskTuneFieldsProps> = ({
  template,
  value,
  dirty,
  onChange,
  onFillBack,
  fillingBack,
  fillBackDisabled,
  previewDate,
  disabled,
}) => {
  const { t } = useTranslation();
  const [preview, setPreview] = useState<TaskDepositPreviewResponse | null>(null);
  const [previewFailed, setPreviewFailed] = useState(false);

  const fillBackDisabledFor = (field: TuneField): { disabled: boolean; hint: string } => {
    if (template.id === null) return { disabled: true, hint: t('tune.fillBackUnavailable') };
    if (fillBackDisabled?.[field]) return { disabled: true, hint: t('tune.fillBackNoTemplateValue') };
    return { disabled: false, hint: t('tune.fillBackHint') };
  };

  /**
   * 押金预览。⚠️ `value.difficulty` **刻意不进依赖**：
   * 难度不影响押金（D3），改星级不该触发重算 —— 这本身就是「难度影响 XP 倍率，
   * 不影响押金」这条口径在 UI 上的落实。只有押金输入与目标日期会重算。
   */
  useEffect(() => {
    if (disabled) return;
    let cancelled = false;
    api.tasks
      .previewDeposit({
        type: template.type,
        estimated_minutes: template.estimated_minutes ?? undefined,
        time_deposit: value.time_deposit,
        difficulty: value.difficulty ?? undefined,
        for_date: previewDate,
      })
      .then(result => {
        if (cancelled) return;
        setPreview(result);
        setPreviewFailed(false);
      })
      .catch(() => {
        if (!cancelled) setPreviewFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [template.type, template.estimated_minutes, value.time_deposit, previewDate, disabled]);

  const fillBackButton = (field: TuneField) => {
    const state = fillBackDisabledFor(field);
    return (
      <button
        type="button"
        onClick={() => onFillBack(field)}
        disabled={state.disabled || disabled || fillingBack === field}
        title={state.hint}
        className="text-[11px] font-bold text-sky-700 hover:text-sky-800 disabled:text-slate-300 disabled:cursor-not-allowed flex items-center gap-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600 rounded px-1"
      >
        <RefreshCw size={11} aria-hidden />
        {fillingBack === field ? t('common.loading') : t('tune.fillBack')}
      </button>
    );
  };

  const dirtyBadge = (field: TuneField) =>
    dirty[field] ? (
      <span className="text-[10px] font-bold bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">
        {t('tune.adjusted')}
      </span>
    ) : null;

  return (
    <div className="space-y-3" data-testid="task-tune-fields">
      {/* 难度 */}
      <div className="border border-slate-200 rounded-xl p-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-slate-700">{t('taskTemplate.difficulty')}</span>
            {dirtyBadge('difficulty')}
          </div>
          {fillBackButton('difficulty')}
        </div>
        <div
          role="radiogroup"
          aria-label={t('taskTemplate.difficulty')}
          className="flex gap-0.5 items-center mt-1"
        >
          {[1, 2, 3, 4, 5].map(star => {
            const active = value.difficulty !== null && star <= value.difficulty;
            return (
              <button
                key={star}
                type="button"
                role="radio"
                aria-checked={value.difficulty === star}
                tabIndex={value.difficulty === star ? 0 : -1}
                aria-label={t('taskTemplate.difficultyN', { n: star })}
                disabled={disabled}
                // 再点当前值不做取消：清空 = 传 null = 422（快照语义下没有"未覆盖"态）
                onClick={() => onChange('difficulty', Math.min(5, Math.max(1, star)))}
                className={`w-7 h-7 text-lg leading-none rounded transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600 ${
                  active ? 'text-amber-500' : 'text-slate-200 hover:text-slate-300'
                }`}
              >
                ★
              </button>
            );
          })}
          <span className="text-[11px] text-slate-400 ml-2">
            {/* 0 与 null 都不是有效星级（后端 ge=1）：一律显示「未评星」，避免 ★0 残留 */}
            {value.difficulty === null || value.difficulty < 1 ? t('tune.unrated') : `★${value.difficulty}`}
          </span>
        </div>
        {fillBackDisabledFor('difficulty').disabled && template.id !== null && (
          <p className="text-[11px] text-slate-400 mt-1">{t('tune.fillBackNoTemplateValue')}</p>
        )}
        <p className="text-[11px] text-slate-400 mt-1">{t('tmpl.difficultyHint')}</p>
      </div>

      {/* 时间币押金 */}
      <div className="border border-slate-200 rounded-xl p-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-slate-700">{t('tmpl.depositLabel')}</span>
            {dirtyBadge('time_deposit')}
          </div>
          {fillBackButton('time_deposit')}
        </div>
        <div className="flex items-center gap-2 mt-1">
          <Coins size={14} className="text-yellow-500" aria-hidden />
          <input
            type="number"
            min={0}
            value={value.time_deposit}
            disabled={disabled}
            // 空输入时 Number('') = 0 / 非法时 NaN：统一收敛为 0，避免把 NaN 写进表单值
            onChange={event => {
              const parsed = Number(event.target.value);
              onChange('time_deposit', Number.isFinite(parsed) ? Math.max(0, parsed) : 0);
            }}
            aria-label={t('tmpl.depositLabel')}
            className="w-24 border border-slate-200 rounded px-2 py-1 text-sm"
          />
          <span className="text-[11px] text-slate-400">{t('tune.depositFreeHint')}</span>
        </div>
        <div className="mt-2 text-[11px] bg-slate-50 border border-slate-200 rounded-lg p-2" aria-live="polite">
          {previewFailed ? (
            <span className="text-slate-400">{t('tmpl.depositFallback')}</span>
          ) : preview === null ? (
            <span className="text-slate-400 animate-pulse">{t('common.loading')}</span>
          ) : (
            <div className="space-y-0.5">
              <div className="text-slate-600 font-bold">
                {t('tmpl.depositPreview')}: {preview.time_deposit}
              </div>
              {/* 只显示后端给的口径：封顶比例是后端业务常量，不在前端复算，避免口径漂移 */}
              <div className="text-slate-400">
                {t('tune.quotaSimple', { allowance: preview.daily_allowance })}
                {' · '}
                {t('tune.previewDateNotice', { date: previewDate })}
              </div>
              {preview.capped_by_allowance && (
                <div className="text-amber-700 flex items-center gap-1">
                  <AlertTriangle size={11} aria-hidden /> {t('tmpl.cappedBadge')} · {t('tmpl.cappedHint')}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 经验值 */}
      <div className="border border-slate-200 rounded-xl p-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-slate-700">{t('common.xp')}</span>
            {dirtyBadge('xp_reward')}
          </div>
          {fillBackButton('xp_reward')}
        </div>
        <div className="flex items-center gap-2 mt-1">
          <input
            type="number"
            min={0}
            value={value.xp_reward}
            disabled={disabled}
            onChange={event => {
              const parsed = Number(event.target.value);
              onChange('xp_reward', Number.isFinite(parsed) ? Math.max(0, parsed) : 0);
            }}
            aria-label={t('common.xp')}
            className="w-24 border border-slate-200 rounded px-2 py-1 text-sm"
          />
        </div>
      </div>

      <p className="text-[11px] text-slate-400 flex items-start gap-1">
        <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
        <span>{t('tune.fillBackHint')}</span>
      </p>
    </div>
  );
};

export default TaskTuneFields;