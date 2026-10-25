import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type {
  ContentMode,
  TaskCreate,
  TaskGenerateRequest,
  TaskGenerateResult,
  TaskTemplateCreate,
  TaskTemplateRead,
  TaskTemplateUpdate,
  TaskType,
  TimedMode,
} from '../../services/api';
import { api, ApiError } from '../../services/api';
import { X, Plus, Info, AlertTriangle, Sparkles, CalendarClock } from 'lucide-react';
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
import TaskTuneFields, { type TuneField, type TuneValues } from '../TaskTuneFields';
import { TARGET_DATE_MAX_AHEAD_DAYS, addDays, localToday } from '../../utils/date';

export type AddTaskSubmit =
  | { mode: 'instance'; task: TaskCreate }
  | { mode: 'template'; template: TaskTemplateCreate }
  | { mode: 'update'; templateId: string; patch: TaskTemplateUpdate };

/** 弹窗用途（DEV-58）：
 *  - `createTemplate`：任务模板管理 tab 的「新建模板 / 编辑」——原行为不变；
 *  - `createTask`：任务板「创建新任务」——顶部「选择模板」下拉分两支：
 *    未选模板 → 一次性临时任务（`ephemeral: true`，不落模板）；
 *    选了模板 → 目标日期 + 三项微调 → 生成实例。 */
export type AddTaskPurpose = 'createTask' | 'createTemplate';

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
  /** 弹窗用途（DEV-58）；缺省 `createTemplate` 保证模板管理 tab 行为不变 */
  purpose?: AddTaskPurpose;
  /** `createTask` 且从模板行「生成」进入时预选的模板（分支 A 直达） */
  initialTemplate?: TaskTemplateRead | null;
  /** 创建模板成功后触发生成（新口径：新建模板后直接选日生成，替代独立的 GenerateTaskModal） */
  onSubmitGenerated?: (result: TaskGenerateResult) => void;
  /** 给生成步骤的人话 toast（失败/命中既有/排期到未来等） */
  onToast?: (title: string, msg: string) => void;
  /** 家庭本地时区的今天，YYYY-MM-DD */
  today?: string;
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

const EMPTY_VALUES: TuneValues = { difficulty: null, time_deposit: 0, xp_reward: 0 };
const EMPTY_DIRTY: Record<TuneField, boolean> = {
  difficulty: false,
  time_deposit: false,
  xp_reward: false,
};

/** 新建任务 / 编辑模板（DEV-35 块 A，Miss.D 设计规范 §3）：
 *  四类任务选择器 + 触发规则编辑器 + 时间窗编辑器；一次性走旧实例路径，其余建模板。
 *  新建非一次性模板提交后进入「选日期 + 微调」生成步骤（DEV-51）。 */
