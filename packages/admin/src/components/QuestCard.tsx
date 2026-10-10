import React from 'react';
import { useTranslation } from 'react-i18next';
import type { TaskRead } from '../services/api';
import { TaskStatus, UserRole } from '../types';
import { Clock, CheckCircle, ShieldAlert, Users, Camera, Star, Play, AlertTriangle, Coins } from 'lucide-react';

interface QuestCardProps {
  task: TaskRead;
  role: UserRole;
  isActive?: boolean;
  onAccept: (id: string) => void;
  onSubmit: (id: string) => void;
  onApprove: (id: string) => void;
  onDelete?: (id: string) => void;
  onAbandon?: (id: string) => void;
}

/**
 * 任务卡（阶段③）：数据源为后端 TaskRead。
 * 本地 XP 倍率动态计算已删除（docs/10 §4 阶段③）——评分倍率/超时惩罚/快速加成
 * 由后端 approve 计算并写入 xp_awarded，前端不再预演。
 */
const QuestCard: React.FC<QuestCardProps> = ({ task, role, isActive, onAccept, onSubmit, onApprove, onDelete, onAbandon }) => {
  const { t } = useTranslation();

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
      case TaskStatus.IN_PROGRESS: return <span className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded text-xs font-bold animate-pulse">{t('taskStatus.IN_PROGRESS')}</span>;
      case TaskStatus.PENDING_REVIEW: return <span className="bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded text-xs font-bold">{t('taskStatus.PENDING_REVIEW')}</span>;
      case TaskStatus.COMPLETED: return <span className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded text-xs font-bold">{t('taskStatus.COMPLETED')}</span>;
      case TaskStatus.EXPIRED: return <span className="bg-red-100 text-red-600 px-2 py-0.5 rounded text-xs font-bold">{t('taskStatus.EXPIRED')}</span>;
    }
  };

  return (
    <div className={`relative p-4 rounded-xl border-l-4 shadow-sm flex flex-col gap-2 transition-all duration-300
        ${isActive ? 'scale-105 ring-4 ring-yellow-400/50 z-10 shadow-xl' : 'hover:-translate-y-1'}
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
        </div>
        <div className="flex items-center gap-2">
            <div className="text-xs font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-600">
                 +{task.xp_reward} {t('common.xp')}
            </div>
            {!isActive && getStatusBadge()}
        </div>
      </div>

      <div>
        <h3 className="font-bold text-lg text-slate-800 leading-tight">{task.title}</h3>
        {task.lore_snippet && <p className="text-xs italic text-slate-500 mt-1 border-l-2 border-slate-300 pl-2">"{task.lore_snippet}"</p>}
        <p className="text-sm text-slate-700 mt-2">{task.description}</p>

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
