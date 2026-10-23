import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../../services/api';
import type { TimeConfigRead } from '../../services/api';
import { Clock, Calendar, Check, X } from 'lucide-react';

interface TimeConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  onToast: (title: string, msg: string) => void;
}

const DAYS = [0, 1, 2, 3, 4, 5, 6];

/**
 * 时间币配置（阶段④，契约 §11）：GET/PUT /scn/time-configs/me。
 * 后端 exceptions 为数组且 PUT 整体替换（docs/09 C1/C3）——字典视图仅在本组件内转换，不进 API 层。
 */
const TimeConfigModal: React.FC<TimeConfigModalProps> = ({ isOpen, onClose, onToast }) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [defaultVal, setDefaultVal] = useState(100);
  // day_of_week(0=周日…6=周六，与 JS getDay() 一致) → 当日额度
  const [exceptions, setExceptions] = useState<Record<number, number>>({});

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.coins
      .getMyTimeConfig()
      .then((config: TimeConfigRead) => {
        if (cancelled) return;
        setDefaultVal(config.default_daily_allowance);
        const map: Record<number, number> = {};
        config.exceptions.forEach(ex => { map[ex.day_of_week] = ex.coin_amount; });
        setExceptions(map);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : t('timeConfig.loadFailed'));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [isOpen, t]);

  if (!isOpen) return null;

  const handleExceptionChange = (dayIndex: number, value: string) => {
    const val = parseInt(value);
    if (isNaN(val) || val < 0) return;
    setExceptions(prev => ({ ...prev, [dayIndex]: val }));
  };

  const handleSave = async () => {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      // PUT 对 exceptions 是整体替换：保存时提交完整数组（docs/09 C3），额度 clamp ≥0
      await api.coins.updateMyTimeConfig({
        default_daily_allowance: Math.max(0, defaultVal),
        exceptions: DAYS
          .filter(day => exceptions[day] !== undefined)
          .map(day => ({ day_of_week: day, coin_amount: Math.max(0, exceptions[day]) })),
      });
      onToast(t('toast.configSavedTitle'), t('toast.configSavedMsg'));
      onClose();
    } catch (err) {
      // 403=孩子账号调父母接口、422=数值校验失败，均展示后端人话文案
      setError(err instanceof ApiError ? err.message : t('timeConfig.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl overflow-hidden animate-in zoom-in duration-200">
        <div className="bg-slate-900 text-white p-4 flex justify-between items-center">
          <h3 className="font-bold text-lg flex items-center gap-2"><Clock size={20} /> {t('timeConfig.title')}</h3>
          <button onClick={onClose}><X size={20} /></button>
        </div>

        <div className="p-6 space-y-6 max-h-[70vh] overflow-y-auto">
          <p className="text-sm text-slate-500">
            {t('timeConfig.hint')}
          </p>

          {loading ? (
            <div className="text-center py-10 text-slate-400 font-bold animate-pulse">{t('common.loading')}</div>
          ) : (
            <>
              <div className="bg-blue-50 p-4 rounded-xl border border-blue-100">
                <label className="block text-sm font-bold text-blue-900 mb-2">{t('timeConfig.defaultDailyBudget')}</label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min={0}
                    value={defaultVal}
                    onChange={(e) => setDefaultVal(Math.max(0, parseInt(e.target.value) || 0))}
                    className="flex-1 p-2 border border-blue-200 rounded-lg text-lg font-bold text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <span className="font-bold text-blue-400">{t('common.coins')}</span>
                </div>
              </div>

              <div>
                <h4 className="font-bold text-slate-700 mb-3 flex items-center gap-2">
                    <Calendar size={16} /> {t('timeConfig.dailyExceptions')}
                </h4>
                <div className="space-y-2">
                    {DAYS.map((dayIndex) => {
                        const isException = exceptions[dayIndex] !== undefined;
                        return (
                            <div key={dayIndex} className={`flex items-center justify-between p-2 rounded-lg border ${isException ? 'bg-amber-50 border-amber-200' : 'bg-slate-50 border-slate-100'}`}>
                                <span className={`text-sm font-medium ${isException ? 'text-amber-900' : 'text-slate-500'}`}>{t(`days.${dayIndex}`)}</span>
                                <div className="flex items-center gap-2">
                                    {isException ? (
                                        <>
                                            <input
                                                type="number"
                                                min={0}
                                                value={exceptions[dayIndex]}
                                                onChange={(e) => handleExceptionChange(dayIndex, e.target.value)}
                                                className="w-20 p-1 text-right text-sm border border-amber-300 rounded focus:outline-none"
                                            />
                                            <button onClick={() => {
                                                const newEx = {...exceptions};
                                                delete newEx[dayIndex];
                                                setExceptions(newEx);
                                            }} className="text-slate-400 hover:text-red-500"><X size={14}/></button>
                                        </>
                                    ) : (
                                        <button
                                            onClick={() => setExceptions(prev => ({...prev, [dayIndex]: Math.max(0, defaultVal)}))}
                                            className="text-xs text-blue-500 font-bold hover:underline"
                                        >
                                            {t('timeConfig.setCustom')}
                                        </button>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>
              </div>
            </>
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700 font-bold">
              {error}
            </div>
          )}
        </div>

        <div className="p-4 bg-slate-50 border-t flex justify-end gap-2">
            <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold hover:bg-slate-200 rounded-lg">{t('common.cancel')}</button>
            <button
              onClick={handleSave}
              disabled={loading || saving}
              className="px-6 py-2 bg-green-600 text-white font-bold rounded-lg hover:bg-green-700 shadow-md flex items-center gap-2 disabled:opacity-50">
                <Check size={18} /> {saving ? t('common.loading') : t('timeConfig.save')}
            </button>
        </div>
      </div>
    </div>
  );
};

export default TimeConfigModal;
