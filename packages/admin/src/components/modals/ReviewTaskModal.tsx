import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { TaskRead } from '../../services/api';
import { Star } from 'lucide-react';

interface ReviewTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  task: TaskRead | undefined;
  onApprove: (taskId: string, rating: number, comment: string) => void;
  approving?: boolean;
}

/**
 * 审核弹窗（阶段③）：证明图来自 TaskRead.proof_url（上传链路阶段⑤完善展示细节）。
 * AI 辅助评分随阶段⑥切到 POST /scn/ai/evaluate-proof；当前为人工星级 + 评语。
 */
const ReviewTaskModal: React.FC<ReviewTaskModalProps> = ({ isOpen, onClose, task, onApprove, approving }) => {
  const { t } = useTranslation();
  const [reviewRating, setReviewRating] = useState(5);
  const [reviewComment, setReviewComment] = useState('');

  useEffect(() => {
    if (isOpen && task) {
      setReviewRating(5);
      setReviewComment('');
    }
  }, [isOpen, task]);

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
