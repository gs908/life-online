import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../../services/api';
import type { TaskCreate, TaskDepositPreviewResponse, TaskType } from '../../services/api';
import { X, Plus, BrainCircuit, Info, Coins, AlertTriangle, Minus, ChevronDown, ChevronRight } from 'lucide-react';

interface AddTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** 提交 TaskCreate（season_id 必填，由 App 注入激活赛季）；失败时 App toast 且弹窗保留 */
  onAdd: (task: TaskCreate) => void;
  narrativeContext: string;
  seasonId: string;
  childLevel: number;
  submitting?: boolean;
}

/** 耗时输入范围与后端 schemas/task.py 的 ge=1 le=1440 对齐 */
const MIN_MINUTES = 1;
const MAX_MINUTES = 24 * 60;
const QUICK_MINUTES = [15, 30, 60, 90];
/** 押金封顶比例：与后端 DepositSection.allowance_cap_ratio（0.5）一致，仅用于展示折算 */
const ALLOWANCE_CAP_RATIO = 0.5;

type PreviewStatus = 'idle' | 'loading' | 'ready' | 'error';

interface PreviewState {
  status: PreviewStatus;
  data?: TaskDepositPreviewResponse;
}

/** 押金预览卡（Miss.D 规范 §3 状态矩阵 / §4 样式）：aria-live 播报，封顶态升为 assertive */
const DepositPreviewCard: React.FC<{
  preview: PreviewState;
  manual: boolean;
  onRetry: () => void;
}> = ({ preview, manual, onRetry }) => {
  const { t } = useTranslation();
  const { status, data } = preview;
  const free = status === 'ready' && data!.time_deposit === 0;
  const capped = status === 'ready' && data!.capped_by_allowance && !free;

  if (status === 'ready' && free) {
    // ⑥ 免押：显示"免押金"，配额行隐藏
    return (
      <div className="p-3 rounded-xl border bg-slate-50 border-slate-200" data-testid="deposit-preview">
        <div aria-live="polite">
          <div className="flex items-center gap-2">
            <Coins size={16} className="text-slate-400" />
            <span className="text-xl font-bold text-slate-600 tmpl-fade" key="free">{t('tmpl.depositFree')}</span>
            {manual && <ManualBadge label={t('tmpl.depositManual')} />}
          </div>
        </div>
      </div>
    );
  }

  if (status === 'error') {
    // ④ 错误降级：不阻断提交，押金由后端创建时重算
    return (
      <div className="p-3 rounded-xl border bg-slate-50 border-slate-200 text-slate-400" data-testid="deposit-preview">
        <div aria-live="polite">
          <p className="text-sm">{t('tmpl.depositFallback')}</p>
          <button
            type="button"
            onClick={onRetry}
            className="text-xs text-blue-600 underline mt-1.5 hover:text-blue-700"
          >
            {t('tmpl.retry')}
          </button>
        </div>
      </div>
    );
  }

  if (status === 'idle') {
    // 耗时字段为空/非法：不发预览请求，仅提示落库兜底
    return (
      <div className="p-3 rounded-xl border bg-slate-50 border-slate-200 text-slate-400" data-testid="deposit-preview">
        <div aria-live="polite">
          <p className="text-sm">{t('tmpl.depositFallback')}</p>
        </div>
      </div>
    );
  }

  const deposit = status === 'ready' ? data!.time_deposit : null;

  return (
    <div
      className={`p-3 rounded-xl border transition-colors duration-150 motion-reduce:transition-none ${
        capped ? 'bg-amber-100 border-amber-300' : 'bg-amber-50 border-amber-100'
      }`}
      data-testid="deposit-preview"
    >
      <div aria-live={capped ? 'assertive' : 'polite'}>
        <div className="flex justify-between items-center">
          <span className="text-[10px] font-bold uppercase text-amber-800 tracking-wider">
            {t('tmpl.depositPreview')}
          </span>
          {capped && (
            <span className="tmpl-fade flex items-center gap-1 text-[10px] font-bold uppercase text-amber-800 bg-amber-200 rounded-full px-2 py-0.5">
              <AlertTriangle size={12} /> {t('tmpl.cappedBadge')}
            </span>
          )}
        </div>
        <div className="flex items-baseline gap-1.5 mt-1">
          <Coins size={16} className="text-amber-700 self-center" />
          {deposit === null ? (
            // ② 加载：骨架占位，卡片高度不变
            <span className="text-2xl font-bold text-amber-700/40 animate-pulse" aria-hidden="true">···</span>
          ) : (
            <span
              key={deposit}
              className={`text-2xl font-bold tmpl-fade ${capped ? 'text-amber-800 tmpl-pop' : 'text-amber-700'}`}
              data-testid="deposit-value"
            >
              {deposit}
            </span>
          )}
          <span className="text-xs text-amber-800/80">{t('tmpl.depositLabel')}</span>
          {manual && <ManualBadge label={t('tmpl.depositManual')} />}
        </div>
        {status === 'ready' && (
          <p className="text-xs text-slate-500 mt-1">
            {t('tmpl.quotaLine', {
              allowance: data!.daily_allowance,
              cap: Math.floor(data!.daily_allowance * ALLOWANCE_CAP_RATIO),
            })}
          </p>
        )}
        {capped && (
          <p className="text-xs text-amber-800 mt-1">{t('tmpl.cappedHint')}</p>
        )}
      </div>
    </div>
  );
};