const AddTaskModal: React.FC<AddTaskModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  seasonId,
  submitting,
  editingTemplate,
  defaultCategory = 'once',
  purpose = 'createTemplate',
  initialTemplate = null,
  onSubmitGenerated,
  onToast,
  today: propToday,
}) => {
  const { t } = useTranslation();
  const isEdit = Boolean(editingTemplate);
  const isCreateTask = purpose === 'createTask';
  const today = useMemo(() => propToday ?? localToday(), [propToday]);
  const maxDate = useMemo(() => addDays(today, TARGET_DATE_MAX_AHEAD_DAYS), [today]);

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

  // 创建模板后进入生成步骤的本地状态
  const [createdTemplateId, setCreatedTemplateId] = useState<string | null>(null);
  /** 从任务板入口选模板（与 GenerateTaskModal 对齐）；已定模板时不展示下拉 */
  const [templates, setTemplates] = useState<TaskTemplateRead[] | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('');
  /** `createTask` 本次打开内用户是否动过「选择模板」下拉；没动过则沿用模板行预选（P2） */
  const [pickerTouched, setPickerTouched] = useState(false);
  const [targetDate, setTargetDate] = useState<string>(today);
  const [tuneValues, setTuneValues] = useState<TuneValues>(EMPTY_VALUES);
  const [tuneDirty, setTuneDirty] = useState<Record<TuneField, boolean>>(EMPTY_DIRTY);
  const [tuneFillingBack, setTuneFillingBack] = useState<TuneField | null>(null);
  const [dateHasInstance, setDateHasInstance] = useState<boolean | null>(null);
  const [generateResult, setGenerateResult] = useState<TaskGenerateResult | null>(null);
  const [sentOverrides, setSentOverrides] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  // 模板行「生成」预选（DEV-58 P2）：用户本次打开未动过下拉时以传入模板为准。
  // 在渲染期直接派生（而非等 effect 回填），避免打开瞬间先闪一下「未选模板」支。
  const presetTemplate = !pickerTouched && isCreateTask ? initialTemplate : null;
  /** `createTask` 当前生效的模板：模板行预选优先，其次下拉选中项 */
  const activeTemplate =
    presetTemplate ?? templates?.find(item => item.id === selectedTemplateId) ?? null;
  /** 下拉当前值：预选时显示预选模板，否则显示用户选择 */
  const pickerValue = presetTemplate?.id ?? selectedTemplateId;

  // 打开时重置表单（创建失败时 App 保留弹窗与已填内容，成功后关闭并在此处复位）
  useEffect(() => {
    if (!isOpen) return;
    setErrors(null);
    setFormError(null);
    setGenerateResult(null);
    setSentOverrides(false);
    setDateHasInstance(null);
    setTuneFillingBack(null);
    setTargetDate(today);
    setTuneValues(EMPTY_VALUES);
    setTuneDirty(EMPTY_DIRTY);
    setCreatedTemplateId(null);
    setTemplates(null);
    setPickerTouched(false);
    setSelectedTemplateId('');
    if (isCreateTask && initialTemplate) {
      // 模板行「生成」直达分支 A：三项微调预填该模板当前值（dirty 保持 false）
      setTuneValues({
        difficulty: initialTemplate.difficulty,
        time_deposit: initialTemplate.time_deposit,
        xp_reward: initialTemplate.xp_reward,
      });
      setTuneDirty(EMPTY_DIRTY);
    }
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
      // createTask 的「未选模板」支是纯一次性任务，没有类别选择，固定 once
      setCategory(isCreateTask ? 'once' : defaultCategory);
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
  }, [isOpen, editingTemplate, defaultCategory, isCreateTask, initialTemplate, today]);

  // 任务板入口（未定模板）：打开弹窗时拉一次可用模板列表；已定模板或编辑态不走
  useEffect(() => {
    if (!isOpen || createdTemplateId || editingTemplate) return;
    let cancelled = false;
    api.taskTemplates
      .listTemplates()
      .then(items => {
        if (cancelled) return;
        // 启用中、且不是 CHAIN 第 2..N 步（与 TaskTemplateManager 行内按钮口径一致）
        setTemplates(
          items.filter(item => item.is_active && !(item.type === 'CHAIN' && item.chain_order > 1)),
        );
      })
      .catch(() => {
        if (!cancelled) setTemplates([]);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, createdTemplateId, editingTemplate]);

  // 进入生成步骤后预检：该模板在目标日期是否已有实例（中性提示用）
  useEffect(() => {
    const tmplId = createdTemplateId ?? presetTemplate?.id ?? selectedTemplateId;
    if (!isOpen || !tmplId || !targetDate) return;
    let cancelled = false;
    setDateHasInstance(null);
    api.tasks
      .listTasks({ template_id: tmplId, page_size: 200 })
      .then(page => {
        if (!cancelled) {
          setDateHasInstance(page.items.some(task => task.generated_for_date === targetDate));
        }
      })
      .catch(() => {
        if (!cancelled) setDateHasInstance(null);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, createdTemplateId, presetTemplate, selectedTemplateId, targetDate]);

  // Esc 关闭（模板编辑与生成步骤都要响应）
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

  // 新建非 once 模板提交：先建模板，再进入生成步骤
  const handleSubmitTemplate = async (): Promise<void> => {
    if (isEdit) return; // 编辑走 handleSubmit（不变）
    if (category === 'once') return; // once 走原有 instance 路径
    const formErrors = buildError();
    setErrors(formErrors);
    if (formErrors) return;

    const timedPayload =
      timedMode === 'DEADLINE'
        ? { timed_mode: timedMode, deadline_time: deadlineTime }
        : timedMode === 'DURATION'
          ? { timed_mode: timedMode, start_time: startTime, duration_minutes: durationMinutes }
          : { timed_mode: 'NONE' as const, deadline_time: null, start_time: null, duration_minutes: null };

    const seasonTag = seasonId ? { season_id: seasonId } : {};
    const template: TaskTemplateCreate = {
      title: newTaskTitle.trim(),
      description: newTaskDesc,
      xp_reward: Math.max(0, newTaskXP),
      content_brief: contentBrief.trim() || undefined,
      content_mode: contentMode,
      reminder_message: t('addTask.defaultReminder'),
      reminder_minutes_before: 15,
      ...seasonTag,
      type: CATEGORY_TYPE[category],
      ...(difficulty !== null ? { difficulty } : {}),
      ...timedPayload,
      triggers: triggers.map(draftToTriggerPayload),
    };
    try {
      const created = await api.taskTemplates.createTemplate(template);
      setCreatedTemplateId(created.id);
      // 预填三项默认值（来自刚创建的模板），dirty 保持 false
      setTuneValues({
        difficulty: created.difficulty,
        time_deposit: created.time_deposit,
        xp_reward: created.xp_reward,
      });
      setTuneDirty(EMPTY_DIRTY);
    } catch (error) {
      showApiError(error, t('toast.templateSaveFailedTitle'));
    }
  };

  const dateError = useMemo<'min' | 'max' | null>(() => {
    if (!targetDate) return 'min';
    if (targetDate < today) return 'min';
    if (targetDate > maxDate) return 'max';
    return null;
  }, [targetDate, today, maxDate]);

  const changeField = (field: TuneField, next: number) => {
    setTuneValues(prev => ({ ...prev, [field]: next }));
    setTuneDirty(prev => ({ ...prev, [field]: true }));
  };

  const fillBack = async (field: TuneField) => {
    const templateId = createdTemplateId ?? presetTemplate?.id ?? selectedTemplateId;
    if (!templateId) return;
    setTuneFillingBack(field);
    try {
      const fresh = await api.taskTemplates.getTemplate(templateId);
      if (field === 'difficulty') {
        if (fresh.difficulty === null || fresh.difficulty < 1) {
          onToast?.(t('toast.actionFailedTitle'), t('tune.fillBackNoTemplateValue'));
          return;
        }
        setTuneValues(prev => ({ ...prev, difficulty: fresh.difficulty as number }));
      } else if (field === 'time_deposit') {
        setTuneValues(prev => ({ ...prev, time_deposit: fresh.time_deposit }));
      } else {
        setTuneValues(prev => ({ ...prev, xp_reward: fresh.xp_reward }));
      }
      setTuneDirty(prev => ({ ...prev, [field]: true }));
    } catch (error) {
      onToast?.(t('toast.actionFailedTitle'), error instanceof ApiError ? error.message : t('tune.fillBackFailed'));
    } finally {
      setTuneFillingBack(null);
    }
  };

  const handleGenerateSubmit = async () => {
    if (dateError) return;
    // 已选模板路径：用下拉选中的模板（任务板入口场景）；否则走新建模板路径（从模板管理进入场景）
    const templateId = createdTemplateId ?? presetTemplate?.id ?? selectedTemplateId;
    if (!templateId || dateError) return;
    setGenerateError(null);
    setGenerating(true);
    const body: TaskGenerateRequest = { target_date: targetDate };
    if (tuneDirty.difficulty && tuneValues.difficulty !== null && tuneValues.difficulty >= 1) {
      body.difficulty = tuneValues.difficulty;
    }
    if (tuneDirty.time_deposit) body.time_deposit = tuneValues.time_deposit;
    if (tuneDirty.xp_reward) body.xp_reward = tuneValues.xp_reward;
    setSentOverrides(Object.keys(body).some(key => key !== 'target_date'));
    try {
      const generated = await api.taskTemplates.generateTemplate(templateId, body);
      setGenerateResult(generated);
      onSubmitGenerated?.(generated);
    } catch (error) {
      setGenerateError(error instanceof ApiError ? error.message : t('generateTask.failed'));
    } finally {
      setGenerating(false);
    }
  };

  const showApiError = (error: unknown, title: string) => {
    if (error instanceof ApiError) {
      onToast?.(title, error.message);
    } else {
      onToast?.(title, t('toast.actionFailedMsg'));
    }
  };

  /** 「创建新任务」未选模板支：一次性临时任务（`ephemeral: true`，只建实例、不落模板）。 */
  const handleSubmitCreateTask = () => {
    const formErrors = buildError();
    setErrors(formErrors);
    if (formErrors) return;
    const seasonTag = seasonId ? { season_id: seasonId } : {};
    const task: TaskCreate = {
      title: newTaskTitle.trim(),
      description: newTaskDesc,
      xp_reward: Math.max(0, newTaskXP),
      content_brief: contentBrief.trim() || undefined,
      content_mode: contentMode,
      reminder_message: t('addTask.defaultReminder'),
      reminder_minutes_before: 15,
      ...seasonTag,
      type: 'DAILY',
      ...(difficulty !== null ? { difficulty } : {}),
      ephemeral: true,
    };
    onSubmit({ mode: 'instance', task });
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

  /** 「选择模板」下拉（DEV-58）：任务板「创建新任务」入口与模板行「生成」共用。 */
  const renderTemplatePicker = () => (
    <div className="bg-slate-50 border border-slate-200 rounded-xl p-3">
      <div className="text-xs font-bold text-slate-600 mb-1.5">{t('generateTask.pickTemplate')}</div>
      {!templates ? (
        <p className="text-xs text-slate-400">{t('common.loading')}</p>
      ) : templates.length === 0 ? (
        <p className="text-xs text-slate-500">{t('generateTask.noTemplates')}</p>
      ) : (
        <select
          value={pickerValue}
          onChange={event => {
            const value = event.target.value;
            // 用户手动改选即放弃「模板行预选」，以下拉为准
            setPickerTouched(true);
            setSelectedTemplateId(value);
            setGenerateResult(null);
            setDateHasInstance(null);
            const tmpl = templates.find(item => item.id === value);
            if (tmpl) {
              setTuneValues({
                difficulty: tmpl.difficulty,
                time_deposit: tmpl.time_deposit,
                xp_reward: tmpl.xp_reward,
              });
              setTuneDirty(EMPTY_DIRTY);
            }
          }}
          aria-label={t('generateTask.pickTemplate')}
          className="border rounded-lg p-2 text-sm w-full border-slate-200"
        >
          <option value="">{t('generateTask.pickTemplatePlaceholder')}</option>
          {templates.map(item => (
            <option key={item.id} value={item.id}>
              {item.title}
            </option>
          ))}
        </select>
      )}
    </div>
  );

  /** 生成步骤主体（目标日期 + 三项微调 + 结果/错误）：
   *  新建模板第二步与「创建新任务」分支 A 共用，避免两份实现漂移。 */
  const renderGenerateStepContent = (opts: {
    templateId: string;
    templateTitle: string;
    templateType: TaskType;
    estimatedMinutes: number | null;
    fillBackDifficultyDisabled: boolean;
  }) => (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-bold text-slate-800">{opts.templateTitle}</span>
        <span className="text-[11px] text-slate-400">{t(`taskType.${opts.templateType}`)}</span>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-xl p-3">
        <div className="text-xs font-bold text-slate-600 mb-1 flex items-center gap-1">
          <CalendarClock size={13} aria-hidden /> {t('generateTask.targetDate')}
        </div>
        <input
          type="date"
          value={targetDate}
          min={today}
          max={maxDate}
          onChange={event => {
            setTargetDate(event.target.value);
            setGenerateResult(null);
          }}
          aria-invalid={Boolean(dateError)}
          aria-describedby="generate-target-date-hint"
          className={`border rounded-lg p-2 text-sm w-full ${
            dateError ? 'border-red-400' : 'border-slate-200'
          }`}
        />
        {dateFieldError ? (
          <p className="text-xs text-red-600 mt-1" aria-live="polite">{dateFieldError}</p>
        ) : (
          <p id="generate-target-date-hint" className="text-[11px] text-slate-400 mt-1">
            {t('generateTask.dateHint', { days: TARGET_DATE_MAX_AHEAD_DAYS })}
          </p>
        )}
        {dateHasInstance && !dateError && (
          <p className="text-[11px] text-slate-600 bg-slate-50 border border-slate-200 rounded-lg p-2 flex items-start gap-1 mt-1" aria-live="polite">
            <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
            <span>{t('generateTask.dateHasInstance', { date: targetDate })}</span>
          </p>
        )}
      </div>

      <div>
        <div className="text-xs font-bold text-slate-600 mb-1.5">{t('tune.sectionTitle')}</div>
        <TaskTuneFields
          template={{
            id: opts.templateId,
            type: opts.templateType,
            estimated_minutes: opts.estimatedMinutes,
          }}
          value={tuneValues}
          dirty={tuneDirty}
          onChange={changeField}
          onFillBack={fillBack}
          fillingBack={tuneFillingBack}
          fillBackDisabled={{ difficulty: opts.fillBackDifficultyDisabled }}
          previewDate={targetDate}
          disabled={generating}
        />
      </div>

      {generateResult && generateResult.instance_id === null && (
        <div
          className="bg-amber-50 border border-amber-200 rounded-xl p-3 space-y-1"
          role="status"
          aria-live="polite"
        >
          <div className="text-sm font-bold text-amber-800">{t('generateTask.resultSkippedTitle')}</div>
          <p className="text-xs text-amber-700">{resultActionCopy(generateResult)}</p>
        </div>
      )}

      {generateResult && generateResult.instance_id !== null && (
        <div
          className="bg-green-50 border border-green-200 rounded-xl p-3 space-y-1"
          role="status"
          aria-live="polite"
        >
          <div className="text-sm font-bold text-green-800">
            {generateResult.generated_for_date === null
              ? t('generateTask.resultReused')
              : generateResult.generated_for_date > today
                ? t('generateTask.scheduledFor', { date: generateResult.generated_for_date })
                : t('generateTask.deployedToday')}
          </div>
          <p className="text-xs text-green-700">{resultActionCopy(generateResult)}</p>
          <p className="text-[11px] text-slate-500">
            {t('generateTask.resultValues', {
              difficulty: generateResult.difficulty ?? t('tune.unrated'),
              deposit: generateResult.time_deposit ?? '—',
              xp: generateResult.xp_reward ?? '—',
            })}
          </p>
          {sentOverrides && !generateResult.overrides_applied && (
            <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-2">
              {t('generateTask.overridesNotApplied')}
            </p>
          )}
        </div>
      )}

      {generateError && (
        <div role="alert" className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm font-bold">
          {generateError}
        </div>
      )}
    </>
  );

  // 任务板「创建新任务」（DEV-58）：顶部「选择模板」下拉分两支
  if (!isEdit && isCreateTask) {
    // 选了模板即进入「生成」语义；未选模板是「创建」语义
    const heading = activeTemplate ? t('generateTask.title') : t('createTask.title');
    return (
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
        <div
          className="bg-white rounded-2xl w-full max-w-xl shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200"
          role="dialog"
          aria-modal="true"
          aria-label={heading}
        >
          <div className="bg-slate-900 text-white p-4 flex justify-between items-center">
            <h3 className="font-bold text-lg flex items-center gap-2">
              {activeTemplate ? <Sparkles size={20} /> : <Plus size={20} />} {heading}
            </h3>
            <button onClick={onClose} aria-label={t('common.close')}><X /></button>
          </div>

          <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
            {renderTemplatePicker()}

            {!activeTemplate ? (
              // 分支 B：未选模板 —— 一次性临时任务（ephemeral，不落模板）
              <>
                <div className="flex gap-3">
                  <div className="space-y-1.5 flex-1">
                    <label className="text-sm font-bold text-slate-700" htmlFor="create-task-title">{t('createTask.questTitle')}</label>
                    <input
                      id="create-task-title"
                      className={`w-full border p-2 rounded ${errors?.title ? 'border-red-400' : 'border-slate-200'}`}
                      value={newTaskTitle}
                      onChange={e => setNewTaskTitle(e.target.value)}
                      placeholder={t('createTask.questNamePlaceholder')}
                    />
                  </div>
                  <div className="space-y-1.5 w-20">
                    <label className="text-sm font-bold text-slate-700" htmlFor="create-task-xp">{t('common.xp')}</label>
                    <input
                      id="create-task-xp"
                      type="number"
                      min={0}
                      className={`w-full border p-2 rounded ${errors?.xp ? 'border-red-400' : 'border-slate-200'}`}
                      value={newTaskXP}
                      onChange={e => setNewTaskXP(Number(e.target.value))}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <div className="text-sm font-bold text-slate-700" id="create-task-difficulty-label">{t('taskTemplate.difficulty')}</div>
                    <div role="radiogroup" aria-labelledby="create-task-difficulty-label" className="flex gap-0.5 h-[38px] items-center">
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
                  <label className="text-sm font-bold text-slate-700">{t('createTask.questContent')}</label>
                  <textarea className="w-full border border-slate-200 p-2 rounded h-20" value={newTaskDesc} onChange={e => setNewTaskDesc(e.target.value)} placeholder={t('createTask.questContentPlaceholder')} />
                </div>

                {/* 分支 B 的「要点 → LLM 润色」接口尚未落地（P3 单开）：此处只预留位置，禁用并说明 */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <label className="text-sm font-bold text-slate-700" htmlFor="create-task-brief">{t('createTask.brief')}</label>
                    <button
                      type="button"
                      disabled
                      title={t('createTask.polishDisabledHint')}
                      aria-disabled="true"
                      className="text-[11px] font-bold text-sky-700 px-2 py-1 rounded border border-slate-200 bg-slate-50 opacity-50 cursor-not-allowed"
                    >
                      <Sparkles size={12} className="inline -mt-0.5 mr-0.5" aria-hidden /> {t('createTask.polish')}
                    </button>
                  </div>
                  <textarea
                    id="create-task-brief"
                    className="w-full border border-slate-200 p-2 rounded h-16"
                    value={contentBrief}
                    onChange={e => setContentBrief(e.target.value)}
                    placeholder={t('createTask.briefPlaceholder')}
                  />
                  <p className="text-[11px] text-slate-400">{t('createTask.briefHint')}</p>
                  <p className="text-[11px] text-amber-600">{t('createTask.polishDisabledHint')}</p>
                </div>

                <div className="flex items-center gap-2 p-3 bg-violet-50 border border-violet-100 rounded-lg">
                  <Info size={14} className="text-violet-500 shrink-0" />
                  <span className="text-xs text-violet-700">{t('createTask.onceHint')}</span>
                </div>
              </>
            ) : (
              // 分支 A：选了模板 —— 目标日期 + 三项微调 → 生成
              renderGenerateStepContent({
                templateId: activeTemplate.id,
                templateTitle: activeTemplate.title,
                templateType: activeTemplate.type,
                estimatedMinutes: activeTemplate.estimated_minutes,
                fillBackDifficultyDisabled: activeTemplate.difficulty === null,
              })
            )}
          </div>

          <div className="p-4 bg-slate-50 border-t flex justify-end gap-2">
            <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold hover:bg-slate-200 rounded">
              {t('common.cancel')}
            </button>
            {!activeTemplate ? (
              <button
                onClick={handleSubmitCreateTask}
                disabled={submitting || !newTaskTitle.trim()}
                className="px-4 py-2 bg-green-600 text-white font-bold rounded hover:bg-green-700 shadow-md transform active:scale-95 disabled:opacity-50"
              >
                {submitting ? t('common.loading') : t('createTask.submit')}
              </button>
            ) : (
              <button
                onClick={handleGenerateSubmit}
                disabled={Boolean(dateError) || generating}
                className="px-4 py-2 bg-green-600 text-white font-bold rounded hover:bg-green-700 shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {generating ? t('common.loading') : t('generateTask.submit')}
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  // 新建非 once 模板：第一步是建模板，第二步是选日期+微调
  if (!isEdit && category !== 'once' && !createdTemplateId) {
    const submitLabel = t('taskTemplate.createTemplate');
    const triggerErrorOf = (index: number) => errors?.triggers?.[index];

    return (
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
        <div
          className="bg-white rounded-2xl w-full max-w-xl shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200"
          role="dialog"
          aria-modal="true"
          aria-label={t('addTask.title')}
        >
          <div className="bg-slate-900 text-white p-4 flex justify-between items-center">
            <h3 className="font-bold text-lg flex items-center gap-2">
              <Plus size={20} /> {t('addTask.title')}
            </h3>
            <button onClick={onClose} aria-label={t('common.close')}><X /></button>
          </div>
          <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">

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
            </div>

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

              <p className="text-[11px] text-slate-500 mt-2">
                📅{' '}
                {t('taskTemplate.previewLine', {
                  rules: triggers.map(draft => describeTrigger(draftToTriggerPayload(draft), t)).join(t('taskTemplate.listJoiner')),
                })}
                {category === 'timed' ? ' ' + t('taskTemplate.previewTimedSuffix') : ''}
                {triggers.length > 1 ? ' ' + t('taskTemplate.previewDedupe') : ''}
              </p>
            </div>

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
          </div>

          <div className="p-4 bg-slate-50 flex justify-between items-center gap-2 border-t">
            <p className="text-[11px] text-slate-400">
              {t('taskTemplate.footerTemplate')}
            </p>
            <div className="flex gap-2 shrink-0">
              <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold hover:bg-slate-200 rounded">{t('common.cancel')}</button>
              <button
                onClick={async () => {
                  await handleSubmitTemplate();
                }}
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
  }

  // 生成步骤（新建非 once 模板第二步：模板已落库，直接选日期 + 微调生成实例）
  if (!isEdit && category !== 'once' && createdTemplateId) {
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
            {renderGenerateStepContent({
              templateId: createdTemplateId,
              templateTitle: newTaskTitle.trim(),
              templateType: CATEGORY_TYPE[category],
              estimatedMinutes: null,
              fillBackDifficultyDisabled: false,
            })}
          </div>

          <div className="p-4 bg-slate-50 border-t flex justify-end gap-2">
            <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold hover:bg-slate-200 rounded">
              {t('common.cancel')}
            </button>
            <button
              onClick={handleGenerateSubmit}
              disabled={!createdTemplateId || Boolean(dateError) || generating}
              className="px-4 py-2 bg-green-600 text-white font-bold rounded hover:bg-green-700 shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {generating ? t('common.loading') : t('generateTask.submit')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // 编辑模板 或 一次性新建（走原路径）
  const patchTrigger = (index: number, patch: Partial<TriggerDraft>) => {
    setTriggers(prev => prev.map((draft, i) => (i === index ? { ...draft, ...patch } : draft)));
  };

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
    const formErrors = buildError();
    setErrors(formErrors);
    if (formErrors) return;

    const timedPayload =
      timedMode === 'DEADLINE'
        ? { timed_mode: timedMode, deadline_time: deadlineTime }
        : timedMode === 'DURATION'
          ? { timed_mode: timedMode, start_time: startTime, duration_minutes: durationMinutes }
          : { timed_mode: 'NONE' as const, deadline_time: null, start_time: null, duration_minutes: null };

    const seasonTag = seasonId ? { season_id: seasonId } : {};

    if (isEdit && editingTemplate) {
      const patch: TaskTemplateUpdate = {
        title: newTaskTitle.trim(),
        description: newTaskDesc,
        xp_reward: Math.max(0, newTaskXP),
        difficulty,
        content_brief: contentBrief.trim() || null,
        content_mode: contentMode,
        ...timedPayload,
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
      const task: TaskCreate = {
        ...base,
        ...seasonTag,
        type: 'DAILY',
      };
      onSubmit({ mode: 'instance', task });
      return;
    }

    // 其他类别新建：走模板创建路径（编辑路径已在上面 return）
    const template: TaskTemplateCreate = {
      ...base,
      ...seasonTag,
      type: CATEGORY_TYPE[category],
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
            {isEdit && editingTemplate?.lore_snippet && (
              <p className="text-[11px] text-slate-400 bg-slate-50 border border-slate-200 rounded-lg p-2">
                {t('addTask.loreNeutralHint')}
              </p>
            )}
          </div>

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
