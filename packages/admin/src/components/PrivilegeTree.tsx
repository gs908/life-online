import React from 'react';
import { useTranslation } from 'react-i18next';
import type { PrivilegeRead } from '../services/api';
import { Lock, Unlock, Star, ScrollText, Settings } from 'lucide-react';

interface PrivilegeTreeProps {
  /** 特权模板树（GET /scn/privileges/templates，后端已按 level_required 排序；docs/09 V2） */
  templates: PrivilegeRead[];
  /** 已解锁特权（GET /scn/privileges/unlocks，按 privilege_template_id 匹配） */
  unlockedTemplateIds: string[];
  /** 冒险者当前等级（未解锁时展示门槛徽标） */
  currentLevel: number;
  loading?: boolean;
  isAdmin?: boolean;
  onRecordUsage?: (privilege: PrivilegeRead) => void;
  /** 打开权益配置弹窗（家长端设置入口） */
  onOpenConfig?: () => void;
}

const PrivilegeTree: React.FC<PrivilegeTreeProps> = ({
  templates,
  unlockedTemplateIds,
  currentLevel,
  loading,
  isAdmin,
  onRecordUsage,
  onOpenConfig,
}) => {
  const { t } = useTranslation();
  const unlockedSet = new Set(unlockedTemplateIds);

  return (
    <div className="bg-white p-4 rounded-xl shadow-md border border-slate-200">
      <h3 className="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2">
        <Star className="text-yellow-500" />
        {t('privilege.title')}
        {isAdmin && onOpenConfig && (
          <button
            onClick={onOpenConfig}
            className="ml-auto text-xs text-slate-400 hover:text-blue-600 flex items-center gap-1 transition-colors"
            title={t('privilegeConfig.title')}
          >
            <Settings size={14} /> {t('privilegeConfig.title')}
          </button>
        )}
      </h3>
      {loading && templates.length === 0 ? (
        <p className="text-sm text-slate-400 italic text-center py-4">{t('common.loading')}</p>
      ) : templates.length === 0 ? (
        <p className="text-sm text-slate-400 italic text-center py-4">{t('privilege.empty')}</p>
      ) : (
        <div className="space-y-3">
          {templates.map((priv) => {
            const isUnlocked = unlockedSet.has(priv.id);
            return (
              <div
                key={priv.id}
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
                          {!isUnlocked && (
                            <span className={`text-xs px-1 rounded ${currentLevel >= priv.level_required ? 'bg-green-100 text-green-700' : 'bg-slate-200 text-slate-500'}`}>
                              {t('common.levelShort')} {priv.level_required}
                            </span>
                          )}
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
                      onClick={() => onRecordUsage(priv)}
                      className="self-end text-xs bg-amber-200 hover:bg-amber-300 text-amber-900 px-3 py-1 rounded-full font-bold flex items-center gap-1 transition-colors"
                    >
                        <ScrollText size={12}/> {t('privilege.recordUsage')}
                    </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default PrivilegeTree;
