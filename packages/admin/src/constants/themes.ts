
import { SeasonTheme, ThemeId } from '../types';

export const THEMES: Record<ThemeId, SeasonTheme> = {
  DEFAULT: {
    id: 'DEFAULT',
    name: 'Classic Guild',
    primaryColor: 'bg-blue-600',
    accentColor: 'text-yellow-400',
    backgroundColor: 'bg-slate-100',
    textColor: 'text-slate-900',
    icon: '🏰',
    bgImage: 'bg-slate-100' 
  },
  FROSTBOUND: {
    id: 'FROSTBOUND',
    name: 'Eternal Winter',
    primaryColor: 'bg-cyan-600',
    accentColor: 'text-cyan-200',
    backgroundColor: 'bg-slate-900',
    textColor: 'text-cyan-50',
    icon: '❄️',
    bgImage: 'bg-gradient-to-br from-slate-900 via-slate-800 to-cyan-950'
  },
  INFERNO: {
    id: 'INFERNO',
    name: 'Dragonfire Peak',
    primaryColor: 'bg-orange-600',
    accentColor: 'text-yellow-300',
    backgroundColor: 'bg-stone-900',
    textColor: 'text-orange-50',
    icon: '🔥',
    bgImage: 'bg-gradient-to-br from-stone-900 via-red-950 to-orange-900'
  },
  SYLVAN: {
    id: 'SYLVAN',
    name: 'Whispering Woods',
    primaryColor: 'bg-emerald-600',
    accentColor: 'text-green-300',
    backgroundColor: 'bg-green-950',
    textColor: 'text-emerald-50',
    icon: '🍃',
    bgImage: 'bg-gradient-to-br from-green-950 via-teal-900 to-emerald-950'
  },
  CYBERPUNK: {
    id: 'CYBERPUNK',
    name: 'Neon City 2077',
    primaryColor: 'bg-fuchsia-600',
    accentColor: 'text-pink-400',
    backgroundColor: 'bg-black',
    textColor: 'text-fuchsia-50',
    icon: '🦾',
    bgImage: 'bg-gradient-to-br from-black via-slate-900 to-purple-950'
  }
};
