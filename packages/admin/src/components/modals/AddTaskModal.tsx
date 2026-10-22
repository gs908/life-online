import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type {
  ContentMode,
  TaskCreate,
  TaskTemplateCreate,
  TaskTemplateRead,
  TaskTemplateUpdate,
  TaskType,
  TimedMode,
} from '../../services/api';
import { X, Plus, Info, AlertTriangle } from 'lucide-react';
import {
  DURATION_MAX,
  DURATION_MIN,
  DURATION_STEP,
  categoryOf,
  deadlineEarlierThanGenerate,
  describeTrigger,
  draftToTriggerPayload,
  makeTriggerDraft,
  triggerToDraft,
  validateTemplateForm,
  type TaskTemplateCategoryIntent,
  type TemplateFormErrors,
  type TriggerDraft,
} from '../taskTemplateUtils';

export type AddTaskSubmit =
  | { mode: 'instance'; task: TaskCreate }
  | { mode: 'template'; template: TaskTemplateCreate }
  | { mode: 'update'; templateId: string; patch: TaskTemplateUpdate };

interface AddTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** 统一提交出口：一次性→instance（POST /scn/task-instances）；其余→template（POST /scn/task-templates）；编辑→update（PATCH） */
  onSubmit: (action: AddTaskSubmit) => void;
  /** 来源赛季标签（契约 §6B）：有激活赛季则带上、没有则省略 —— 模板不绑赛季 */
  seasonId: string;
  childLevel: number;
  submitting?: boolean;
  /** 编辑模式：传入待改模板；提交走 PATCH（triggers 整组替换） */
  editingTemplate?: TaskTemplateRead | null;
  /** 新建默认类别：任务板「新建任务」= once（旧行为），模板管理「新建模板」= daily */
  defaultCategory?: TaskTemplateCategoryIntent;
}

/** UI 类别 → 模板 type（契约 §6A：一次性走实例路径，不落 type） */
const CATEGORY_TYPE: Record<Exclude<TaskTemplateCategoryIntent, 'once'>, TaskType> = {
  daily: 'DAILY',
  challenge: 'CHALLENGE',
  timed: 'TIMED',
};

/** 类别选择器四卡（Miss.D §2：radio group 语义 + 方向键切换） */
const CATEGORY_CARDS: Array<{
  key: TaskTemplateCategoryIntent;
  icon: string;
  descKey: string;
  accent: string;
}> = [
  { key: 'once', icon: '✨', descKey: 'taskTemplate.catOnceDesc', accent: 'text-violet-700' },
  { key: 'daily', icon: '🔁', descKey: 'taskTemplate.catDailyDesc', accent: 'text-sky-700' },
  { key: 'challenge', icon: '🏆', descKey: 'taskTemplate.catChallengeDesc', accent: 'text-amber-700' },
  { key: 'timed', icon: '⏱', descKey: 'taskTemplate.catTimedDesc', accent: 'text-rose-700' },
];

