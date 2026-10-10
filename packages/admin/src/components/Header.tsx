import React from 'react';
import { useTranslation } from 'react-i18next';
import { User } from '../types';
import { Languages, LayoutDashboard, LogOut, Crown, Swords } from 'lucide-react';

interface HeaderProps {
  currentSeason: string;
  /** 真实登录用户（UserRead 映射，Mock 用户已删除） */
  currentUser: User;
  onLogout: () => void;
}

const Header: React.FC<HeaderProps> = ({ currentSeason, currentUser, onLogout }) => {
  const { i18n, t } = useTranslation();
  const currentLocale = i18n.resolvedLanguage === 'en-US' ? 'en-US' : 'zh-CN';
  const isParent = currentUser.role === ('GUILD_MASTER' as User['role']);

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

        <div
          className={`flex items-center gap-2 bg-slate-800 px-3 py-1.5 rounded-full text-xs font-bold ${
            isParent ? 'text-purple-300' : 'text-blue-300'
          }`}
          title={t(isParent ? 'roles.GUILD_MASTER' : 'roles.ADVENTURER')}
        >
          {isParent ? <Crown size={14} /> : <Swords size={14} />}
          <span className="max-w-[120px] truncate">{currentUser.name}</span>
        </div>

        <button
          onClick={onLogout}
          title={t('header.logout')}
          aria-label={t('header.logout')}
          className="flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white px-3 py-1.5 rounded-full text-xs font-bold transition-colors"
        >
          <LogOut size={14} />
          <span className="hidden sm:inline">{t('header.logout')}</span>
        </button>
      </div>
    </header>
  );
};

export default Header;
