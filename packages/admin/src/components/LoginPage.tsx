/**
 * 开发登录页（docs/10 §4 阶段①）
 *
 * H5 开发期登录通道：POST /sys/auth/dev-login（仅后端 DEV_LOGIN_ENABLED=true 时可用）。
 * 微信 jscode 登录属小程序端，不在本页；DEV_LOGIN_ENABLED=false 时后端返回
 * permission_denied，此处给出明确提示。
 */
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Shield, Swords, Crown, LogIn } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { ApiError } from '../services/api';
import type { UserRole } from '../services/api';

const LoginPage: React.FC = () => {
  const { t } = useTranslation();
  const { login } = useAuth();
  const [role, setRole] = useState<UserRole>('ADVENTURER');
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await login(role, name.trim() || undefined);
    } catch (err) {
      if (err instanceof ApiError && err.errorCode === 'permission_denied') {
        setError(t('login.devDisabled'));
      } else {
        setError(err instanceof Error ? err.message : t('login.loginFailed'));
      }
      setSubmitting(false);
    }
  };

  const roleOptions: Array<{ value: UserRole; icon: React.ReactNode; label: string; desc: string; activeClass: string }> = [
    {
      value: 'ADVENTURER',
      icon: <Swords size={22} />,
      label: t('roles.ADVENTURER'),
      desc: t('login.roleChildDesc'),
      activeClass: 'border-blue-500 bg-blue-500/10 text-blue-300',
    },
    {
      value: 'GUILD_MASTER',
      icon: <Crown size={22} />,
      label: t('roles.GUILD_MASTER'),
      desc: t('login.roleParentDesc'),
      activeClass: 'border-purple-500 bg-purple-500/10 text-purple-300',
    },
  ];

  return (
    <div className="min-h-full flex items-center justify-center bg-slate-900 p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex p-3 bg-yellow-500 rounded-2xl text-slate-900 mb-4">
            <Shield size={32} />
          </div>
          <h1 className="font-pixel text-2xl text-white mb-2">{t('common.appName')}</h1>
          <p className="text-sm text-slate-400">{t('login.subtitle')}</p>
        </div>

        <form
          onSubmit={handleLogin}
          className="bg-slate-800 rounded-2xl shadow-2xl p-6 space-y-5 border border-slate-700"
          aria-label={t('login.title')}
        >
          <div role="radiogroup" aria-label={t('login.chooseRole')} className="grid grid-cols-2 gap-3">
            {roleOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={role === option.value}
                onClick={() => setRole(option.value)}
                className={`flex flex-col items-center gap-1.5 p-4 rounded-xl border-2 transition-all outline-none focus-visible:ring-2 focus-visible:ring-yellow-400 ${
                  role === option.value
                    ? option.activeClass
                    : 'border-slate-700 bg-slate-900/50 text-slate-400 hover:border-slate-500'
                }`}
              >
                {option.icon}
                <span className="text-sm font-bold">{option.label}</span>
                <span className="text-xs opacity-75">{option.desc}</span>
              </button>
            ))}
          </div>

          <div>
            <label htmlFor="login-nickname" className="block text-xs font-bold text-slate-400 mb-1.5">
              {t('login.nicknameLabel')}
            </label>
            <input
              id="login-nickname"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('login.nicknamePlaceholder')}
              maxLength={50}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 outline-none focus:border-yellow-500 focus:ring-1 focus:ring-yellow-500"
            />
            <p className="mt-1 text-xs text-slate-500">{t('login.nicknameHint')}</p>
          </div>

          {error && (
            <p role="alert" className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full flex items-center justify-center gap-2 bg-yellow-500 hover:bg-yellow-400 disabled:opacity-50 disabled:cursor-not-allowed text-slate-900 font-bold py-2.5 rounded-lg transition-colors"
          >
            <LogIn size={16} />
            {submitting ? t('login.loggingIn') : t('login.submit')}
          </button>

          <p className="text-center text-xs text-slate-500">{t('login.devOnlyHint')}</p>
        </form>
      </div>
    </div>
  );
};

export default LoginPage;
