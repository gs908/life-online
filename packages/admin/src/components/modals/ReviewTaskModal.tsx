import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../../services/api';
import type { TaskRead } from '../../services/api';
import { Star, Sparkles } from 'lucide-react';

interface ReviewTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  task: TaskRead | undefined;
  onApprove: (taskId: string, rating: number, comment: string) => void;
  approving?: boolean;
}

/**
 * 审核弹窗（阶段③+⑥）：证明图来自 TaskRead.proof_url（上传链路阶段⑤完善展示细节）。
 * AI 辅助评分走 POST /scn/ai/evaluate-proof（后端当前为纯文本评分,结果仅供参考）。
 */
const ReviewTaskModal: React.FC<ReviewTaskModalProps> = ({ isOpen, onClose, task, onApprove, approving }) => {
  const { t } = useTranslation();
  const [reviewRating, setReviewRating] = useState(5);
  const [reviewComment, setReviewComment] = useState('');
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [evaluateError, setEvaluateError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && task) {
      setReviewRating(5);
      setReviewComment('');
      setEvaluateError(null);

      if (task.proof_url) {
        setIsEvaluating(true);
        // 阶段③后前端只持有 proof_url；evaluate-proof 契约要求 image_data_url，
        // 取回图片转 data URL 再送评（评分只是辅助建议,失败不阻塞人工审核）
        fetch(task.proof_url)
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
      }
    }
  }, [isOpen, task, t]);

  if (!isOpen || !task) return null;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden">
        <div className="p-6">
          <h3 className="text-xl font-bold mb-4">{t('reviewTask.title', { title: task.title })}</h3>

          {/* Proof Display */}
          <div className="bg-slate-100 rounded-lg p-2 mb-4 flex justify-center">
            {task.proof_url ? (
              <img src={task.proof_url} className="max-h-64 object-contain rounded" alt={t('reviewTask.proofAlt')} />
            ) : (
              <div className="p-8 text-slate-400 italic">{t('reviewTask.noImage')}</div>
            )}
          </div>

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
              <input className="w-full border p-2 rounded" value={reviewComment} onChange={e => setReviewComment(e.target.value)} placeholder={t('reviewTask.commentPlaceholder')} />
            </div>
          </div>
        </div>
        <div className="p-4 bg-slate-50 border-t flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold">{t('common.close')}</button>
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