/** 分段控件（role=radiogroup，Miss.D §7 键盘可达） */
const Segmented: React.FC<{
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
  tone?: 'slate' | 'rose';
}> = ({ label, value, options, onChange, tone = 'slate' }) => {
  const handleKeyDown = (event: React.KeyboardEvent) => {
    const index = options.findIndex(option => option.value === value);
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      event.preventDefault();
      onChange(options[(index + 1) % options.length].value);
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      event.preventDefault();
      onChange(options[(index - 1 + options.length) % options.length].value);
    }
  };
  const activeCls = tone === 'rose' ? 'bg-rose-600 text-white border-rose-600' : 'bg-slate-900 text-white border-slate-900';
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1.5" onKeyDown={handleKeyDown}>
      {options.map(option => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(option.value)}
            className={`text-xs px-3 py-1.5 rounded-full border font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600 ${
              active ? activeCls : 'bg-white border-slate-200 text-slate-500 hover:border-slate-400'
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
};

/** 新建任务 / 编辑模板（DEV-35 块 A，Miss.D 设计规范 §3）：
 *  四类任务选择器 + 触发规则编辑器 + 时间窗编辑器；一次性走旧实例路径，其余建模板。 */
const AddTaskModal: React.FC<AddTaskModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  seasonId,
  submitting,
  editingTemplate,
  defaultCategory = 'once',
}) => {
  const { t } = useTranslation();
  const isEdit = Boolean(editingTemplate);

  const [category, setCategory] = useState<TaskTemplateCategoryIntent>(defaultCategory);
  const [newTaskTitle, setNewTaskTitle] = useState('');
  const [newTaskDesc, setNewTaskDesc] = useState('');
  const [newTaskXP, setNewTaskXP] = useState(50);
  /** null = 未评星（契约 difficulty 可空）；编辑态保留原值，避免 PATCH 把 null 静默写成 3 */
  const [difficulty, setDifficulty] = useState<number | null>(3);
  /** 任务要点（docs/15 R24）：模板只存与赛季无关的任务实质，作为 LLM 叙事的输入 */
  const [contentBrief, setContentBrief] = useState('');
  /** 叙事方式（docs/15 R24）：新口径下后端默认 LLM（生成时结合当季背景） */
  const [contentMode, setContentMode] = useState<ContentMode>('LLM');

  const [triggers, setTriggers] = useState<TriggerDraft[]>([makeTriggerDraft()]);
  const [timedMode, setTimedMode] = useState<TimedMode>('NONE');
  const [deadlineTime, setDeadlineTime] = useState('20:00');
  const [startTime, setStartTime] = useState('16:30');
  const [durationMinutes, setDurationMinutes] = useState(45);
  const [errors, setErrors] = useState<TemplateFormErrors | null>(null);

  // 打开时重置表单（创建失败时 App 保留弹窗与已填内容，成功后关闭并在此处复位）
  useEffect(() => {
    if (!isOpen) return;
    setErrors(null);
    if (editingTemplate) {
      setCategory(categoryOf(editingTemplate));
      setNewTaskTitle(editingTemplate.title);
      setNewTaskDesc(editingTemplate.description);
      setNewTaskXP(editingTemplate.xp_reward);
      setDifficulty(editingTemplate.difficulty); // null 保留 null（Mars S2）
      setContentBrief(editingTemplate.content_brief ?? '');
      setContentMode(editingTemplate.content_mode);
      // 编辑预填：规则为空（如一次性走实例路径产生的模板）保持为空，
      // 不注入默认草稿——否则保存时会静默给模板追加一条 DAILY 触发器
      setTriggers(editingTemplate.triggers.map(triggerToDraft));
      setTimedMode(editingTemplate.timed_mode);
      setDeadlineTime((editingTemplate.deadline_time ?? '20:00').slice(0, 5));
      setStartTime((editingTemplate.start_time ?? '16:30').slice(0, 5));
      setDurationMinutes(editingTemplate.duration_minutes ?? 45);
    } else {
      setCategory(defaultCategory);
      setNewTaskTitle('');
      setNewTaskDesc('');
      setNewTaskXP(50);
      setDifficulty(3);
      setContentBrief('');
      // 新口径：模板默认叙事方式为 LLM（生成任务时结合当季背景）——与后端默认值一致
      setContentMode('LLM');
      // Miss.D §2 默认触发：一次性无规则区；日常=DAILY、挑战=WEEKDAYS 周一、限时=DAILY
      setTriggers([
        defaultCategory === 'challenge'
          ? makeTriggerDraft({ kind: 'WEEKDAYS', weekdays: [0], generate_at: '08:00' })
          : makeTriggerDraft({ generate_at: '08:00' }),
      ]);
      // 限时类时间窗必选（Miss.D §2），默认 DEADLINE 20:00
      setTimedMode(defaultCategory === 'timed' ? 'DEADLINE' : 'NONE');
      setDeadlineTime('20:00');
      setStartTime('16:30');
      setDurationMinutes(45);
    }
  }, [isOpen, editingTemplate, defaultCategory]);

  // Esc 关闭
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  const showSoftWarning = useMemo(
    () =>
      deadlineEarlierThanGenerate({
        timed_mode: timedMode,
        deadline_time: deadlineTime,
        triggers,
      }),
    [timedMode, deadlineTime, triggers],
  );

  if (!isOpen) return null;

  const patchTrigger = (index: number, patch: Partial<TriggerDraft>) => {
    setTriggers(prev => prev.map((draft, i) => (i === index ? { ...draft, ...patch } : draft)));
  };

  // 说明：模板表单原有的「AI 生成」面板已整体迁到生成表单（GenerateTaskModal）——
// 它会带上**本赛季的 narrative_context**，属于"模板结合赛季背景生成内容"，
// 与新口径（模板只存与赛季无关的任务实质）冲突，故不在此处出现。

  // V3：切回 NONE 时清空三字段（对应后端「三者皆空」校验）
  const changeTimedMode = (mode: TimedMode) => {
    setTimedMode(mode);
    if (mode === 'NONE') {
      setDeadlineTime('');
      setStartTime('');
      setDurationMinutes(0);
    } else {
      setDeadlineTime(prev => prev || '20:00');
      setStartTime(prev => prev || '16:30');
      setDurationMinutes(prev => (prev > 0 ? prev : 45));
    }
  };

  const buildError = (): TemplateFormErrors | null =>
    validateTemplateForm({
      title: newTaskTitle,
      xp: newTaskXP,
      timed_mode: timedMode,
      deadline_time: deadlineTime,
      start_time: startTime,
      duration_minutes: durationMinutes,
      triggers: category === 'once' ? [] : triggers,
    });

  const handleSubmit = () => {
    // 模板不绑赛季（契约 §6B）：无激活赛季也能建模板，故不再有赛季闸门
    const formErrors = buildError();
    setErrors(formErrors);
    if (formErrors) return;

    const timedPayload =
      timedMode === 'DEADLINE'
        ? { timed_mode: timedMode, deadline_time: deadlineTime }
        : timedMode === 'DURATION'
          ? { timed_mode: timedMode, start_time: startTime, duration_minutes: durationMinutes }
          : { timed_mode: 'NONE' as const, deadline_time: null, start_time: null, duration_minutes: null };

    // 来源赛季标签（契约 §6B）：有激活赛季就带上，没有则省略（模板不绑赛季）
    const seasonTag = seasonId ? { season_id: seasonId } : {};

    if (isEdit && editingTemplate) {
      const patch: TaskTemplateUpdate = {
        title: newTaskTitle.trim(),
        description: newTaskDesc,
        // ⚠️ 不提交 lore_snippet：模板 lore 已收窄为"中性兜底叙事"，表单不再提供输入，
        // 不传 = PATCH 保持不变（避免把既有值静默清空）
        xp_reward: Math.max(0, newTaskXP),
        // 显式传 null = 保持「未评星」，与 PATCH「未提供的字段不变」语义对齐（Mars S2）
        difficulty,
        content_brief: contentBrief.trim() || null,
        content_mode: contentMode,
        ...timedPayload,
        // triggers 整组替换（契约 §6A）；一次性类别 = 清空周期规则
        triggers: category === 'once' ? [] : triggers.map(draftToTriggerPayload),
      };
      onSubmit({ mode: 'update', templateId: editingTemplate.id, patch });
      return;
    }

    const base = {
      title: newTaskTitle.trim(),
      description: newTaskDesc,
      xp_reward: Math.max(0, newTaskXP),
      content_brief: contentBrief.trim() || undefined,
      content_mode: contentMode,
      reminder_message: t('addTask.defaultReminder'),
      reminder_minutes_before: 15,
    };

    if (category === 'once') {
      // 一次性：POST /scn/task-instances（旧实例路径，立即出现、不重复生成）
      const task: TaskCreate = {
        ...base,
        ...seasonTag,
        type: 'DAILY',
      };
      onSubmit({ mode: 'instance', task });
      return;
    }

    const template: TaskTemplateCreate = {
      ...base,
      ...seasonTag,
      type: CATEGORY_TYPE[category],
      // 未评星不写字段（新建时 difficulty 可空，避免把 null 固化成默认值）
      ...(difficulty !== null ? { difficulty } : {}),
      ...timedPayload,
      triggers: triggers.map(draftToTriggerPayload),
    };
    onSubmit({ mode: 'template', template });
  };

  const submitLabel = isEdit
    ? t('taskTemplate.saveChanges')
    : category === 'once'
      ? t('addTask.postQuest')
      : t('taskTemplate.createTemplate');

  const triggerErrorOf = (index: number) => errors?.triggers?.[index];

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div
        className="bg-white rounded-2xl w-full max-w-xl shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200"
        role="dialog"
        aria-modal="true"
        aria-label={isEdit ? t('taskTemplate.editTitle') : t('addTask.title')}
      >
        <div className="bg-slate-900 text-white p-4 flex justify-between items-center">
          <h3 className="font-bold text-lg flex items-center gap-2">
            <Plus size={20} /> {isEdit ? t('taskTemplate.editTitle') : t('addTask.title')}
          </h3>
          <button onClick={onClose} aria-label={t('common.close')}><X /></button>
        </div>
        <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          {/* AI Generator（保留） */}
          {/* 叙事方式 + 任务要点（docs/15 R24）：模板只存与赛季无关的任务实质。
              原「AI 生成」面板已迁到生成表单 —— 它会带入赛季背景，不属于模板层。 */}
          <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-2">
            <div>
              <div className="text-xs font-bold text-slate-600 mb-1.5">{t('addTask.narrativeMode')}</div>
              <div role="radiogroup" aria-label={t('addTask.narrativeMode')} className="flex gap-1.5">
                {(['LLM', 'STATIC'] as const).map(mode => (
                  <button
                    key={mode}
                    type="button"
                    role="radio"
                    aria-checked={contentMode === mode}
                    tabIndex={contentMode === mode ? 0 : -1}
                    onClick={() => setContentMode(mode)}
                    className={`text-xs px-3 py-1.5 rounded-full border font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600 ${
                      contentMode === mode
                        ? 'bg-slate-900 text-white border-slate-900'
                        : 'bg-white border-slate-200 text-slate-500 hover:border-slate-400'
                    }`}
                  >
                    {t(`addTask.narrativeModeValue.${mode}`)}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-slate-400 mt-1">
                {contentMode === 'LLM' ? t('addTask.narrativeModeLlmHint') : t('addTask.narrativeModeStaticHint')}
              </p>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-bold text-slate-600 block" htmlFor="add-task-brief">
                {t('addTask.contentBrief')}
              </label>
              <textarea
                id="add-task-brief"
                value={contentBrief}
                onChange={event => setContentBrief(event.target.value)}
                placeholder={t('addTask.contentBriefPlaceholder')}
                maxLength={500}
                className="w-full border border-slate-200 rounded-lg p-2 h-16 text-sm"
              />
              <p className="text-[11px] text-slate-400">{t('addTask.contentBriefHint')}</p>
            </div>
          </div>

          {/* 任务类型四卡（Miss.D §2；radio group 语义，方向键切换） */}
          <div>
            <div className="text-xs font-bold text-slate-600 mb-1.5">{t('taskTemplate.taskCategory')}</div>
            <div
              role="radiogroup"
              aria-label={t('taskTemplate.taskCategory')}
              className="grid grid-cols-4 gap-2"
              onKeyDown={(event) => {
                const keys = CATEGORY_CARDS.map(card => card.key);
                const index = keys.indexOf(category);
                if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
                  event.preventDefault();
                  setCategory(keys[(index + 1) % keys.length]);
                } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
                  event.preventDefault();
                  setCategory(keys[(index - 1 + keys.length) % keys.length]);
                }
              }}
            >
              {CATEGORY_CARDS.map(card => {
                const active = card.key === category;
                return (
                  <button
                    key={card.key}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    tabIndex={active ? 0 : -1}
                    onClick={() => setCategory(card.key)}
                    className={`rounded-xl px-2 py-2.5 text-center border-[1.5px] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600 ${
                      card.key === 'timed'
                        ? active
                          ? 'border-rose-500 bg-rose-50 shadow-[0_0_0_3px_rgba(244,63,94,0.15)]'
                          : 'border-slate-200 bg-slate-50 hover:border-slate-300'
                        : active
                          ? 'border-slate-800 bg-slate-100 shadow-[0_0_0_3px_rgba(15,23,42,0.1)]'
                          : 'border-slate-200 bg-slate-50 hover:border-slate-300'
                    }`}
                  >
                    <div className="text-xl leading-none mb-1" aria-hidden>{card.icon}</div>
                    <div className={`text-xs font-bold ${active ? card.accent : 'text-slate-500'}`}>
                      {t(`taskTemplate.cat.${card.key}`)}
                    </div>
                    <div className="text-[10px] text-slate-400 mt-0.5">{t(card.descKey)}</div>
                  </button>
                );
              })}
            </div>
            {category === 'timed' && (
              <p className="text-[11px] text-rose-600 mt-1.5" aria-live="polite">
                {t('taskTemplate.catTimedHint')}
              </p>
            )}
          </div>

          {/* 标题 / XP / 难度 */}
          <div className="flex gap-3">
            <div className="space-y-1.5 flex-1">
              <label className="text-sm font-bold text-slate-700" htmlFor="add-task-title">{t('addTask.questTitle')}</label>
              <input
                id="add-task-title"
                className={`w-full border p-2 rounded ${errors?.title ? 'border-red-400' : 'border-slate-200'}`}
                value={newTaskTitle}
                onChange={e => setNewTaskTitle(e.target.value)}
                placeholder={t('addTask.questNamePlaceholder')}
              />
            </div>
            <div className="space-y-1.5 w-20">
              <label className="text-sm font-bold text-slate-700" htmlFor="add-task-xp">{t('common.xp')}</label>
              <input
                id="add-task-xp"
                type="number"
                min={0}
                className={`w-full border p-2 rounded ${errors?.xp ? 'border-red-400' : 'border-slate-200'}`}
                value={newTaskXP}
                onChange={e => setNewTaskXP(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1.5">
              <div className="text-sm font-bold text-slate-700" id="add-task-difficulty-label">{t('taskTemplate.difficulty')}</div>
              <div role="radiogroup" aria-labelledby="add-task-difficulty-label" className="flex gap-0.5 h-[38px] items-center">
                {[1, 2, 3, 4, 5].map(star => {
                  const active = difficulty !== null && star <= difficulty;
                  return (
                    <button
                      key={star}
                      type="button"
                      role="radio"
                      aria-checked={difficulty !== null && star === difficulty}
                      tabIndex={difficulty === null ? (star === 3 ? 0 : -1) : (star === difficulty ? 0 : -1)}
                      aria-label={t('taskTemplate.difficultyN', { n: star })}
                      // 再点当前值取消评星（回 null）
                      onClick={() => setDifficulty(prev => (prev === star ? null : star))}
                      className={`w-7 h-7 text-lg leading-none transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600 rounded ${
                        active ? 'text-amber-500' : 'text-slate-200 hover:text-slate-300'
                      }`}
                    >
                      ★
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
          {(errors?.title || errors?.xp) && (
            <p className="text-xs text-red-600" aria-live="polite">
              {errors?.title ? t('taskTemplate.errTitleRequired') : t('taskTemplate.errXpInvalid')}
            </p>
          )}

          <div className="space-y-1.5">
            <label className="text-sm font-bold text-slate-700">{t('addTask.descriptionLore')}</label>
            <textarea className="w-full border border-slate-200 p-2 rounded h-20" value={newTaskDesc} onChange={e => setNewTaskDesc(e.target.value)} placeholder={t('addTask.descriptionPlaceholder')} />
            {/* 模板 lore 已收窄为「与赛季无关的中性兜底叙事」：不再提供输入，
                编辑态若既有值带赛季色彩，仅作提示（Shark §二-4） */}
            {isEdit && editingTemplate?.lore_snippet && (
              <p className="text-[11px] text-slate-400 bg-slate-50 border border-slate-200 rounded-lg p-2">
                {t('addTask.loreNeutralHint')}
              </p>
            )}
          </div>

          {/* 一次性：隐藏触发规则区，显示提示条（Miss.D §3） */}
          {category === 'once' ? (
            <div className="flex items-center gap-2 p-3 bg-violet-50 border border-violet-100 rounded-lg">
              <Info size={14} className="text-violet-500 shrink-0" />
              <span className="text-xs text-violet-700">{t('taskTemplate.onceInstantHint')}</span>
            </div>
          ) : (
            <div className="border border-slate-200 rounded-xl p-3">
              <div className="flex justify-between items-center mb-2">
                <div className="text-xs font-bold text-slate-600">
                  🕘 {t('taskTemplate.triggerSection')} <span className="text-slate-400 font-normal">{t('taskTemplate.triggerSectionSub')}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setTriggers(prev => [...prev, makeTriggerDraft({ generate_at: triggers[0]?.generate_at ?? '08:00' })])}
                  className="text-[11px] font-bold text-sky-700 hover:text-sky-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600 rounded px-1"
                >
                  ＋ {t('taskTemplate.addRule')}
                </button>
              </div>

              <div className="space-y-3">
                {triggers.length === 0 && (
                  <p className="text-[11px] text-slate-400">{t('taskTemplate.noTriggersEdit')}</p>
                )}
                {triggers.map((draft, index) => (
                  <div key={index} className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 space-y-2">
                    <div className="flex justify-between items-center gap-2">
                      <Segmented
                        label={t('taskTemplate.triggerKindLabel', { n: index + 1 })}
                        value={draft.kind}
                        options={(draft.kind === 'ONCE'
                          ? [
                              { value: 'DAILY', label: t('taskTemplate.triggerDaily') },
                              { value: 'WEEKDAYS', label: t('taskTemplate.triggerWeekdays') },
                              { value: 'MONTHLY', label: t('taskTemplate.triggerMonthly') },
                              { value: 'CRON', label: t('taskTemplate.triggerCron') },
                              { value: 'ONCE', label: t('taskTemplate.triggerOnce') },
                            ]
                          : [
                              { value: 'DAILY', label: t('taskTemplate.triggerDaily') },
                              { value: 'WEEKDAYS', label: t('taskTemplate.triggerWeekdays') },
                              { value: 'MONTHLY', label: t('taskTemplate.triggerMonthly') },
                              { value: 'CRON', label: t('taskTemplate.triggerCron') },
                            ]
                        ).filter(option => option.value !== 'ONCE' || draft.kind === 'ONCE')}
                        onChange={(value) => patchTrigger(index, { kind: value as TriggerDraft['kind'] })}
                      />
                      {triggers.length > 1 && (
                        <button
                          type="button"
                          onClick={() => setTriggers(prev => prev.filter((_, i) => i !== index))}
                          className="text-[11px] text-slate-400 hover:text-red-600 shrink-0"
                          aria-label={t('taskTemplate.removeRule', { n: index + 1 })}
                        >
                          <X size={14} />
                        </button>
                      )}
                    </div>

                    {draft.kind === 'WEEKDAYS' && (
                      <div>
                        <div className="flex gap-1" role="group" aria-label={t('taskTemplate.triggerWeekdays')}>
                          {[0, 1, 2, 3, 4, 5, 6].map(weekday => {
                            const selected = draft.weekdays.includes(weekday);
                            return (
                              <button
                                key={weekday}
                                type="button"
                                aria-pressed={selected}
                                onClick={() =>
                                  patchTrigger(index, {
                                    weekdays: selected
                                      ? draft.weekdays.filter(w => w !== weekday)
                                      : [...draft.weekdays, weekday],
                                  })
                                }
                                className={`w-11 h-11 rounded-lg text-xs font-bold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600 ${
                                  selected ? 'bg-sky-600 text-white' : 'bg-white border border-slate-200 text-slate-500 hover:border-slate-400'
                                }`}
                              >
                                {t(`taskTemplate.weekday.${weekday}`)}
                              </button>
                            );
                          })}
                        </div>
                        {triggerErrorOf(index) === 'V4' && (
                          <p className="text-[11px] text-red-600 mt-1" aria-live="polite">{t('taskTemplate.errWeekdaysRequired')}</p>
                        )}
                      </div>
                    )}

                    {draft.kind === 'MONTHLY' && (
                      <div>
                        <div className="flex items-center gap-2 text-xs text-slate-600">
                          <span>{t('taskTemplate.dayOfMonthLabel')}</span>
                          <input
                            type="number"
                            min={1}
                            max={31}
                            value={draft.day_of_month}
                            onChange={e => patchTrigger(index, { day_of_month: Number(e.target.value) })}
                            className={`w-16 border p-1.5 rounded ${triggerErrorOf(index) === 'V5' ? 'border-red-400' : 'border-slate-200'}`}
                            aria-label={t('taskTemplate.dayOfMonthLabel')}
                          />
                        </div>
                        <p className="text-[10px] text-slate-400 mt-1">{t('taskTemplate.dayOfMonthHelper')}</p>
                        {triggerErrorOf(index) === 'V5' && (
                          <p className="text-[11px] text-red-600 mt-1" aria-live="polite">{t('taskTemplate.errDayOfMonth')}</p>
                        )}
                      </div>
                    )}

                    {draft.kind === 'CRON' && (
                      <div>
                        <input
                          type="text"
                          value={draft.cron_expr}
                          onChange={e => patchTrigger(index, { cron_expr: e.target.value })}
                          placeholder="0 8 * * 1-5"
                          className={`w-full border p-2 rounded font-mono text-sm ${triggerErrorOf(index) === 'V6' ? 'border-red-400' : 'border-slate-200'}`}
                          aria-label={t('taskTemplate.cronLabel')}
                        />
                        <p className="text-[10px] text-slate-400 mt-1">{t('taskTemplate.cronHelper')}</p>
                        {triggerErrorOf(index) === 'V6' && (
                          <p className="text-[11px] text-red-600 mt-1" aria-live="polite">{t('taskTemplate.errCron')}</p>
                        )}
                      </div>
                    )}

                    {/* 通用字段：生成时间 + 生效区间（Miss.D §3.1） */}
                    <div className="flex flex-wrap gap-2 text-xs text-slate-600">
                      <div>
                        <div className="text-[10px] text-slate-400 mb-0.5">{t('taskTemplate.generateAt')}</div>
                        <input
                          type="time"
                          value={draft.generate_at}
                          onChange={e => patchTrigger(index, { generate_at: e.target.value })}
                          className="border border-slate-200 rounded px-2 py-1"
                          aria-label={t('taskTemplate.generateAt')}
                        />
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-400 mb-0.5">{t('taskTemplate.startsOn')}</div>
                        <input
                          type="date"
                          value={draft.starts_on}
                          onChange={e => patchTrigger(index, { starts_on: e.target.value })}
                          className="border border-slate-200 rounded px-2 py-1"
                          aria-label={t('taskTemplate.startsOn')}
                        />
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-400 mb-0.5">{t('taskTemplate.endsOn')}</div>
                        <input
                          type="date"
                          value={draft.ends_on}
                          onChange={e => patchTrigger(index, { ends_on: e.target.value })}
                          className={`border rounded px-2 py-1 ${errors?.range ? 'border-red-400' : 'border-slate-200'}`}
                          aria-label={t('taskTemplate.endsOn')}
                        />
                      </div>
                    </div>
                    {errors?.range && (
                      <p className="text-[11px] text-red-600" aria-live="polite">{t('taskTemplate.errRange')}</p>
                    )}
                  </div>
                ))}
              </div>

              {/* 人话预览（实时，Miss.D §3.1） */}
              <p className="text-[11px] text-slate-500 mt-2">
                📅{' '}
                {t('taskTemplate.previewLine', {
                  rules: triggers.map(draft => describeTrigger(draftToTriggerPayload(draft), t)).join(t('taskTemplate.listJoiner')),
                })}
                {category === 'timed' ? ' ' + t('taskTemplate.previewTimedSuffix') : ''}
                {triggers.length > 1 ? ' ' + t('taskTemplate.previewDedupe') : ''}
              </p>
            </div>
          )}

          {/* 时间窗编辑器（Miss.D §3.2；限时类选中时 rose 高亮） */}
          {category !== 'once' && (
            <div className={`border rounded-xl p-3 ${timedMode !== 'NONE' ? 'border-rose-200 bg-rose-50' : 'border-slate-200 bg-white'}`}>
              <div className="text-xs font-bold text-slate-600 mb-2">
                ⏱ {t('taskTemplate.windowSection')} <span className="text-slate-400 font-normal">{t('taskTemplate.windowSectionSub')}</span>
              </div>
              <Segmented
                label={t('taskTemplate.windowSection')}
                value={timedMode}
                tone="rose"
                options={[
                  { value: 'NONE', label: t('taskTemplate.windowNone') },
                  { value: 'DEADLINE', label: t('taskTemplate.windowDeadline') },
                  { value: 'DURATION', label: t('taskTemplate.windowDuration') },
                ]}
                onChange={(value) => changeTimedMode(value as TimedMode)}
              />
              {timedMode === 'DEADLINE' && (
                <div className="mt-2 flex items-center gap-2 text-sm text-slate-600">
                  <span>{t('taskTemplate.windowDeadlinePrefix')}</span>
                  <input
                    type="time"
                    value={deadlineTime}
                    onChange={e => setDeadlineTime(e.target.value)}
                    className={`border rounded px-2 py-1 ${errors?.timed === 'V1' ? 'border-red-400' : 'border-rose-200 bg-white'}`}
                    aria-label={t('taskTemplate.deadlineTimeLabel')}
                  />
                  <span>{t('taskTemplate.windowDeadlineSuffix')}</span>
                </div>
              )}
              {timedMode === 'DURATION' && (
                <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-slate-600">
                  <span>{t('taskTemplate.windowDurationFrom')}</span>
                  <input
                    type="time"
                    value={startTime}
                    onChange={e => setStartTime(e.target.value)}
                    className={`border rounded px-2 py-1 ${errors?.timed === 'V2' ? 'border-red-400' : 'border-rose-200 bg-white'}`}
                    aria-label={t('taskTemplate.startTimeLabel')}
                  />
                  <span>{t('taskTemplate.windowDurationFor')}</span>
                  <input
                    type="number"
                    min={DURATION_MIN}
                    max={DURATION_MAX}
                    step={DURATION_STEP}
                    value={durationMinutes}
                    onChange={e => setDurationMinutes(Number(e.target.value))}
                    className={`w-20 border rounded px-2 py-1 ${errors?.timed === 'V2' ? 'border-red-400' : 'border-rose-200 bg-white'}`}
                    aria-label={t('taskTemplate.durationLabel')}
                  />
                  <span>{t('taskTemplate.windowDurationMinutes')}</span>
                </div>
              )}
              {errors?.timed && (
                <p className="text-[11px] text-red-600 mt-1.5" aria-live="polite">
                  {errors.timed === 'V1' ? t('taskTemplate.errDeadlineRequired') : t('taskTemplate.errDurationInvalid')}
                </p>
              )}
              {showSoftWarning && !errors?.timed && (
                <p className="text-[11px] text-amber-600 mt-1.5 flex items-center gap-1" aria-live="polite">
                  <AlertTriangle size={12} /> {t('taskTemplate.warnDeadlineEarly')}
                </p>
              )}
            </div>
          )}
        </div>

        {/* 页脚：左侧 helper + 按钮（Miss.D §3） */}
        <div className="p-4 bg-slate-50 flex justify-between items-center gap-2 border-t">
          <p className="text-[11px] text-slate-400">
            {category === 'once' ? t('taskTemplate.footerOnce') : t('taskTemplate.footerTemplate')}
          </p>
          <div className="flex gap-2 shrink-0">
            <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold hover:bg-slate-200 rounded">{t('common.cancel')}</button>
            <button
              onClick={handleSubmit}
              disabled={submitting || !newTaskTitle.trim()}
              className="px-4 py-2 bg-green-600 text-white font-bold rounded hover:bg-green-700 shadow-md transform active:scale-95 disabled:opacity-50"
            >
              {submitting ? t('common.loading') : submitLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AddTaskModal;
