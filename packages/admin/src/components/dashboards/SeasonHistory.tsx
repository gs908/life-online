import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../../services/api';
import type { SeasonHistoryItem } from '../../services/api';
import { THEMES } from '../../constants/themes';
import { Calendar, Trophy, CheckCircle2, ScrollText, AlertTriangle } from 'lucide-react';

interface SeasonHistoryProps {
  onBack: () => void;
}

/**
 * 赛季历史（阶段②，docs/10 §4）：数据源 GET /scn/seasons/history。
 * 完成度 / 累计 XP 均为后端统计（SeasonHistoryItem），不再本地按任务折算。
 */
const SeasonHistory: React.FC<SeasonHistoryProps> = ({ onBack }) => {
  const { t } = useTranslation();
  const [items, setItems] = useState<SeasonHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.seasons
      .getSeasonHistory()
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : t('seasonHistory.loadFailed'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  return (
    <div className="space-y-6 animate-in slide-in-from-right duration-300">
      <div className="flex items-center gap-4 border-b border-slate-200 pb-4">
        <button onClick={onBack} className="text-sm font-bold text-blue-600 hover:underline">{t('seasonHistory.back')}</button>
        <h2 className="text-2xl font-bold text-slate-800">{t('seasonHistory.title')}</h2>
      </div>

      {loading ? (
        <div className="text-center py-20 text-slate-400 font-bold animate-pulse">{t('common.loading')}</div>
      ) : error ? (
        <div className="text-center py-20 bg-red-50 rounded-xl border border-red-200">
          <AlertTriangle className="mx-auto text-red-300 mb-4" size={48} />
          <p className="text-red-600 font-bold">{error}</p>
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-20 bg-slate-50 rounded-xl border-2 border-dashed border-slate-300">
          <Calendar className="mx-auto text-slate-300 mb-4" size={48} />
          <p className="text-slate-500 font-bold">{t('seasonHistory.emptyTitle')}</p>
          <p className="text-slate-400 text-sm">{t('seasonHistory.emptyHint')}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6">
          {items.map(({ season, total_tasks, completed_tasks, total_xp }) => {
            const theme = THEMES[season.theme_id] || THEMES.DEFAULT;
            return (
              <div key={season.id} className="bg-white rounded-xl shadow-md overflow-hidden border border-slate-200 flex flex-col md:flex-row">
                {/* Visual Sidebar */}
                <div className={`p-6 md:w-1/3 text-white ${theme.bgImage} flex flex-col justify-center relative overflow-hidden`}>
                   <div className="absolute inset-0 bg-black/30"></div>
                   <div className="relative z-10 text-center md:text-left">
                       <div className="text-4xl mb-2">{theme.icon}</div>
                       <h3 className="text-2xl font-bold leading-tight mb-1">{season.name}</h3>
                       <span className="text-xs font-bold uppercase tracking-wider opacity-80">{theme.name} {t('seasonHistory.theme')}</span>
                       {season.is_active && (
                         <span className="mt-2 inline-block text-[10px] font-bold bg-green-500 text-white px-2 py-0.5 rounded-full">
                           {t('seasonConfig.activeBadge')}
                         </span>
                       )}
                   </div>
                </div>

                {/* Stats & Lore */}
                <div className="p-6 md:w-2/3 flex flex-col justify-between gap-4">
                    <div>
                        {season.narrative_context && (
                          <div className="flex items-start gap-2 text-slate-600 italic text-sm mb-4 bg-slate-50 p-3 rounded-lg border-l-4 border-slate-300">
                             <ScrollText size={16} className="shrink-0 mt-0.5" />
                             "{season.narrative_context}"
                          </div>
                        )}

                        <div className="grid grid-cols-2 gap-4">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-yellow-100 text-yellow-600 rounded-full"><Trophy size={20} /></div>
                                <div>
                                    <div className="text-2xl font-bold text-slate-800">{total_xp}</div>
                                    <div className="text-xs text-slate-500 uppercase font-bold">{t('seasonHistory.totalXp')}</div>
                                </div>
                            </div>
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-green-100 text-green-600 rounded-full"><CheckCircle2 size={20} /></div>
                                <div>
                                    <div className="text-2xl font-bold text-slate-800">{completed_tasks} / {total_tasks}</div>
                                    <div className="text-xs text-slate-500 uppercase font-bold">{t('seasonHistory.questsCompleted')}</div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="text-right text-xs text-slate-400 font-mono mt-2">
                        {t('seasonHistory.endedOn')}: {season.end_date ? new Date(season.end_date).toLocaleDateString() : '—'}
                    </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default SeasonHistory;
