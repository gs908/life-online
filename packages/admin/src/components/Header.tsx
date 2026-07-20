import React from 'react';
import { User, UserRole } from '../types';
import { LayoutDashboard, UserCircle } from 'lucide-react';

interface HeaderProps {
  currentSeason: string;
  currentUser: User;
  onSwitchUser: (role: UserRole) => void;
}

const Header: React.FC<HeaderProps> = ({ currentSeason, currentUser, onSwitchUser }) => {
  return (
    <header className="bg-slate-900 text-white p-4 shadow-lg flex justify-between items-center z-10 sticky top-0">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-yellow-500 rounded-lg text-slate-900">
          <LayoutDashboard size={24} />
        </div>
        <div>
          <h1 className="font-pixel text-lg leading-none hidden md:block">QuestGuild</h1>
          <p className="text-xs text-slate-400">
            Season: <span className="text-yellow-400 font-bold">{currentSeason}</span>
          </p>
        </div>
      </div>

      <div className="flex gap-2 bg-slate-800 p-1 rounded-full">
        <button
          onClick={() => onSwitchUser(UserRole.CHILD)}
          className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold transition-all ${
            currentUser.role === UserRole.CHILD ? 'bg-blue-500 text-white' : 'text-slate-400 hover:text-white'
          }`}
        >
          <UserCircle size={14} /> Adventurer
        </button>
        <button
          onClick={() => onSwitchUser(UserRole.PARENT)}
          className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold transition-all ${
            currentUser.role === UserRole.PARENT ? 'bg-purple-600 text-white' : 'text-slate-400 hover:text-white'
          }`}
        >
          Guild Master <UserCircle size={14} />
        </button>
      </div>
    </header>
  );
};

export default Header;