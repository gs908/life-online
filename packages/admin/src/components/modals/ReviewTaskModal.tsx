import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../../services/api';
import type { ProofKind, TaskRead } from '../../services/api';
import { ChevronLeft, ChevronRight, Star, Sparkles, Music } from 'lucide-react';

interface ReviewTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  task: TaskRead | undefined;
  onApprove: (taskId: string, rating: number, comment: string) => void;
  /** 驳回（DEV-57）：reason 必填（空则按钮禁用），后端写入 review_comment 并把实例退回 IN_PROGRESS */
  onReject: (taskId: string, comment: string) => void;
  approving?: boolean;
}

/** 展示用证据项：TaskRead.proofs 归一化后的最小形状 */
interface ProofViewItem {
  kind: ProofKind;
  url: string;
}

/**
 * 审核弹窗（阶段③+⑥）：证据来自 TaskRead.proofs（DEV-33 块 E 多证据：图集可切换 + 视频播放；DEV-43 音频占位/播放控件）；
 * proofs 为空时回退单值 proof_url（过渡字段 = 首个证据，兼容存量数据）。
 * AI 辅助评分走 POST /scn/ai/evaluate-proof，契约要求 image_data_url —— 只对首个图片证据送评，
 * 纯视频/无证据任务跳过 AI（评分只是辅助建议，失败不阻塞人工审核）。
 * 打开弹窗不再自动调 LLM（DEV-66）：评语默认空，由「✨ 生成」按钮显式触发，避免驳回场景误用 AI 文案。
 *
 * 驳回（DEV-57）：与「评语」分开的独立输入框 —— 评语会被 AI 评分预填，复用会让 AI 文案被当成驳回原因。
 * rejectComment 必填，为空时驳回按钮禁用。
 */
