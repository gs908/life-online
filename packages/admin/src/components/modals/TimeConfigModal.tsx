import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { TimeConfig } from '../../types';
import { Clock, Calendar, Check, X } from 'lucide-react';

interface TimeConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  config: TimeConfig;
  onSave: (newConfig: TimeConfig) => void;
}

const DAYS = [0, 1, 2, 3, 4, 5, 6];

const TimeConfigModal: React.FC<TimeConfigModalProps> = ({ isOpen, onClose, config, onSave }) => {
  const { t } = useTranslation();
  const [defaultVal, setDefaultVal] = useState(config.defaultDailyAllowance);
  const [exceptions, setExceptions] = useState<Record<number, number>>(config.exceptions || {});

  if (!isOpen) return null;

  const handleExceptionChange = (dayIndex: number, value: string) => {
    const val = parseInt(value);
    if (isNaN(val)) return;
    setExceptions(prev => ({ ...prev, [dayIndex]: val }));
  };

  const handleSave = () => {
    onSave({
      defaultDailyAllowance: defaultVal,
      exceptions
    });
    onClose();
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

          <div className="bg-blue-50 p-4 rounded-xl border border-blue-100">
            <label className="block text-sm font-bold text-blue-900 mb-2">{t('timeConfig.defaultDailyBudget')}</label>
            <div className="flex items-center gap-2">
              <input 
                type="number" 
                value={defaultVal}
                onChange={(e) => setDefaultVal(parseInt(e.target.value) || 0)}
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
                                        onClick={() => setExceptions(prev => ({...prev, [dayIndex]: defaultVal}))}
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
        </div>

        <div className="p-4 bg-slate-50 border-t flex justify-end gap-2">
            <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold hover:bg-slate-200 rounded-lg">{t('common.cancel')}</button>
            <button onClick={handleSave} className="px-6 py-2 bg-green-600 text-white font-bold rounded-lg hover:bg-green-700 shadow-md flex items-center gap-2">
                <Check size={18} /> {t('timeConfig.save')}
            </button>
        </div>
      </div>
    </div>
  );
};

export default TimeConfigModal;