import React from 'react';
import { useTranslation } from 'react-i18next';
import type { TaskRead } from '../services/api';
import { TaskStatus, UserRole } from '../types';
import { Clock, CheckCircle, ShieldAlert, Users, Camera, Star, Play, AlertTriangle, Coins } from 'lucide-react';

interface QuestCardProps {
  task: TaskRead;
  role: UserRole;
  isActive?: boolean;
  /** 已排期（`generated_for_date > 今天`）：孩子端看不到也接不了，父母端必须标出来 */
  scheduled?: boolean;
  onAccept: (id: string) => void;
  onSubmit: (id: string) => void;
  onApprove: (id: string) => void;
  onDelete?: (id: string) => void;
  onAbandon?: (id: string) => void;
  /** 微调难度/押金/经验值（契约 §6B：PATCH /scn/task-instances/{id}） */
  onTune?: (id: string) => void;
}

/**
 * 任务卡（阶段③）：数据源为后端 TaskRead。
 * 本地 XP 倍率动态计算已删除（docs/10 §4 阶段③）——评分倍率/超时惩罚/快速加成
 * 由后端 approve 计算并写入 xp_awarded，前端不再预演。
 */
const QuestCard: React.FC<QuestCardProps> = ({ task, role, isActive, scheduled, onAccept, onSubmit, onApprove, onDelete, onAbandon, onTune }) => {
  const { t } = useTranslation();

  /** 驳回展示态（DEV-57）：后端在 IN_PROGRESS 上以 rejected 派生，重交后自动回落 */
  const rejectedInProgress = task.status === TaskStatus.IN_PROGRESS && !!task.rejected;

  /**
   * 头部日期小标签（DEV-65 块 B）。三种口径，统一取 MM-DD：
   * 已完成 → 实际完成日；待审核 → 提交日；其余 → 逻辑日（排期日）。
   * 已排期任务下方已有角标表达同一信息，这里返回 null 不重复显示。
   */
  const dateLabel = (() => {
    const mmdd = (raw: string | null | undefined) => (raw ? raw.slice(5, 10) : null);
    if (task.status === TaskStatus.COMPLETED) {
      const date = mmdd(task.completed_at ?? task.generated_for_date);
      return date ? { key: 'questCard.completedOn', date } : null;
    }
    if (task.status === TaskStatus.PENDING_REVIEW) {
      const date = mmdd(task.submitted_at ?? task.generated_for_date);
      return date ? { key: 'questCard.submittedOn', date } : null;
    }
    if (scheduled) return null;
    const date = mmdd(task.generated_for_date);
    return date ? { key: 'taskTemplate.scheduledBadge', date } : null;
  })();

  const getTypeColor = (type: TaskRead['type']) => {
    switch (type) {
      case 'CHALLENGE': return 'border-red-400 bg-red-50';
      case 'DAILY': return 'border-blue-300 bg-blue-50';
      case 'TIMED': return 'border-orange-300 bg-orange-50';
      case 'COOP': return 'border-purple-300 bg-purple-50';
      case 'CHAIN': return 'border-amber-300 bg-amber-50';
      default: return 'border-slate-200 bg-white';
    }
  };

  const getStatusBadge = () => {
    switch (task.status) {
      case TaskStatus.AVAILABLE: return <span className="bg-green-100 text-green-700 px-2 py-0.5 rounded text-xs font-bold">{t('taskStatus.AVAILABLE')}</span>;
      case TaskStatus.IN_PROGRESS: return rejectedInProgress
        ? <span className="bg-red-100 text-red-700 px-2 py-0.5 rounded text-xs font-bold">{t('taskStatus.REJECTED')}</span>
        : <span className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded text-xs font-bold animate-pulse">{t('taskStatus.IN_PROGRESS')}</span>;
      case TaskStatus.PENDING_REVIEW: return <span className="bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded text-xs font-bold">{t('taskStatus.PENDING_REVIEW')}</span>;
      case TaskStatus.COMPLETED: return <span className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded text-xs font-bold">{t('taskStatus.COMPLETED')}</span>;
      case TaskStatus.EXPIRED: return <span className="bg-red-100 text-red-600 px-2 py-0.5 rounded text-xs font-bold">{t('taskStatus.EXPIRED')}</span>;
    }
  };

  return (
    <div className={`relative p-4 rounded-xl border-l-4 shadow-sm flex flex-col gap-2 transition-all duration-300
        ${isActive ? 'ring-4 ring-yellow-400/50 z-10 shadow-xl' : 'hover:-translate-y-1'}
        ${getTypeColor(task.type)}`}>

      {isActive && (
          <div className="absolute -top-3 left-1/2 transform -translate-x-1/2 bg-yellow-500 text-white text-xs font-bold px-3 py-1 rounded-full shadow flex items-center gap-1">
              <Play size={10} fill="currentColor" /> {t('questCard.currentQuest')}
          </div>
      )}

      <div className="flex justify-between items-start">
        <div className="flex gap-2 items-center">
            {task.type === 'CHALLENGE' && <ShieldAlert size={16} className="text-red-500" />}
            {task.type === 'COOP' && <Users size={16} className="text-purple-500" />}
            {task.type === 'TIMED' && <Clock size={16} className="text-orange-500" />}
            <span className="text-xs uppercase font-bold text-slate-500 tracking-wider">{t(`taskType.${task.type}`)}</span>
            {/* 已排期角标（契约 §6B）：未来日期的实例孩子端不可见，不标出来家长会当成"孩子没做" */}
            {scheduled && (
              <span className="shrink-0 whitespace-nowrap text-[10px] font-bold bg-sky-100 text-sky-700 px-2 py-0.5 rounded-full">
                {t('taskTemplate.scheduledBadge', { date: task.generated_for_date?.slice(5, 10) })}
              </span>
            )}
            {/* 日期小标签（DEV-65 块 B）：与排期角标同款同格式，已排期时不出现在此（角标已表达） */}
            {dateLabel && (
              <span className="shrink-0 whitespace-nowrap text-[10px] font-bold bg-sky-100 text-sky-700 px-2 py-0.5 rounded-full">
                {t(dateLabel.key, { date: dateLabel.date })}
              </span>
            )}
        </div>
        <div className="flex items-center gap-2">
            <div className="text-xs font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-600">
                 +{task.xp_reward} {t('common.xp')}
            </div>
            {/* 已驳回徽标即使作为「当前任务」高亮也照常显示（否则驳回事实被 isActive 隐藏） */}
            {(!isActive || rejectedInProgress) && getStatusBadge()}
        </div>
      </div>

      <div>
        <h3 className="font-bold text-lg text-slate-800 leading-tight">{task.title}</h3>
        {task.lore_snippet && <p className="text-xs italic text-slate-500 mt-1 border-l-2 border-slate-300 pl-2">"{task.lore_snippet}"</p>}
        <p className="text-sm text-slate-700 mt-2">{task.description}</p>

        {/* 驳回原因（DEV-57）：家长填写的 review_comment；引导孩子修改后重交（重交按钮沿用 IN_PROGRESS 分支） */}
        {rejectedInProgress && (
          <div className="mt-2 flex items-start gap-1.5 text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-2 py-1.5" role="note">
            <AlertTriangle size={14} className="shrink-0 mt-0.5" aria-hidden />
            <span>
              <span className="font-bold">{t('questCard.rejectReasonLabel')}</span>
              {task.review_comment}
              <span className="block mt-0.5 text-red-600/80">{t('questCard.rejectResubmitHint')}</span>
            </span>
          </div>
        )}

        {/* Time & Cost Info */}
        <div className="flex flex-wrap gap-2 mt-2">
            {task.time_deposit > 0 && task.status === TaskStatus.AVAILABLE && (
                 <p className="text-xs font-bold text-slate-600 flex items-center gap-1 bg-slate-100 px-2 py-1 rounded">
                    <Coins size={12} className="text-yellow-500"/> {t('questCard.deposit')}: {task.time_deposit}
                 </p>
            )}

            {task.deadline && <p className="text-xs text-red-500 flex items-center gap-1"><Clock size={12}/> {t('questCard.due')}: {new Date(task.deadline).toLocaleDateString()}</p>}
            {task.required_start_time && (
                <p className="text-xs font-bold flex items-center gap-1 text-orange-600">
                    <AlertTriangle size={12}/> {t('questCard.startBy')}: {task.required_start_time}
                </p>
            )}
        </div>
      </div>

      {/* 凭证缩略图（阶段⑤）：proof_url 由后端按 object_key 现算 ——
          MinIO 模式为带签名的临时 URL，local 模式为稳定路径，前端无需区分 */}
      {task.proof_url && (task.status === TaskStatus.PENDING_REVIEW || task.status === TaskStatus.COMPLETED) && (
        <a href={task.proof_url} target="_blank" rel="noreferrer" className="mt-2 block">
          <img src={task.proof_url} alt={t('reviewTask.proofAlt')} className="h-20 object-cover rounded-lg border border-slate-200 hover:opacity-80 transition-opacity" />
        </a>
      )}

      {/* Action Buttons */}
      <div className="mt-2 flex gap-2 justify-end items-center">

        {/* Child Actions */}
        {role === UserRole.CHILD && task.status === TaskStatus.AVAILABLE && (
           <button onClick={() => onAccept(task.id)} className="bg-blue-600 text-white text-sm px-4 py-2 rounded-lg font-bold hover:bg-blue-700 active:scale-95 transition-all shadow-md">
             {t('questCard.accept')}
           </button>
        )}

        {role === UserRole.CHILD && task.status === TaskStatus.IN_PROGRESS && (
           <>
               <button onClick={() => onAbandon && onAbandon(task.id)} className="text-red-400 hover:text-red-600 text-xs font-bold px-2">
                    {t('questCard.abandon')}
               </button>
               <button onClick={() => onSubmit(task.id)} className="bg-green-600 text-white text-sm px-4 py-2 rounded-lg font-bold hover:bg-green-700 flex items-center gap-2 active:scale-95 transition-all shadow-md">
                    <Camera size={16} /> {t('questCard.submitProof')}
               </button>
           </>
        )}

        {/* Parent Actions */}
        {role === UserRole.PARENT && task.status === TaskStatus.PENDING_REVIEW && (
           <button onClick={() => onApprove(task.id)} className="bg-yellow-500 text-white text-sm px-4 py-2 rounded-lg font-bold hover:bg-yellow-600 flex items-center gap-2 active:scale-95 transition-all shadow-md">
             <CheckCircle size={16} /> {t('questCard.review')}
           </button>
        )}

        {role === UserRole.PARENT && onTune && task.status === TaskStatus.AVAILABLE && (
            <button onClick={() => onTune(task.id)} className="text-sky-600 hover:text-sky-800 text-xs font-bold underline">
                {t('tune.entry')}
            </button>
        )}

        {role === UserRole.PARENT && onDelete && task.status !== TaskStatus.PENDING_REVIEW && (
            <button onClick={() => onDelete(task.id)} className="text-red-400 hover:text-red-600 text-xs underline">
                {t('common.delete')}
            </button>
        )}
      </div>

      {/* Completed State（评分与实发 XP 均来自后端） */}
      {task.status === TaskStatus.COMPLETED && (
          <div className="flex items-center gap-1 text-yellow-500 mt-2">
            {[...Array(5)].map((_, i) => (
                <Star key={i} size={16} fill={i < (task.rating || 0) ? "currentColor" : "none"} />
            ))}
            <span className="text-xs text-slate-400 ml-2">
              {t('questCard.verified')}{task.xp_awarded != null ? ` +${task.xp_awarded} ${t('common.xp')}` : ''}
            </span>
          </div>
      )}
    </div>
  );
};

export default QuestCard;
