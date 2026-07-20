import React from 'react';
import { Privilege } from '../types';
import { Lock, Unlock, Star, ScrollText } from 'lucide-react';

interface PrivilegeTreeProps {
  currentLevel: number;
  isAdmin?: boolean;
  onRecordUsage?: (privilegeTitle: string) => void;
}

const PRIVILEGES: Privilege[] = [
  { levelRequired: 2, title: "Explorer's Permit", description: "Allowed to go to the park on weekends alone.", icon: "🌳" },
  { levelRequired: 3, title: "Tavern Access", description: "Unlock 'Restaurant' choice once a month.", icon: "🍔" },
  { levelRequired: 4, title: "Merchant's Guild", description: "Can visit the convenience store with pocket money.", icon: "🏪" },
  { levelRequired: 5, title: "Time Mage", description: "Unlock +30 mins screen time on Fridays.", icon: "🎮" },
  { levelRequired: 8, title: "Mount Master", description: "Can ride bike to friend's house.", icon: "🚲" },
  { levelRequired: 10, title: "Guild Leader", description: "Can veto one household chore per week.", icon: "👑" },
];

const PrivilegeTree: React.FC<PrivilegeTreeProps> = ({ currentLevel, isAdmin, onRecordUsage }) => {
  return (
    <div className="bg-white p-4 rounded-xl shadow-md border border-slate-200">
      <h3 className="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2">
        <Star className="text-yellow-500" />
        Privilege Log
      </h3>
      <div className="space-y-3">
        {PRIVILEGES.map((priv) => {
          const isUnlocked = currentLevel >= priv.levelRequired;
          return (
            <div 
              key={priv.title} 
              className={`flex flex-col gap-2 p-3 rounded-lg border ${
                isUnlocked 
                  ? 'bg-amber-50 border-amber-200' 
                  : 'bg-slate-50 border-slate-200 opacity-60'
              }`}
            >
              <div className="flex items-center gap-3">
                <div className="text-2xl">{priv.icon}</div>
                <div className="flex-1">
                    <div className="flex items-center gap-2">
                        <h4 className={`font-bold text-sm ${isUnlocked ? 'text-amber-900' : 'text-slate-500'}`}>
                            {priv.title}
                        </h4>
                        {!isUnlocked && <span className="text-xs bg-slate-200 px-1 rounded text-slate-500">Lvl {priv.levelRequired}</span>}
                    </div>
                    <p className="text-xs text-slate-600">{priv.description}</p>
                </div>
                <div className="text-slate-400">
                    {isUnlocked ? <Unlock size={16} className="text-green-600" /> : <Lock size={16} />}
                </div>
              </div>

              {/* Admin Usage Button */}
              {isAdmin && isUnlocked && onRecordUsage && (
                  <button 
                    onClick={() => onRecordUsage(priv.title)}
                    className="self-end text-xs bg-amber-200 hover:bg-amber-300 text-amber-900 px-3 py-1 rounded-full font-bold flex items-center gap-1 transition-colors"
                  >
                      <ScrollText size={12}/> Record Usage
                  </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default PrivilegeTree;