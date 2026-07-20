
import React, { useState } from 'react';
import { Task, TaskType, TaskStatus } from '../../types';
import { generateQuestSuggestion } from '../../services/geminiService';
import { X, Plus, BrainCircuit, Info } from 'lucide-react';

interface AddTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (task: Task) => void;
  narrativeContext: string;
  seasonId: string;
  childLevel: number;
}

const AddTaskModal: React.FC<AddTaskModalProps> = ({ isOpen, onClose, onAdd, narrativeContext, seasonId, childLevel }) => {
  const [newTaskTitle, setNewTaskTitle] = useState('');
  const [newTaskDesc, setNewTaskDesc] = useState('');
  const [newTaskXP, setNewTaskXP] = useState(50);
  const [newTaskType, setNewTaskType] = useState<TaskType>(TaskType.DAILY);
  
  // AI State
  const [aiPrompt, setAiPrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);

  if (!isOpen) return null;

  const handleGenerateQuest = async () => {
    if (!aiPrompt) return;
    setIsGenerating(true);
    const suggestion = await generateQuestSuggestion(aiPrompt, childLevel, narrativeContext);
    setIsGenerating(false);

    if (suggestion) {
      setNewTaskTitle(suggestion.title);
      setNewTaskDesc(`${suggestion.description}\n\nLore: ${suggestion.loreSnippet}`);
      setNewTaskXP(suggestion.xpReward);
      setNewTaskType(suggestion.type);
    }
  };

  const handleSubmit = () => {
    const newTask: Task = {
      id: Math.random().toString(36).substr(2, 9),
      seasonId: seasonId,
      title: newTaskTitle,
      description: newTaskDesc,
      xpReward: newTaskXP,
      type: newTaskType,
      status: TaskStatus.AVAILABLE,
      reminderMessage: "Time is running out, hero!",
      reminderMinutesBefore: 15
    };
    onAdd(newTask);
    
    // Reset
    setNewTaskTitle('');
    setNewTaskDesc('');
    setAiPrompt('');
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200">
        <div className="bg-slate-900 text-white p-4 flex justify-between items-center">
          <h3 className="font-bold text-lg flex items-center gap-2"><Plus size={20} /> Create New Quest</h3>
          <button onClick={onClose}><X /></button>
        </div>
        <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
          {/* AI Generator */}
          <div className="bg-purple-50 p-4 rounded-xl border border-purple-100">
            <label className="text-xs font-bold text-purple-700 uppercase mb-2 block flex items-center gap-1">
              <BrainCircuit size={14} /> AI Quest Generator
            </label>
            <p className="text-xs text-slate-500 mb-2 italic">Based on current theme: "{narrativeContext.substring(0, 50)}..."</p>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="e.g. Clean Room, Practice Math..."
                className="flex-1 text-sm p-2 rounded border border-purple-200 focus:outline-none focus:border-purple-500"
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
              />
              <button
                disabled={isGenerating || !aiPrompt}
                onClick={handleGenerateQuest}
                className="bg-purple-600 text-white px-3 py-2 rounded font-bold text-xs disabled:opacity-50"
              >
                {isGenerating ? 'Thinking...' : 'Generate'}
              </button>
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-bold text-slate-700">Quest Title</label>
            <input className="w-full border p-2 rounded" value={newTaskTitle} onChange={e => setNewTaskTitle(e.target.value)} placeholder="Quest Name" />
          </div>

          <div className="flex gap-4">
            <div className="space-y-2 flex-1">
              <label className="text-sm font-bold text-slate-700">Type</label>
              <select className="w-full border p-2 rounded" value={newTaskType} onChange={e => setNewTaskType(e.target.value as TaskType)}>
                {Object.values(TaskType).map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="space-y-2 w-24">
              <label className="text-sm font-bold text-slate-700">XP</label>
              <input type="number" className="w-full border p-2 rounded" value={newTaskXP} onChange={e => setNewTaskXP(Number(e.target.value))} />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-bold text-slate-700">Description / Lore</label>
            <textarea className="w-full border p-2 rounded h-24" value={newTaskDesc} onChange={e => setNewTaskDesc(e.target.value)} placeholder="Description..." />
          </div>

          <div className="p-3 bg-orange-50 rounded border border-orange-100">
            <div className="flex items-center gap-2 mb-2">
              <Info size={14} className="text-orange-500" />
              <span className="text-xs font-bold text-orange-700">Timed Task Settings</span>
            </div>
            <div className="text-xs text-slate-500">
              (Optional) Add reminders or deadlines if the task is time-sensitive.
              Currently not editable in this demo form, but handled by AI.
            </div>
          </div>
        </div>
        <div className="p-4 bg-slate-50 flex justify-end gap-2 border-t">
          <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold hover:bg-slate-200 rounded">Cancel</button>
          <button onClick={handleSubmit} className="px-4 py-2 bg-green-600 text-white font-bold rounded hover:bg-green-700 shadow-md transform active:scale-95">Post Quest</button>
        </div>
      </div>
    </div>
  );
};

export default AddTaskModal;
