import React from 'react';
import { useTranslation } from 'react-i18next';
import { User, UserRole } from '../types';
import { Languages, LayoutDashboard, UserCircle } from 'lucide-react';

interface HeaderProps {
  currentSeason: string;
  currentUser: User;
  onSwitchUser: (role: UserRole) => void;
}

const Header: React.FC<HeaderProps> = ({ currentSeason, currentUser, onSwitchUser }) => {
  const { i18n, t } = useTranslation();
  const currentLocale = i18n.resolvedLanguage === 'en-US' ? 'en-US' : 'zh-CN';

  const handleLocaleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    i18n.changeLanguage(event.target.value);
  };

  return (
    <header className="bg-slate-900 text-white p-4 shadow-lg flex justify-between items-center z-10 sticky top-0">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-yellow-500 rounded-lg text-slate-900">
          <LayoutDashboard size={24} />
        </div>
        <div>
          <h1 className="font-pixel text-lg leading-none hidden md:block">{t('common.appName')}</h1>
          <p className="text-xs text-slate-400">
            {t('header.season')}: <span className="text-yellow-400 font-bold">{currentSeason}</span>
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <label className="hidden sm:flex items-center gap-1 text-xs text-slate-400" title={t('common.language')}>
          <Languages size={14} />
          <select
            value={currentLocale}
            onChange={handleLocaleChange}
            className="bg-slate-800 border border-slate-700 rounded-full px-2 py-1 text-white text-xs font-bold outline-none"
          >
            <option value="zh-CN">{t('common.chinese')}</option>
            <option value="en-US">{t('common.english')}</option>
          </select>
        </label>

        <div className="flex gap-2 bg-slate-800 p-1 rounded-full">
          <button
            onClick={() => onSwitchUser(UserRole.CHILD)}
            className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold transition-all ${
              currentUser.role === UserRole.CHILD ? 'bg-blue-500 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            <UserCircle size={14} /> {t('roles.ADVENTURER')}
          </button>
          <button
            onClick={() => onSwitchUser(UserRole.PARENT)}
            className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold transition-all ${
              currentUser.role === UserRole.PARENT ? 'bg-purple-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            {t('roles.GUILD_MASTER')} <UserCircle size={14} />
          </button>
        </div>
      </div>
    </header>
  );
};

export default Header;
