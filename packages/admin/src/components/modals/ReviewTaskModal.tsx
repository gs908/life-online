
import React, { useState, useEffect } from 'react';
import { Task } from '../../types';
import { evaluateTaskProof } from '../../services/geminiService';
import { Star, Sparkles } from 'lucide-react';

interface ReviewTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  task: Task | undefined;
  onApprove: (taskId: string, rating: number, comment: string) => void;
}

const ReviewTaskModal: React.FC<ReviewTaskModalProps> = ({ isOpen, onClose, task, onApprove }) => {
  const [reviewRating, setReviewRating] = useState(5);
  const [reviewComment, setReviewComment] = useState('');
  const [isEvaluating, setIsEvaluating] = useState(false);

  // Reset and auto-evaluate when modal opens
  useEffect(() => {
    if (isOpen && task) {
      setReviewRating(5);
      setReviewComment('');
      
      if (task.proofImage) {
        setIsEvaluating(true);
        evaluateTaskProof(task.title, task.proofImage).then(res => {
          setIsEvaluating(false);
          if (res) {
            setReviewRating(res.rating);
            setReviewComment(res.comment);
          }
        });
      }
    }
  }, [isOpen, task]);

  if (!isOpen || !task) return null;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden">
        <div className="p-6">
          <h3 className="text-xl font-bold mb-4">Review Submission: {task.title}</h3>

          {/* Proof Display */}
          <div className="bg-slate-100 rounded-lg p-2 mb-4 flex justify-center">
            {task.proofImage ? (
              <img src={task.proofImage} className="max-h-64 object-contain rounded" alt="Proof" />
            ) : (
              <div className="p-8 text-slate-400 italic">No image provided</div>
            )}
          </div>

          {/* AI Evaluation */}
          {isEvaluating && (
            <div className="bg-purple-50 p-3 rounded mb-4 text-purple-700 text-xs flex items-center gap-2 animate-pulse">
              <Sparkles size={14} /> AI is evaluating the proof...
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="text-sm font-bold text-slate-700 block mb-1">Quality Rating (Stars)</label>
              <div className="flex gap-2">
                {[1, 2, 3, 4, 5].map(star => (
                  <button key={star} onClick={() => setReviewRating(star)} className={`transition-transform hover:scale-110 ${star <= reviewRating ? 'text-yellow-400' : 'text-slate-200'}`}>
                    <Star size={32} fill="currentColor" />
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-sm font-bold text-slate-700 block mb-1">Comment</label>
              <input className="w-full border p-2 rounded" value={reviewComment} onChange={e => setReviewComment(e.target.value)} placeholder="Great job!" />
            </div>
          </div>
        </div>
        <div className="p-4 bg-slate-50 border-t flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold">Close</button>
          <button 
            onClick={() => onApprove(task.id, reviewRating, reviewComment)} 
            className="px-6 py-2 bg-yellow-500 text-white font-bold rounded shadow hover:bg-yellow-600"
          >
            Approve & Grant XP
          </button>
        </div>
      </div>
    </div>
  );
};

export default ReviewTaskModal;