const ManualBadge: React.FC<{ label: string }> = ({ label }) => (
  <span className="text-[10px] font-bold text-slate-600 bg-slate-200 rounded-full px-2 py-0.5">{label}</span>
);

/** 新建任务（阶段③）：表单产出 TaskCreate，POST /scn/task-instances 由 App 调用（docs/09 A6）。
 *  DEV-34 块 C：新增"难度 + 预计耗时 + 押金实时预览"——押金 = 耗时驱动，难度只影响 XP。 */
const AddTaskModal: React.FC<AddTaskModalProps> = ({ isOpen, onClose, onAdd, narrativeContext, seasonId, childLevel, submitting }) => {
  const { t } = useTranslation();
  const [newTaskTitle, setNewTaskTitle] = useState('');
  const [newTaskDesc, setNewTaskDesc] = useState('');
  const [newTaskLore, setNewTaskLore] = useState('');
  const [newTaskXP, setNewTaskXP] = useState(50);
  const [newTaskType, setNewTaskType] = useState<TaskType>('DAILY');

  // 难度与耗时（押金耗时驱动的输入；难度不影响押金，仅透传对齐契约）
  const [difficulty, setDifficulty] = useState(2);
  const [estimatedMinutes, setEstimatedMinutes] = useState('30');
  const [manualDeposit, setManualDeposit] = useState('');
  const [advancedOpen, setAdvancedOpen] = useState(false);

  // 押金预览：400ms 防抖 + 递增 seq 丢弃过期响应（快速改耗时不闪动）
  const [preview, setPreview] = useState<PreviewState>({ status: 'loading' });
  const previewSeqRef = useRef(0);
  const lastTypeRef = useRef<TaskType | null>(null);

  // AI State（阶段⑥已切后端 /scn/ai/generate-quest）
  const [aiPrompt, setAiPrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const minutesNum = estimatedMinutes.trim() === '' ? null : Number(estimatedMinutes);
  const minutesInvalid =
    minutesNum === null || !Number.isInteger(minutesNum) || minutesNum < MIN_MINUTES || minutesNum > MAX_MINUTES;
  const minutesValid = minutesNum !== null && !minutesInvalid;

  const depositNum = manualDeposit.trim() === '' ? null : Number(manualDeposit);
  const depositInvalid = depositNum !== null && (!Number.isInteger(depositNum) || depositNum < 0);
  const manualActive = depositNum !== null && !depositInvalid;

  /** 立即发起一次预览（重试链接 / seq 守序由调用方兜底） */
  const fetchPreview = useCallback(
    (type: TaskType, minutes: number | null, explicitDeposit: number | null) => {
      const seq = ++previewSeqRef.current;
      setPreview({ status: 'loading' });
      api.tasks
        .previewDeposit({
          type,
          estimated_minutes: minutes ?? undefined,
          time_deposit: explicitDeposit ?? undefined,
          difficulty, // 难度不影响押金，透传仅为契约完整
        })
        .then((data) => {
          if (previewSeqRef.current === seq) setPreview({ status: 'ready', data });
        })
        .catch(() => {
          if (previewSeqRef.current === seq) setPreview({ status: 'error' });
        });
    },
    [difficulty],
  );

  // 打开时重置表单（创建失败时 App 保留弹窗与已填内容，成功后关闭并在此处复位）
  useEffect(() => {
    if (isOpen) {
      setNewTaskTitle('');
      setNewTaskDesc('');
      setNewTaskLore('');
      setNewTaskXP(50);
      setNewTaskType('DAILY');
      setDifficulty(2);
      setEstimatedMinutes('30');
      setManualDeposit('');
      setAdvancedOpen(false);
      setAiPrompt('');
    }
  }, [isOpen]);

  // 预览触发源：type / estimated_minutes / time_deposit。难度不触发（后端难度不进押金公式）。
  // 类型切换立刻请求（delay=0），其余变更 400ms 防抖；过期响应用 seq 丢弃。
  useEffect(() => {
    if (!isOpen) return;
    const typeChanged = lastTypeRef.current !== newTaskType;
    lastTypeRef.current = newTaskType;
    if (!minutesValid) {
      // 耗时非法（空/越界）：不请求，预览卡显示兜底文案
      previewSeqRef.current++; // 使在途响应失效
      setPreview({ status: 'idle' });
      return;
    }
    const delay = typeChanged ? 0 : 400;
    const timer = window.setTimeout(() => {
      fetchPreview(newTaskType, minutesNum, manualActive ? depositNum : null);
    }, delay);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, newTaskType, estimatedMinutes, manualDeposit]);

  if (!isOpen) return null;

  const handleGenerateQuest = async () => {
    if (!aiPrompt) return;
    setIsGenerating(true);
    setAiError(null);
    // AI 调用统一走后端 /scn/ai(模型与默认参数收敛在后端 config.yaml 的 ai.llm 段)
    try {
      const suggestion = await api.ai.generateQuest({
        topic: aiPrompt,
        child_level: childLevel,
        narrative_context: narrativeContext,
      });
      setNewTaskTitle(suggestion.title);
      setNewTaskDesc(suggestion.description);
      setNewTaskLore(suggestion.lore_snippet ?? '');
      setNewTaskXP(suggestion.xp_reward);
      setNewTaskType(suggestion.type as TaskType);
    } catch (err) {
      if (err instanceof ApiError && err.errorCode === 'service_unavailable') {
        setAiError(t('addTask.aiNotConfigured'));
      } else {
        setAiError(err instanceof Error ? err.message : t('addTask.aiFailed'));
      }
    } finally {
      setIsGenerating(false);
    }
  };

  /** 难度分段：方向键在 1–5 间移动并选中（role=radiogroup 语义） */
  const handleDifficultyKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const delta = e.key === 'ArrowRight' || e.key === 'ArrowUp' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowDown' ? -1 : 0;
    if (!delta) return;
    e.preventDefault();
    const next = Math.min(5, Math.max(1, difficulty + delta));
    setDifficulty(next);
    document.getElementById(`difficulty-opt-${next}`)?.focus();
  };

  const stepMinutes = (delta: number) => {
    const base = minutesValid ? minutesNum! : 30;
    setEstimatedMinutes(String(Math.min(MAX_MINUTES, Math.max(MIN_MINUTES, base + delta))));
  };

  const handleRetryPreview = () => {
    if (minutesValid) fetchPreview(newTaskType, minutesNum, manualActive ? depositNum : null);
  };

  const handleSubmit = () => {
    if (!newTaskTitle.trim() || !seasonId) return;
    onAdd({
      season_id: seasonId,
      title: newTaskTitle.trim(),
      description: newTaskDesc,
      lore_snippet: newTaskLore || undefined,
      xp_reward: Math.max(0, newTaskXP),
      type: newTaskType,
      difficulty,
      estimated_minutes: minutesValid ? minutesNum! : undefined,
      time_deposit: manualActive ? depositNum! : undefined, // 缺省时后端按耗时解析落库；预览不作为提交依赖
      reminder_message: t('addTask.defaultReminder'),
      reminder_minutes_before: 15,
    });
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      {/* 数值 fade / 封顶脉冲 / reduced-motion 降级（Miss.D §4 动效） */}
      <style>{`
        @keyframes tmpl-fade-in { from { opacity: 0; } to { opacity: 1; } }
        .tmpl-fade { animation: tmpl-fade-in 150ms ease-out; }
        @keyframes tmpl-pop-in { 0% { transform: scale(1); } 50% { transform: scale(1.08); } 100% { transform: scale(1); } }
        .tmpl-pop { animation: tmpl-pop-in 200ms ease-out; }
        @media (prefers-reduced-motion: reduce) {
          .tmpl-fade, .tmpl-pop, .animate-pulse { animation: none !important; }
        }
      `}</style>
      <div className="bg-white rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200">
        <div className="bg-slate-900 text-white p-4 flex justify-between items-center">
          <h3 className="font-bold text-lg flex items-center gap-2"><Plus size={20} /> {t('addTask.title')}</h3>
          <button onClick={onClose}><X /></button>
        </div>
        <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
          {/* AI Generator */}
          <div className="bg-purple-50 p-4 rounded-xl border border-purple-100">
            <label className="text-xs font-bold text-purple-700 uppercase mb-2 block flex items-center gap-1">
              <BrainCircuit size={14} /> {t('addTask.aiGenerator')}
            </label>
            <p className="text-xs text-slate-500 mb-2 italic">{t('addTask.basedOnTheme')} "{narrativeContext.substring(0, 50)}..."</p>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder={t('addTask.aiPlaceholder')}
                className="flex-1 text-sm p-2 rounded border border-purple-200 focus:outline-none focus:border-purple-500"
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
              />
              <button
                disabled={isGenerating || !aiPrompt}
                onClick={handleGenerateQuest}
                className="bg-purple-600 text-white px-3 py-2 rounded font-bold text-xs disabled:opacity-50"
              >
                {isGenerating ? t('common.loadingThinking') : t('common.generate')}
              </button>
            </div>
            {aiError && (
              <p className="text-xs text-red-600 mt-2" data-testid="ai-error">{aiError}</p>
            )}
          </div>

          <div className="space-y-2">
            <label className="text-sm font-bold text-slate-700">{t('addTask.questTitle')}</label>
            <input className="w-full border p-2 rounded" value={newTaskTitle} onChange={e => setNewTaskTitle(e.target.value)} placeholder={t('addTask.questNamePlaceholder')} />
          </div>

          <div className="flex gap-4">
            <div className="space-y-2 flex-1">
              <label className="text-sm font-bold text-slate-700">{t('addTask.type')}</label>
              <select className="w-full border p-2 rounded" value={newTaskType} onChange={e => setNewTaskType(e.target.value as TaskType)}>
                {(['DAILY', 'CHALLENGE', 'CHAIN', 'TIMED', 'COOP'] as TaskType[]).map(type => <option key={type} value={type}>{t(`taskType.${type}`)}</option>)}
              </select>
            </div>
            <div className="space-y-2 w-24">
              <label className="text-sm font-bold text-slate-700">{t('common.xp')}</label>
              <input type="number" min={0} className="w-full border p-2 rounded" value={newTaskXP} onChange={e => setNewTaskXP(Number(e.target.value))} />
            </div>
          </div>

          {/* 难度与耗时（DEV-34 块 C）：押金 = 耗时驱动，难度 → XP 倍率 */}
          <div className="bg-slate-50 p-4 rounded-xl border border-slate-100 space-y-3">
            <div className="space-y-1.5">
              <label className="text-sm font-bold text-slate-700">{t('tmpl.difficulty')}</label>
              <div
                role="radiogroup"
                aria-label={t('tmpl.difficulty')}
                className="flex gap-1.5"
                onKeyDown={handleDifficultyKeyDown}
              >
                {([1, 2, 3, 4, 5] as const).map(d => (
                  <button
                    key={d}
                    id={`difficulty-opt-${d}`}
                    type="button"
                    role="radio"
                    aria-checked={difficulty === d}
                    tabIndex={difficulty === d ? 0 : -1}
                    onClick={() => setDifficulty(d)}
                    className={`min-w-[44px] h-10 rounded font-bold text-sm transition-colors duration-150 motion-reduce:transition-none ${
                      difficulty === d
                        ? 'bg-slate-900 text-white'
                        : 'bg-white text-slate-600 border border-slate-300 hover:border-slate-400'
                    }`}
                  >
                    {d}
                  </button>
                ))}
              </div>
              <p className="text-xs text-slate-400">{t('tmpl.difficultyHint')}</p>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-bold text-slate-700" htmlFor="estimated-minutes">{t('tmpl.estimatedMinutes')}</label>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  aria-label={t('tmpl.decreaseMinutes')}
                  onClick={() => stepMinutes(-5)}
                  className="w-9 h-10 flex items-center justify-center rounded border border-slate-300 bg-white text-slate-600 hover:bg-slate-100"
                >
                  <Minus size={16} />
                </button>
                <input
                  id="estimated-minutes"
                  type="number"
                  min={MIN_MINUTES}
                  max={MAX_MINUTES}
                  step={5}
                  value={estimatedMinutes}
                  onChange={e => setEstimatedMinutes(e.target.value)}
                  aria-invalid={minutesInvalid}
                  className={`w-20 text-sm p-2 rounded border text-center focus:outline-none ${
                    minutesInvalid ? 'border-red-400 focus:border-red-500' : 'border-slate-300 focus:border-slate-500'
                  }`}
                />
                <button
                  type="button"
                  aria-label={t('tmpl.increaseMinutes')}
                  onClick={() => stepMinutes(5)}
                  className="w-9 h-10 flex items-center justify-center rounded border border-slate-300 bg-white text-slate-600 hover:bg-slate-100"
                >
                  <Plus size={16} />
                </button>
                <span className="text-sm text-slate-500">{t('tmpl.minutesUnit')}</span>
              </div>
              {minutesInvalid && (
                <p className="text-xs text-red-600" role="alert">{t('tmpl.minutesInvalid')}</p>
              )}
              <div className="flex gap-2 pt-0.5" role="group" aria-label={t('tmpl.quickChips')}>
                {QUICK_MINUTES.map(m => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setEstimatedMinutes(String(m))}
                    className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs text-slate-600 hover:border-slate-500"
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>

            {/* 高级（可选）：手动指定押金，对应 time_deposit 显式值；填 0 = 免押金 */}
            <div className="space-y-1.5">
              <button
                type="button"
                aria-expanded={advancedOpen}
                onClick={() => setAdvancedOpen(v => !v)}
                className="flex items-center gap-1 text-xs font-bold text-slate-500 hover:text-slate-700"
              >
                {advancedOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                {t('tmpl.advanced')}
              </button>
              {advancedOpen && (
                <div className="space-y-1.5">
                  <label className="text-xs text-slate-600" htmlFor="manual-deposit">{t('tmpl.manualDeposit')}</label>
                  <input
                    id="manual-deposit"
                    type="number"
                    min={0}
                    step={1}
                    value={manualDeposit}
                    onChange={e => setManualDeposit(e.target.value)}
                    aria-invalid={depositInvalid}
                    placeholder={t('tmpl.manualDepositPlaceholder')}
                    className={`w-28 text-sm p-2 rounded border focus:outline-none ${
                      depositInvalid ? 'border-red-400 focus:border-red-500' : 'border-slate-300 focus:border-slate-500'
                    }`}
                  />
                  {depositInvalid && (
                    <p className="text-xs text-red-600" role="alert">{t('tmpl.manualDepositInvalid')}</p>
                  )}
                  <p className="text-xs text-slate-400">{t('tmpl.manualDepositHint')}</p>
                </div>
              )}
            </div>
          </div>

          {/* 押金预览卡（实时，纯展示：提交 payload 不依赖预览结果，押金由后端创建时按同一公式落库） */}
          <DepositPreviewCard preview={preview} manual={manualActive} onRetry={handleRetryPreview} />

          <div className="space-y-2">
            <label className="text-sm font-bold text-slate-700">{t('addTask.descriptionLore')}</label>
            <textarea className="w-full border p-2 rounded h-24" value={newTaskDesc} onChange={e => setNewTaskDesc(e.target.value)} placeholder={t('addTask.descriptionPlaceholder')} />
          </div>

          <div className="p-3 bg-orange-50 rounded border border-orange-100">
            <div className="flex items-center gap-2 mb-2">
              <Info size={14} className="text-orange-500" />
              <span className="text-xs font-bold text-orange-700">{t('addTask.timedSettings')}</span>
            </div>
            <div className="text-xs text-slate-500">
              {t('addTask.timedHint')}
            </div>
          </div>
        </div>
        <div className="p-4 bg-slate-50 flex justify-end gap-2 border-t">
          <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold hover:bg-slate-200 rounded">{t('common.cancel')}</button>
          <button onClick={handleSubmit} disabled={submitting || !newTaskTitle.trim()} className="px-4 py-2 bg-green-600 text-white font-bold rounded hover:bg-green-700 shadow-md transform active:scale-95 disabled:opacity-50">{submitting ? t('common.loading') : t('addTask.postQuest')}</button>
        </div>
      </div>
    </div>
  );
};

export default AddTaskModal;
