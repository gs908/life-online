import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../../services/api';
import type { TaskInstancePatch, TaskRead, TaskTemplateRead } from '../../services/api';
import { Sliders, X } from 'lucide-react';
import TaskTuneFields, { type TuneField, type TuneValues } from '../TaskTuneFields';
import { localToday } from '../../utils/date';

interface TuneTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** 待微调的实例（来自任务板 / 模板详情抽屉） */
  task: TaskRead | null;
  onSaved: () => void;
  onToast: (title: string, msg: string) => void;
}

const EMPTY_DIRTY: Record<TuneField, boolean> = {
  difficulty: false,
  time_deposit: false,
  xp_reward: false,
};

/**
 * 生成之后的微调（契约 §6B，`PATCH /scn/task-instances/{id}`）。
 *
 * - 三个字段都是**快照**：只提交用户改过的字段；`null` 一律 422 → 本组件永不发 null；
 * - 「按模板当前值填回」现取一次模板当前值再填（一次性取值，之后改模板不会同步）；
 * - 实例 `season_id` 不可改（任务不跨赛季），故表单里没有赛季控件。
 */
const TuneTaskModal: React.FC<TuneTaskModalProps> = ({ isOpen, onClose, task, onSaved, onToast }) => {
  const { t } = useTranslation();
  const today = useMemo(() => localToday(), [isOpen]);

  const [template, setTemplate] = useState<TaskTemplateRead | null>(null);
  const [values, setValues] = useState<TuneValues>({ difficulty: null, time_deposit: 0, xp_reward: 0 });
  const [dirty, setDirty] = useState<Record<TuneField, boolean>>(EMPTY_DIRTY);
  const [fillingBack, setFillingBack] = useState<TuneField | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const loadTemplate = useCallback(async (templateId: string | null) => {
    if (!templateId) {
      setTemplate(null);
      return null;
    }
    try {
      const fresh = await api.taskTemplates.getTemplate(templateId);
      setTemplate(fresh);
      return fresh;
    } catch {
      setTemplate(null);
      return null;
    }
  }, []);

  useEffect(() => {
    if (!isOpen || !task) return;
    setFormError(null);
    setFillingBack(null);
    setDirty(EMPTY_DIRTY);
    // 预填实例当前值（快照值本身就是实例上的具体数值）
    setValues({
      difficulty: task.difficulty,
      time_deposit: task.time_deposit,
      xp_reward: task.xp_reward,
    });
    void loadTemplate(task.template_id);
  }, [isOpen, task, loadTemplate]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !task) return null;

  const changeField = (field: TuneField, next: number) => {
    setValues(prev => ({ ...prev, [field]: next }));
    setDirty(prev => ({ ...prev, [field]: true }));
  };

  /** 「按模板当前值填回」：现取模板当前值（一次性取值，不是持续跟随） */
  const fillBack = async (field: TuneField) => {
    if (!task.template_id) return;
    setFillingBack(field);
    try {
      const fresh = (await loadTemplate(task.template_id)) ?? template;
      if (!fresh) throw new Error('template unavailable');
      // ⚠️ 模板未评星时 difficulty 是 null，难度没有"空值"可提交（后端 ge=1）：
      // 写 0 必然 422，故直接不动值并说明（Mars 审查 🔴）
      if (field === 'difficulty') {
        if (fresh.difficulty === null || fresh.difficulty < 1) {
          onToast(t('toast.actionFailedTitle'), t('tune.fillBackNoTemplateValue'));
          return;
        }
        setValues(prev => ({ ...prev, difficulty: fresh.difficulty as number }));
      } else if (field === 'time_deposit') {
        setValues(prev => ({ ...prev, time_deposit: fresh.time_deposit }));
      } else {
        setValues(prev => ({ ...prev, xp_reward: fresh.xp_reward }));
      }
      setDirty(prev => ({ ...prev, [field]: true }));
    } catch (error) {
      onToast(t('toast.actionFailedTitle'), error instanceof ApiError ? error.message : t('tune.fillBackFailed'));
    } finally {
      setFillingBack(null);
    }
  };

  const handleSubmit = async () => {
    // 只放改过的字段；没有任何改动就不发请求（未提供 = 保持不变）
    const body: TaskInstancePatch = {};
    // 结构上兜住"永不发出非法难度"：后端 ge=1
    if (dirty.difficulty && values.difficulty !== null && values.difficulty >= 1) {
      body.difficulty = values.difficulty;
    }
    if (dirty.time_deposit) body.time_deposit = values.time_deposit;
    if (dirty.xp_reward) body.xp_reward = values.xp_reward;
    if (Object.keys(body).length === 0) {
      onClose();
      return;
    }
    setFormError(null);
    setSubmitting(true);
    try {
      await api.tasks.patchTask(task.id, body);
      onSaved();
      onToast(t('toast.taskTunedTitle'), t('toast.taskTunedMsg', { title: task.title }));
      onClose();
    } catch (error) {
      // 422（含"显式 null 一律拒绝"）原样透出：按契约这条前端不该触发，出现即是我们自己的 bug
      setFormError(error instanceof ApiError ? error.message : t('tune.saveFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div
        className="bg-white rounded-2xl w-full max-w-xl shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200"
        role="dialog"
        aria-modal="true"
        aria-label={t('tune.title')}
      >
        <div className="bg-slate-900 text-white p-4 flex justify-between items-center">
          <h3 className="font-bold text-lg flex items-center gap-2">
            <Sliders size={20} /> {t('tune.title')}
          </h3>
          <button onClick={onClose} aria-label={t('common.close')}>
            <X />
          </button>
        </div>

        <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-bold text-slate-800">{task.title}</span>
            <span className="text-[11px] text-slate-400">
              {t(`taskStatus.${task.status}`)}
              {task.generated_for_date ? ` · ${task.generated_for_date}` : ''}
              {task.season_name ? ` · ${task.season_name}` : ''}
            </span>
          </div>

          <TaskTuneFields
            template={{
              id: task.template_id,
              type: task.type,
              estimated_minutes: template?.estimated_minutes ?? null,
            }}
            value={values}
            dirty={dirty}
            onChange={changeField}
            onFillBack={fillBack}
            fillingBack={fillingBack}
            // 模板未取到 / 未评星时难度「填回」置灰：无值可填，写 0 会被 ge=1 拒绝
            fillBackDisabled={{ difficulty: template === null || template.difficulty === null }}
            previewDate={task.generated_for_date ?? today}
            disabled={submitting}
          />

          {formError && (
            <div role="alert" className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm font-bold">
              {formError}
            </div>
          )}

          <p className="text-[11px] text-slate-400">{t('tune.snapshotHint')}</p>
        </div>

        <div className="p-4 bg-slate-50 border-t flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold hover:bg-slate-200 rounded">
            {t('common.cancel')}
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="px-4 py-2 bg-green-600 text-white font-bold rounded hover:bg-green-700 shadow-md disabled:opacity-50"
          >
            {submitting ? t('common.loading') : t('tune.save')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default TuneTaskModal;