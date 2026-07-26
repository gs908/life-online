import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Season, ThemeId } from '../../types';
import { THEMES } from '../../constants/themes';
import { Palette, ScrollText, Check, X } from 'lucide-react';

interface SeasonConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentSeason: Season;
  onSave: (season: Season) => void;
}

const SeasonConfigModal: React.FC<SeasonConfigModalProps> = ({ isOpen, onClose, currentSeason, onSave }) => {
  const { t } = useTranslation();
  const [name, setName] = useState(currentSeason.name);
  const [narrativeContext, setNarrativeContext] = useState(currentSeason.narrativeContext);
  const [selectedTheme, setSelectedTheme] = useState<ThemeId>(currentSeason.themeId);

  useEffect(() => {
    if (isOpen) {
      setName(currentSeason.name);
      setNarrativeContext(currentSeason.narrativeContext);
      setSelectedTheme(currentSeason.themeId);
    }
  }, [isOpen, currentSeason]);

  if (!isOpen) return null;

  const handleSave = () => {
    onSave({
      ...currentSeason,
      name,
      narrativeContext,
      themeId: selectedTheme
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200 flex flex-col max-h-[90vh]">
        <div className="bg-slate-900 text-white p-4 flex justify-between items-center shrink-0">
          <h3 className="font-bold text-lg flex items-center gap-2">
            <Palette size={20} /> {t('seasonConfig.title')}
          </h3>
          <button onClick={onClose}><X /></button>
        </div>

        <div className="p-6 overflow-y-auto space-y-6">
          
          {/* Section 1: Basic Info */}
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-bold text-slate-700 mb-1">{t('seasonConfig.seasonName')}</label>
              <input 
                type="text" 
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full border border-slate-300 rounded-lg p-2 font-bold focus:ring-2 focus:ring-blue-500 outline-none"
                placeholder={t('seasonConfig.seasonNamePlaceholder')}
              />
            </div>
            
            <div>
              <label className="block text-sm font-bold text-slate-700 mb-1 flex items-center gap-2">
                 <ScrollText size={16}/> {t('seasonConfig.narrativeContext')}
              </label>
              <textarea 
                value={narrativeContext}
                onChange={(e) => setNarrativeContext(e.target.value)}
                className="w-full h-24 border border-slate-300 rounded-lg p-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none resize-none"
                placeholder={t('seasonConfig.narrativePlaceholder')}
              />
              <p className="text-xs text-slate-500 mt-1">{t('seasonConfig.aiHint')}</p>
            </div>
          </div>

          {/* Section 2: Theme Selection */}
          <div>
            <h4 className="text-sm font-bold text-slate-700 mb-3">{t('seasonConfig.visualTheme')}</h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {(Object.values(THEMES) as any[]).map((theme) => (
                <div 
                  key={theme.id}
                  onClick={() => setSelectedTheme(theme.id)}
                  className={`cursor-pointer rounded-xl p-3 border-2 transition-all relative overflow-hidden group
                    ${selectedTheme === theme.id ? 'border-blue-500 shadow-lg scale-105' : 'border-slate-200 hover:border-blue-300'}
                  `}
                >
                  <div className={`absolute inset-0 opacity-10 ${theme.primaryColor}`}></div>
                  <div className="flex items-center gap-3 relative z-10">
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xl shadow-sm ${theme.primaryColor} text-white`}>
                      {theme.icon}
                    </div>
                    <div>
                      <h5 className="font-bold text-slate-800 text-sm">{theme.name}</h5>
                      <p className="text-xs text-slate-500">{t('seasonConfig.previewStyle')}</p>
                    </div>
                    {selectedTheme === theme.id && <div className="absolute right-0 top-0 p-1 bg-blue-500 text-white rounded-bl-lg"><Check size={12}/></div>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="p-4 bg-slate-50 border-t flex justify-end gap-2 shrink-0">
          <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold hover:bg-slate-200 rounded-lg">{t('common.cancel')}</button>
          <button onClick={handleSave} className="px-6 py-2 bg-green-600 text-white font-bold rounded-lg hover:bg-green-700 shadow-md">
            {t('seasonConfig.save')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SeasonConfigModal;