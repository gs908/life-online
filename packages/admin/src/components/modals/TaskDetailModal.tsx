import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { ProofKind, TaskRead } from '../../services/api';
import { ChevronLeft, ChevronRight, Music, Star, X } from 'lucide-react';

interface TaskDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  task: TaskRead | null | undefined;
}

/** 展示用证据项：TaskRead.proofs 归一化后的最小形状（与 ReviewTaskModal 同口径） */
interface ProofViewItem {
  kind: ProofKind;
  url: string;
}

/** 类型徽标配色（与周视图 chip / QuestCard 同色系，保持视觉一致） */
function getTypeBadgeColor(type: TaskRead['type']) {
  switch (type) {
    case 'CHALLENGE': return 'bg-red-100 text-red-700 border-red-200';
    case 'DAILY': return 'bg-blue-100 text-blue-700 border-blue-200';
    case 'TIMED': return 'bg-orange-100 text-orange-700 border-orange-200';
    case 'COOP': return 'bg-purple-100 text-purple-700 border-purple-200';
    case 'CHAIN': return 'bg-amber-100 text-amber-700 border-amber-200';
    default: return 'bg-slate-100 text-slate-700 border-slate-200';
  }
}

/** 状态徽标配色（含 DEV-57 驳回派生态：IN_PROGRESS + rejected） */
function getStatusBadgeColor(task: TaskRead) {
  if (task.status === 'IN_PROGRESS' && task.rejected) return 'bg-red-100 text-red-700';
  switch (task.status) {
    case 'AVAILABLE': return 'bg-green-100 text-green-700';
    case 'IN_PROGRESS': return 'bg-blue-100 text-blue-700';
    case 'PENDING_REVIEW': return 'bg-yellow-100 text-yellow-700';
    case 'COMPLETED': return 'bg-gray-100 text-gray-600';
    case 'EXPIRED': return 'bg-red-100 text-red-600';
    default: return 'bg-slate-100 text-slate-600';
  }
}

/**
 * 任务详情弹窗（DEV-68）：周视图点击任务 chip / 移动端卡片弹出的只读详情。
 * 孩子端与家长端共用，纯展示 —— 不含接取/提交/审核等任何操作按钮（唯一的「关闭」除外）。
 * 证据图集复用 ReviewTaskModal 的切换样式；proofs 为空时回退过渡字段 proof_url。
 */
