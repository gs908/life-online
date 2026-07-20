import React from 'react';

interface XPBarProps {
  currentXP: number;
  level: number;
}

const XPBar: React.FC<XPBarProps> = ({ currentXP, level }) => {
  // Simple exponential leveling curve: Level * 1000 XP needed for next level
  const xpForNextLevel = level * 1000;
  const progressPercentage = Math.min((currentXP / xpForNextLevel) * 100, 100);

  return (
    <div className="w-full flex flex-col gap-1">
      <div className="flex justify-between items-end">
        <div className="flex items-center gap-2">
            <span className="bg-yellow-500 text-white font-bold rounded-full w-8 h-8 flex items-center justify-center border-2 border-yellow-600 shadow-md">
                {level}
            </span>
            <span className="text-sm font-bold text-slate-700">Lvl {level}</span>
        </div>
        <span className="text-xs font-medium text-slate-500">{currentXP} / {xpForNextLevel} XP</span>
      </div>
      <div className="h-4 w-full bg-slate-200 rounded-full overflow-hidden border border-slate-300 shadow-inner relative">
        <div 
            className="h-full bg-gradient-to-r from-green-400 to-green-600 transition-all duration-1000 ease-out relative"
            style={{ width: `${progressPercentage}%` }}
        >
            <div className="absolute top-0 left-0 w-full h-full bg-white opacity-20 animate-pulse"></div>
        </div>
      </div>
    </div>
  );
};

export default XPBar;