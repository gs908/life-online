import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../services/api';
import type { TaskRead, TaskStatus, TaskTemplateRead } from '../services/api';
import { Pencil, X } from 'lucide-react';
import {
  categoryOf,
  describeRange,
  describeTimeWindow,
  describeTrigger,
} from './taskTemplateUtils';

/** 实例状态色点（Miss.D §4 详情抽屉：最近实例列表） */
const STATUS_DOT: Record<TaskStatus, string> = {
  AVAILABLE: 'bg-sky-500',
  IN_PROGRESS: 'bg-amber-500',
  PENDING_REVIEW: 'bg-violet-500',
  COMPLETED: 'bg-green-500',
  EXPIRED: 'bg-slate-400',
};

interface TaskTemplateDetailDrawerProps {
  template: TaskTemplateRead | null;
  onClose: () => void;
  onEdit: (template: TaskTemplateRead) => void;
}

/** 模板详情抽屉（Miss.D §4：点卡片滑出，展示全部触发规则、时间窗、pool_policy、最近实例） */
const TaskTemplateDetailDrawer: React.FC<TaskTemplateDetailDrawerProps> = ({ template, onClose, onEdit }) => {
  const { t } = useTranslation();
  const [recent, setRecent] = useState<TaskRead[] | null>(null);

  // 打开时拉最近实例（契约 §6：GET /scn/task-instances?template_id）
  useEffect(() => {
    setRecent(null);
    if (!template) return;
    let cancelled = false;
    api.tasks
      .listTasks({ template_id: template.id, page_size: 10 })
      .then(page => { if (!cancelled) setRecent(page.items); })
      .catch(() => { if (!cancelled) setRecent([]); });
    return () => { cancelled = true; };
  }, [template]);

  // Esc 关闭
  useEffect(() => {
    if (!template) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [template, onClose]);

  if (!template) return null;

  const category = categoryOf(template);

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={template.title}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} aria-hidden />
      <aside className="absolute right-0 top-0 h-full w-full max-w-md bg-white shadow-2xl overflow-y-auto animate-in slide-in-from-right duration-200">
        <div className="sticky top-0 bg-white border-b border-slate-100 p-4 flex justify-between items-start gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${template.is_active ? 'bg-sky-100 text-sky-700' : 'bg-slate-200 text-slate-600'}`}>
                {t(`taskTemplate.cat.${category}`)}
              </span>
              <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${template.is_active ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500'}`}>
                {template.is_active ? t('taskTemplate.statusActive') : t('taskTemplate.statusDeprecated')}
              </span>
            </div>
            <h3 className="text-base font-bold text-slate-800 mt-1.5 truncate">{template.title}</h3>
            <p className="text-[11px] text-slate-400">
              XP {template.xp_reward}
              {template.difficulty ? ' · ' + '★'.repeat(template.difficulty) + '☆'.repeat(5 - template.difficulty) : ''}
              {' · '}{t('taskTemplate.poolPolicy')}:{' '}{t(`taskTemplate.poolPolicyValue.${template.pool_policy}`)}
            </p>
          </div>
          <div className="flex gap-1 shrink-0">
            <button
              onClick={() => onEdit(template)}
              className="p-2 rounded-lg text-sky-700 hover:bg-sky-50"
              aria-label={t('taskTemplate.edit')}
            >
              <Pencil size={16} />
            </button>
            <button onClick={onClose} className="p-2 rounded-lg text-slate-400 hover:bg-slate-100" aria-label={t('common.close')}>
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="p-4 space-y-5 text-sm">
          {template.description && (
            <section>
              <h4 className="text-xs font-bold text-slate-500 uppercase mb-1">{t('addTask.descriptionLore')}</h4>
              <p className="text-slate-700 whitespace-pre-wrap">{template.description}</p>
            </section>
          )}

          <section>
            <h4 className="text-xs font-bold text-slate-500 uppercase mb-1.5">
              🕘 {t('taskTemplate.triggerSection')}（{template.triggers.length}）
            </h4>
            {template.triggers.length === 0 ? (
              <p className="text-xs text-slate-400">{t('taskTemplate.noTriggers')}</p>
            ) : (
              <ul className="space-y-2">
                {template.triggers.map(trigger => (
                  <li key={trigger.id} className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-xs">
                    <div className="font-semibold text-slate-700">{describeTrigger(trigger, t)}</div>
                    <div className="text-slate-400 mt-0.5">
                      {describeRange(trigger, t)}
                      {!trigger.is_active && ' · ' + t('taskTemplate.ruleInactive')}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h4 className="text-xs font-bold text-slate-500 uppercase mb-1.5">⏱ {t('taskTemplate.windowSection')}</h4>
            <p className="text-xs text-slate-700 bg-rose-50 border border-rose-100 rounded-lg p-2.5">
              {describeTimeWindow(template, t)}
            </p>
          </section>

          <section>
            <h4 className="text-xs font-bold text-slate-500 uppercase mb-1.5">{t('taskTemplate.recentInstances')}</h4>
            {recent === null ? (
              <p className="text-xs text-slate-400 animate-pulse">{t('common.loading')}</p>
            ) : recent.length === 0 ? (
              <p className="text-xs text-slate-400">{t('taskTemplate.noInstances')}</p>
            ) : (
              <ul className="space-y-1.5">
                {recent.map(task => (
                  <li key={task.id} className="flex items-center gap-2 text-xs">
                    <span className={`w-2 h-2 rounded-full shrink-0 ${STATUS_DOT[task.status]}`} aria-hidden />
                    <span className="text-slate-700 font-medium truncate flex-1">{task.title}</span>
                    <span className="text-slate-400 shrink-0">
                      {task.generated_for_date ?? task.created_at.slice(0, 10)} · {t(`taskStatus.${task.status}`)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </aside>
    </div>
  );
};

export default TaskTemplateDetailDrawer;
