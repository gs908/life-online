import React from 'react';
import { useTranslation } from 'react-i18next';
import { Privilege } from '../types';
import { Lock, Unlock, Star, ScrollText } from 'lucide-react';

interface PrivilegeTreeProps {
  currentLevel: number;
  isAdmin?: boolean;
  onRecordUsage?: (privilegeTitle: string) => void;
}

const PRIVILEGE_KEYS = [
  { levelRequired: 2, titleKey: 'explorerTitle', descriptionKey: 'explorerDesc', icon: '🌳' },
  { levelRequired: 3, titleKey: 'tavernTitle', descriptionKey: 'tavernDesc', icon: '🍔' },
  { levelRequired: 4, titleKey: 'merchantTitle', descriptionKey: 'merchantDesc', icon: '🏪' },
  { levelRequired: 5, titleKey: 'mageTitle', descriptionKey: 'mageDesc', icon: '🎮' },
  { levelRequired: 8, titleKey: 'mountTitle', descriptionKey: 'mountDesc', icon: '🚲' },
  { levelRequired: 10, titleKey: 'leaderTitle', descriptionKey: 'leaderDesc', icon: '👑' },
];

const PrivilegeTree: React.FC<PrivilegeTreeProps> = ({ currentLevel, isAdmin, onRecordUsage }) => {
  const { t } = useTranslation();
  const privileges: Privilege[] = PRIVILEGE_KEYS.map(priv => ({
    levelRequired: priv.levelRequired,
    title: t(`privilege.${priv.titleKey}`),
    description: t(`privilege.${priv.descriptionKey}`),
    icon: priv.icon,
  }));

  return (
    <div className="bg-white p-4 rounded-xl shadow-md border border-slate-200">
      <h3 className="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2">
        <Star className="text-yellow-500" />
        {t('privilege.title')}
      </h3>
      <div className="space-y-3">
        {privileges.map((priv) => {
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
                        {!isUnlocked && <span className="text-xs bg-slate-200 px-1 rounded text-slate-500">{t('common.levelShort')} {priv.levelRequired}</span>}
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
                      <ScrollText size={12}/> {t('privilege.recordUsage')}
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
