import i18n from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import { initReactI18next } from 'react-i18next';

import enUS from './locales/en-US';
import zhCN from './locales/zh-CN';

export const SUPPORTED_LOCALES = ['zh-CN', 'en-US'] as const;
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

const normalizeLocale = (locale?: string | null): SupportedLocale => {
  if (!locale) return 'zh-CN';
  if (locale.toLowerCase().startsWith('zh')) return 'zh-CN';
  if (locale.toLowerCase().startsWith('en')) return 'en-US';
  return 'zh-CN';
};

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      'zh-CN': { translation: zhCN },
      'en-US': { translation: enUS },
    },
    fallbackLng: 'zh-CN',
    supportedLngs: [...SUPPORTED_LOCALES],
    load: 'currentOnly',
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'life-online-admin-locale',
      convertDetectedLanguage: normalizeLocale,
    },
  });

export default i18n;
