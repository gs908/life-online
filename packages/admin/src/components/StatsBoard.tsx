import React from 'react';
import { useTranslation } from 'react-i18next';
import { Task, TaskStatus, TaskType } from '../types';
import { PieChart, Star, Activity, CheckCircle2, Clock } from 'lucide-react';

interface StatsBoardProps {
  tasks: Task[];
}

const StatsBoard: React.FC<StatsBoardProps> = ({ tasks }) => {
  const { t } = useTranslation();

  // --- CALCULATIONS ---
  const totalTasks = tasks.length;
  const completedTasks = tasks.filter(t => t.status === TaskStatus.COMPLETED);
  const completedCount = completedTasks.length;
  const completionRate = totalTasks > 0 ? Math.round((completedCount / totalTasks) * 100) : 0;
  
  // Star Distribution
  const starCounts = [0, 0, 0, 0, 0]; // 1 to 5 stars
  completedTasks.forEach(t => {
    if (t.rating && t.rating >= 1 && t.rating <= 5) {
      starCounts[t.rating - 1]++;
    }
  });
  const maxStarCount = Math.max(...starCounts, 1);

  // Task Type Breakdown
  const typeCounts: Record<string, number> = {};
  Object.values(TaskType).forEach(type => typeCounts[type] = 0);
  tasks.forEach(t => {
      if (!typeCounts[t.type]) typeCounts[t.type] = 0;
      typeCounts[t.type]++;
  });

  return (
    <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 space-y-6">
      <div className="flex items-center gap-2 border-b border-slate-100 pb-2">
        <Activity className="text-blue-600" />
        <h3 className="text-lg font-bold text-slate-800">{t('stats.title')}</h3>
      </div>

      {/* Top Row: Key Metrics */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-green-50 p-3 rounded-xl border border-green-100 text-center">
            <div className="text-green-600 mb-1 flex justify-center"><CheckCircle2 size={20}/></div>
            <div className="text-2xl font-bold text-green-800">{completedCount}</div>
            <div className="text-xs text-green-600 font-bold uppercase">{t('stats.completed')}</div>
        </div>
        <div className="bg-blue-50 p-3 rounded-xl border border-blue-100 text-center">
            <div className="text-blue-600 mb-1 flex justify-center"><PieChart size={20}/></div>
            <div className="text-2xl font-bold text-blue-800">{completionRate}%</div>
            <div className="text-xs text-blue-600 font-bold uppercase">{t('stats.successRate')}</div>
        </div>
        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100 text-center">
             <div className="text-slate-500 mb-1 flex justify-center"><Clock size={20}/></div>
            <div className="text-2xl font-bold text-slate-700">{totalTasks}</div>
            <div className="text-xs text-slate-500 font-bold uppercase">{t('stats.totalQuests')}</div>
        </div>
      </div>

      {/* Middle Row: Star Distribution */}
      <div>
        <h4 className="text-xs font-bold text-slate-500 uppercase mb-3 flex items-center gap-1">
            <Star size={12} /> {t('stats.qualityRatings')}
        </h4>
        <div className="flex items-end justify-between h-24 gap-2 px-2">
            {starCounts.map((count, index) => {
                const heightPercent = (count / maxStarCount) * 100;
                return (
                    <div key={index} className="flex flex-col items-center justify-end w-full h-full group">
                        <div className="text-xs font-bold text-slate-400 mb-1 opacity-0 group-hover:opacity-100 transition-opacity">{count}</div>
                        <div 
                            className="w-full bg-yellow-400 rounded-t-sm hover:bg-yellow-500 transition-all relative"
                            style={{ height: `${heightPercent}%`, minHeight: '4px' }}
                        ></div>
                        <div className="text-xs font-bold text-slate-500 mt-1">{index + 1}★</div>
                    </div>
                );
            })}
        </div>
      </div>

      {/* Bottom Row: Type Distribution */}
      <div>
         <h4 className="text-xs font-bold text-slate-500 uppercase mb-3">{t('stats.questTypes')}</h4>
         <div className="space-y-2">
            {Object.entries(typeCounts).map(([type, count]) => (
                <div key={type} className="flex items-center text-xs">
                    <span className="w-24 font-bold text-slate-600">{t(`taskType.${type}`)}</span>
                    <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div 
                            className="h-full bg-slate-400 rounded-full"
                            style={{ width: totalTasks > 0 ? `${(count / totalTasks) * 100}%` : '0%' }}
                        ></div>
                    </div>
                    <span className="w-8 text-right text-slate-400">{count}</span>
                </div>
            ))}
         </div>
      </div>
    </div>
  );
};

export default StatsBoard;