const ReviewTaskModal: React.FC<ReviewTaskModalProps> = ({ isOpen, onClose, task, onApprove, onReject, approving }) => {
  const { t } = useTranslation();
  const [reviewRating, setReviewRating] = useState(5);
  const [reviewComment, setReviewComment] = useState('');
  const [rejectComment, setRejectComment] = useState('');
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [evaluateError, setEvaluateError] = useState<string | null>(null);
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

  /** 首个图片证据 URL：AI 评分输入；纯视频任务返回 null（跳过 AI） */
  const firstImageUrl = useMemo(
    () => proofs.find((p) => p.kind === 'IMAGE')?.url ?? null,
    [proofs],
  );

  // 打开弹窗只重置表单；AI 评估改为「✨ 生成」手动触发（DEV-66），驳回场景不再隐式调用 LLM。
  useEffect(() => {
    if (isOpen && task) {
      setReviewRating(5);
      setReviewComment('');
      setRejectComment('');
      setEvaluateError(null);
      setActiveIndex(0);
    }
  }, [isOpen, task]);

  /** 「✨ 生成」：取回首图 → dataURL → 送评 → 回填评分与评语（失败不阻塞人工审核） */
  const handleGenerate = useCallback(() => {
    if (!task || !firstImageUrl || isEvaluating) return;
    setIsEvaluating(true);
    setEvaluateError(null);
    // 前端只持有证据 URL；evaluate-proof 契约要求 image_data_url，取回图片转 data URL 再送评
    fetch(firstImageUrl)
      .then(res => {
        // 404/403（如预签名 URL 过期、dev 无反代）不能把错误页 HTML 当图片送评（review 🟡-2）
        if (!res.ok) throw new Error(`proof fetch failed: ${res.status}`);
        return res.blob();
      })
      .then(
        blob =>
          new Promise<string>((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result as string);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
          })
      )
      .then(image_data_url => api.ai.evaluateProof({ task_title: task.title, image_data_url }))
      .then(res => {
        setReviewRating(res.rating);
        setReviewComment(res.comment);
      })
      .catch(err => {
        // 503(能力未启用/未配置)单独提示,与 AddTaskModal 口径一致
        if (err instanceof ApiError && err.errorCode === 'service_unavailable') {
          setEvaluateError(t('addTask.aiNotConfigured'));
        } else {
          setEvaluateError(t('reviewTask.evaluateFailed'));
        }
      })
      .finally(() => setIsEvaluating(false));
  }, [task, firstImageUrl, isEvaluating, t]);

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

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden">
        <div className="p-6">
          <h3 className="text-xl font-bold mb-4">{t('reviewTask.title', { title: task.title })}</h3>

          {/* Proof Display（DEV-33 块 E：图集切换 + 视频播放） */}
          {proofs.length ? (
            <div className="bg-slate-100 rounded-lg p-2 mb-4">
              <div className="relative flex justify-center min-h-[16rem] items-center">
                {active && active.kind === 'VIDEO' ? (
                  <video
                    key={active.url}
                    src={active.url}
                    controls
                    playsInline
                    preload="metadata"
                    className="max-h-64 max-w-full rounded"
                    aria-label={t('reviewTask.proofVideoAlt', { index: activeIndex + 1, total: proofs.length })}
                  />
                ) : active && active.kind === 'AUDIO' ? (
                  <div
                    key={active.url}
                    className="flex flex-col items-center gap-3 py-6"
                    aria-label={t('reviewTask.proofAudioAlt', { index: activeIndex + 1, total: proofs.length })}
                  >
                    <Music size={40} className="text-slate-400" aria-hidden />
                    <span className="text-sm text-slate-500">
                      {t('reviewTask.proofAudioAlt', { index: activeIndex + 1, total: proofs.length })}
                    </span>
                    <audio key={active.url} src={active.url} controls preload="metadata" className="w-full max-w-xs" />
                  </div>
                ) : (
                  active && (
                    <img
                      key={active.url}
                      src={active.url}
                      className="max-h-64 object-contain rounded"
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
            <div className="bg-slate-100 rounded-lg p-2 mb-4 flex justify-center">
              <div className="p-8 text-slate-400 italic">{t('reviewTask.noImage')}</div>
            </div>
          )}

          {/* AI Evaluation */}
          {isEvaluating && (
            <div className="bg-purple-50 p-3 rounded mb-4 text-purple-700 text-xs flex items-center gap-2 animate-pulse">
              <Sparkles size={14} /> {t('reviewTask.evaluating')}
            </div>
          )}
          {evaluateError && (
            <div className="bg-orange-50 p-3 rounded mb-4 text-orange-700 text-xs" data-testid="evaluate-error">
              {evaluateError}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="text-sm font-bold text-slate-700 block mb-1">{t('reviewTask.qualityRating')}</label>
              <div className="flex gap-2">
                {[1, 2, 3, 4, 5].map(star => (
                  <button key={star} onClick={() => setReviewRating(star)} className={`transition-transform hover:scale-110 ${star <= reviewRating ? 'text-yellow-400' : 'text-slate-200'}`}>
                    <Star size={32} fill="currentColor" />
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-sm font-bold text-slate-700 block mb-1">{t('reviewTask.comment')}</label>
              <div className="flex items-center gap-2">
                <input className="flex-1 border p-2 rounded" value={reviewComment} onChange={e => setReviewComment(e.target.value)} placeholder={t('reviewTask.commentPlaceholder')} />
                <button
                  type="button"
                  onClick={handleGenerate}
                  disabled={isEvaluating || !firstImageUrl}
                  title={!firstImageUrl ? t('reviewTask.noImageForAi') : undefined}
                  className="shrink-0 flex items-center gap-1 px-3 py-2 rounded border border-purple-300 text-purple-700 font-bold text-sm hover:bg-purple-50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Sparkles size={14} />
                  {t('reviewTask.generateComment')}
                </button>
              </div>
              {!firstImageUrl && (
                <p className="text-xs text-slate-500 mt-1">{t('reviewTask.noImageForAi')}</p>
              )}
            </div>

            {/* 驳回原因（DEV-57）：独立输入框，与 AI 预填的「评语」分离；必填，空则驳回按钮禁用 */}
            <div className="border-t border-slate-200 pt-4">
              <label htmlFor="reviewTask-reject-reason" className="text-sm font-bold text-slate-700 block mb-1">
                {t('reviewTask.rejectReason')}
              </label>
              <textarea
                id="reviewTask-reject-reason"
                className="w-full border p-2 rounded"
                rows={2}
                value={rejectComment}
                onChange={e => setRejectComment(e.target.value)}
                placeholder={t('reviewTask.rejectReasonPlaceholder')}
                aria-describedby="reviewTask-reject-hint"
              />
              <p id="reviewTask-reject-hint" className="text-xs text-slate-500 mt-1">
                {t('reviewTask.rejectReasonRequired')}
              </p>
            </div>
          </div>
        </div>
        <div className="p-4 bg-slate-50 border-t flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold">{t('common.close')}</button>
          <button
            onClick={() => onReject(task.id, rejectComment.trim())}
            disabled={approving || !rejectComment.trim()}
            className="px-6 py-2 bg-white text-red-600 border border-red-300 font-bold rounded hover:bg-red-50 disabled:opacity-50"
          >
            {t('reviewTask.reject')}
          </button>
          <button
            onClick={() => onApprove(task.id, reviewRating, reviewComment)}
            disabled={approving}
            className="px-6 py-2 bg-yellow-500 text-white font-bold rounded shadow hover:bg-yellow-600 disabled:opacity-50"
          >
            {approving ? t('common.loading') : t('reviewTask.approve')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ReviewTaskModal;
