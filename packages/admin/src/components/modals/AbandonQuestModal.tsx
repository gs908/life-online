
import React from 'react';
import { Task } from '../../types';
import { AlertTriangle } from 'lucide-react';

interface AbandonQuestModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  taskTitle?: string;
}

const AbandonQuestModal: React.FC<AbandonQuestModalProps> = ({ isOpen, onClose, onConfirm, taskTitle }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-sm shadow-2xl p-6 text-center animate-in zoom-in duration-200">
        <div className="mx-auto w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mb-4">
          <AlertTriangle className="text-red-600" size={32} />
        </div>
        <h3 className="text-xl font-bold text-slate-900 mb-2">Abandon Current Quest?</h3>
        <p className="text-slate-600 mb-6 text-sm">
          You are currently on <strong>"{taskTitle}"</strong>.<br />
          You can only do one quest at a time. Switching will reset your progress on the current quest.
        </p>
        <div className="flex gap-2 justify-center">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-slate-600 font-bold hover:bg-slate-100">Cancel</button>
          <button onClick={onConfirm} className="px-4 py-2 rounded-lg bg-red-600 text-white font-bold hover:bg-red-700 shadow-lg">Abandon & Switch</button>
        </div>
      </div>
    </div>
  );
};

export default AbandonQuestModal;
