import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../../services/api';
import type { TaskCreate, TaskType } from '../../services/api';
import { X, Plus, BrainCircuit, Info } from 'lucide-react';

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

/** 新建任务（阶段③）：表单产出 TaskCreate，POST /scn/task-instances 由 App 调用（docs/09 A6） */
const AddTaskModal: React.FC<AddTaskModalProps> = ({ isOpen, onClose, onAdd, narrativeContext, seasonId, childLevel, submitting }) => {
  const { t } = useTranslation();
  const [newTaskTitle, setNewTaskTitle] = useState('');
  const [newTaskDesc, setNewTaskDesc] = useState('');
  const [newTaskLore, setNewTaskLore] = useState('');
  const [newTaskXP, setNewTaskXP] = useState(50);
  const [newTaskType, setNewTaskType] = useState<TaskType>('DAILY');

  // AI State（阶段⑥已切后端 /scn/ai/generate-quest）
  const [aiPrompt, setAiPrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  // 打开时重置表单（创建失败时 App 保留弹窗与已填内容，成功后关闭并在此处复位）
  useEffect(() => {
    if (isOpen) {
      setNewTaskTitle('');
      setNewTaskDesc('');
      setNewTaskLore('');
      setNewTaskXP(50);
      setNewTaskType('DAILY');
      setAiPrompt('');
    }
  }, [isOpen]);

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

  const handleSubmit = () => {
    if (!newTaskTitle.trim() || !seasonId) return;
    onAdd({
      season_id: seasonId,
      title: newTaskTitle.trim(),
      description: newTaskDesc,
      lore_snippet: newTaskLore || undefined,
      xp_reward: Math.max(0, newTaskXP),
      type: newTaskType,
      reminder_message: t('addTask.defaultReminder'),
      reminder_minutes_before: 15,
    });
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
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