const TaskDetailModal: React.FC<TaskDetailModalProps> = ({ isOpen, onClose, task }) => {
  const { t } = useTranslation();
  const [activeIndex, setActiveIndex] = useState(0);

  const proofs: ProofViewItem[] = useMemo(() => {
    if (!task) return [];
    const fromProofs = (task.proofs ?? [])
      .filter((p) => p.url)
      .map((p) => ({ kind: p.kind, url: p.url as string }));
    if (fromProofs.length) return fromProofs;
    // 过渡兼容：存量任务只有 proof_url（视为图片）
    return task.proof_url ? [{ kind: 'IMAGE' as const, url: task.proof_url }] : [];
  }, [task]);

  // 打开/换任务时重置图集游标，避免沿用上一条任务的索引
  useEffect(() => {
    if (isOpen) setActiveIndex(0);
  }, [isOpen, task]);

  // Esc 关闭
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  const goPrev = useCallback(
    () => setActiveIndex((i) => (i - 1 + proofs.length) % proofs.length),
    [proofs.length],
  );
  const goNext = useCallback(
    () => setActiveIndex((i) => (i + 1) % proofs.length),
    [proofs.length],
  );

  if (!isOpen || !task) return null;

  const active = proofs[Math.min(activeIndex, proofs.length - 1)];
  const isRejected = task.status === 'IN_PROGRESS' && !!task.rejected;
  const difficulty = task.difficulty
    ? '★'.repeat(Math.min(task.difficulty, 5)) + '☆'.repeat(Math.max(5 - task.difficulty, 0))
    : t('taskDetail.unrated');

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-label={task.title}
    >
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} aria-hidden />
      <div className="relative bg-white rounded-2xl w-full max-w-lg shadow-2xl flex flex-col max-h-[90vh]">
        <div className="p-5 border-b border-slate-100 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-bold uppercase tracking-wider text-slate-400">{t('taskDetail.title')}</p>
            <h3 className="text-lg font-bold text-slate-800 leading-tight mt-0.5">{task.title}</h3>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg text-slate-400 hover:bg-slate-100 shrink-0" aria-label={t('common.close')}>
            <X size={16} />
          </button>
        </div>

        <div className="p-5 space-y-5 text-sm overflow-y-auto">
          {/* 类型 / 状态（驳回态显示「已驳回」而非「冒险中」） */}
          <div className="flex flex-wrap items-center gap-2">
            <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${getTypeBadgeColor(task.type)}`}>
              {t(`taskType.${task.type}`)}
            </span>
            <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${getStatusBadgeColor(task)}`}>
              {t(`taskStatus.${isRejected ? 'REJECTED' : task.status}`)}
            </span>
          </div>

          {task.description && (
            <section>
              <h4 className="text-xs font-bold text-slate-500 uppercase mb-1">{t('taskDetail.description')}</h4>
              <p className="text-slate-700 whitespace-pre-wrap">{task.description}</p>
            </section>
          )}

          {task.lore_snippet && (
            <section>
              <h4 className="text-xs font-bold text-slate-500 uppercase mb-1">{t('taskDetail.lore')}</h4>
              <p className="text-xs italic text-slate-500 border-l-2 border-slate-300 pl-2">"{task.lore_snippet}"</p>
            </section>
          )}

          <section>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
              <div>
                <dt className="text-xs font-bold text-slate-500 uppercase">{t('taskDetail.difficulty')}</dt>
                <dd className="text-slate-800 mt-0.5">{difficulty}</dd>
              </div>
              <div>
                <dt className="text-xs font-bold text-slate-500 uppercase">{t('taskDetail.xpReward')}</dt>
                <dd className="text-slate-800 mt-0.5">+{task.xp_reward} {t('common.xp')}</dd>
              </div>
              <div>
                <dt className="text-xs font-bold text-slate-500 uppercase">{t('taskDetail.deposit')}</dt>
                <dd className="text-slate-800 mt-0.5">{task.time_deposit}</dd>
              </div>
              <div>
                <dt className="text-xs font-bold text-slate-500 uppercase">{t('taskDetail.targetDate')}</dt>
                <dd className="text-slate-800 mt-0.5">{task.generated_for_date ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-xs font-bold text-slate-500 uppercase">{t('taskDetail.completedAt')}</dt>
                <dd className="text-slate-800 mt-0.5">{task.completed_at ? task.completed_at.slice(0, 10) : '—'}</dd>
              </div>
            </dl>
          </section>

          {/* 证据图集（复用 ReviewTaskModal 的切换/缩略条样式，纯展示） */}
          <section>
            <h4 className="text-xs font-bold text-slate-500 uppercase mb-1.5">{t('reviewTask.proofAlt')}</h4>
            {proofs.length ? (
              <div className="bg-slate-100 rounded-lg p-2">
                <div className="relative flex justify-center min-h-[12rem] items-center">
                  {active && active.kind === 'VIDEO' ? (
                    <video
                      key={active.url}
                      src={active.url}
                      controls
                      playsInline
                      preload="metadata"
                      className="max-h-56 max-w-full rounded"
                      aria-label={t('reviewTask.proofVideoAlt', { index: activeIndex + 1, total: proofs.length })}
                    />
                  ) : active && active.kind === 'AUDIO' ? (
                    <div
                      key={active.url}
                      className="flex flex-col items-center gap-3 py-4"
                      aria-label={t('reviewTask.proofAudioAlt', { index: activeIndex + 1, total: proofs.length })}
                    >
                      <Music size={36} className="text-slate-400" aria-hidden />
                      <audio key={active.url} src={active.url} controls preload="metadata" className="w-full max-w-xs" />
                    </div>
                  ) : (
                    active && (
                      <img
                        key={active.url}
                        src={active.url}
                        className="max-h-56 object-contain rounded"
                        alt={t('reviewTask.proofAltWithIndex', { index: activeIndex + 1, total: proofs.length })}
                      />
                    )
                  )}
                  {proofs.length > 1 && (
                    <>
                      <button
                        type="button"
                        onClick={goPrev}
                        aria-label={t('reviewTask.prevProof')}
                        className="absolute left-1 top-1/2 -translate-y-1/2 bg-white/80 hover:bg-white rounded-full p-1 shadow"
                      >
                        <ChevronLeft size={18} />
                      </button>
                      <span className="absolute right-2 bottom-1 text-xs text-slate-500 bg-white/80 rounded px-1.5">
                        {activeIndex + 1} / {proofs.length}
                      </span>
                      <button
                        type="button"
                        onClick={goNext}
                        aria-label={t('reviewTask.nextProof')}
                        className="absolute right-1 top-1/2 -translate-y-1/2 bg-white/80 hover:bg-white rounded-full p-1 shadow"
                      >
                        <ChevronRight size={18} />
                      </button>
                    </>
                  )}
                </div>
                {proofs.length > 1 && (
                  <div className="flex gap-1.5 mt-2 overflow-x-auto" role="tablist" aria-label={t('reviewTask.proofStripAlt')}>
                    {proofs.map((p, i) => (
                      <button
                        key={`${p.url}-${i}`}
                        type="button"
                        role="tab"
                        aria-selected={i === activeIndex}
                        onClick={() => setActiveIndex(i)}
                        className={`shrink-0 w-12 h-12 rounded overflow-hidden border-2 ${i === activeIndex ? 'border-yellow-500' : 'border-transparent opacity-70 hover:opacity-100'}`}
                      >
                        {p.kind === 'VIDEO' ? (
                          <video src={p.url} muted preload="metadata" className="h-full w-full object-cover" />
                        ) : p.kind === 'AUDIO' ? (
                          <span className="flex h-full w-full items-center justify-center bg-slate-200" aria-hidden>
                            <Music size={18} className="text-slate-500" />
                          </span>
                        ) : (
                          <img src={p.url} alt="" className="h-full w-full object-cover" />
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-slate-400 italic">{t('reviewTask.noImage')}</p>
            )}
          </section>

          {/* 评分星级（有评分才展示） */}
          {task.rating != null && (
            <section>
              <h4 className="text-xs font-bold text-slate-500 uppercase mb-1">{t('taskDetail.rating')}</h4>
              <div className="flex items-center gap-1">
                {[...Array(5)].map((_, i) => (
                  <Star
                    key={i}
                    size={16}
                    className={i < task.rating! ? 'text-yellow-400' : 'text-slate-200'}
                    fill={i < task.rating! ? 'currentColor' : 'none'}
                  />
                ))}
                <span className="text-xs text-slate-400 ml-2">{task.rating} / 5</span>
              </div>
            </section>
          )}

          {/* review_comment 双重语义：驳回时是驳回原因，通过后是审核评语 */}
          {task.review_comment && (
            <section>
              <h4 className="text-xs font-bold text-slate-500 uppercase mb-1">
                {isRejected ? t('questCard.rejectReasonLabel') : t('taskDetail.reviewComment')}
              </h4>
              <p className={`whitespace-pre-wrap ${isRejected ? 'text-red-700' : 'text-slate-700'}`}>
                {task.review_comment}
              </p>
            </section>
          )}
        </div>

        <div className="p-4 bg-slate-50 border-t border-slate-100 flex justify-end">
          <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold rounded hover:bg-slate-100">
            {t('common.close')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default TaskDetailModal;