
import React, { useState, useEffect, useRef } from 'react';
import { User, Task, UserRole, SeasonTheme, TaskType } from '../../types';
import XPBar from '../XPBar';
import PrivilegeTree from '../PrivilegeTree';
import QuestCard from '../QuestCard';
import { Sparkles, BrainCircuit, Trophy, Star, Coins, ScrollText, ChevronLeft, ChevronRight, Bookmark, Calendar, Shield, Clock, Users, Link } from 'lucide-react';

interface ChildDashboardProps {
  childUser: User;
  currentTheme: SeasonTheme;
  tasks: Task[];
  activeQuest: Task | undefined;
  availableTasks: Task[];
  completedTasks: Task[];
  pendingTasks: Task[];
  onAcceptAttempt: (id: string) => void;
  onSubmit: (id: string) => void;
  onAbandonCurrent: (id: string) => void;
}

const ChildDashboard: React.FC<ChildDashboardProps> = ({
  childUser,
  currentTheme,
  activeQuest,
  availableTasks,
  completedTasks,
  pendingTasks,
  onAcceptAttempt,
  onSubmit,
  onAbandonCurrent
}) => {
  const [showLevelUp, setShowLevelUp] = useState(false);
  const prevLevelRef = useRef(childUser.level);

  // Quest Book State
  const categories = ['ALL', ...Object.values(TaskType)];
  const [activeCategoryIndex, setActiveCategoryIndex] = useState(0);
  const activeCategory = categories[activeCategoryIndex];

  // Detect Level Up
  useEffect(() => {
    if (childUser.level > prevLevelRef.current) {
      setShowLevelUp(true);
      const timer = setTimeout(() => setShowLevelUp(false), 8000);
      return () => clearTimeout(timer);
    }
    prevLevelRef.current = childUser.level;
  }, [childUser.level]);

  // Filter Tasks for Book Page
  const bookTasks = availableTasks.filter(t => {
      if (activeCategory === 'ALL') return true;
      return t.type === activeCategory;
  });

  const handleNextPage = () => {
      setActiveCategoryIndex((prev) => (prev + 1) % categories.length);
  };

  const handlePrevPage = () => {
      setActiveCategoryIndex((prev) => (prev - 1 + categories.length) % categories.length);
  };

  const getCategoryIcon = (cat: string) => {
      switch (cat) {
          case 'DAILY': return <Calendar size={14}/>;
          case 'CHALLENGE': return <Shield size={14}/>;
          case 'TIMED': return <Clock size={14}/>;
          case 'COOP': return <Users size={14}/>;
          case 'CHAIN': return <Link size={14}/>;
          default: return <Bookmark size={14}/>;
      }
  };

  const getCategoryLabel = (cat: string) => {
      if (cat === 'ALL') return 'Guild Hall';
      return cat.charAt(0) + cat.slice(1).toLowerCase() + ' Quests';
  };

  return (
    <div className={`relative min-h-screen -m-4 md:-m-6 lg:-m-8 p-4 md:p-6 lg:p-8 transition-colors duration-500 ${currentTheme.backgroundColor}`}>
      
      {/* Dynamic Background Overlay */}
      <div className={`absolute inset-0 opacity-20 pointer-events-none ${currentTheme.bgImage}`}></div>
      
      {/* Content Container */}
      <div className="relative z-10 grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* --- LEVEL UP OVERLAY ANIMATION --- */}
        {showLevelUp && (
          <div 
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm animate-in fade-in duration-500 cursor-pointer"
            onClick={() => setShowLevelUp(false)}
          >
            <div className="relative flex flex-col items-center justify-center text-center p-8">
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-gradient-to-r from-yellow-500/0 via-yellow-500/20 to-yellow-500/0 rounded-full animate-spin-slow pointer-events-none blur-xl"></div>
              <h1 className="text-6xl md:text-8xl font-pixel text-yellow-400 drop-shadow-[0_0_15px_rgba(250,204,21,0.8)] animate-bounce mb-8">
                LEVEL UP!
              </h1>
              <div className="relative group">
                <Trophy size={160} className="text-yellow-200 drop-shadow-2xl animate-pulse" />
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-3/4 text-6xl font-bold text-yellow-800 font-pixel">
                  {childUser.level}
                </div>
              </div>
              <p className="mt-8 text-white text-xl font-bold animate-pulse">
                You are now Level {childUser.level}!
              </p>
              <button className="mt-8 bg-yellow-500 hover:bg-yellow-400 text-yellow-900 font-bold py-3 px-8 rounded-full shadow-lg transform transition hover:scale-105 active:scale-95">
                CONTINUE ADVENTURE
              </button>
            </div>
          </div>
        )}

        {/* Left Column: Stats & Profile */}
        <div className="lg:col-span-1 space-y-6">
          <div className="bg-white/95 backdrop-blur-sm p-6 rounded-2xl shadow-lg border-2 border-slate-200 text-center relative overflow-hidden">
            {/* Theme Decor Bar */}
            <div className={`absolute top-0 left-0 w-full h-3 ${currentTheme.primaryColor}`}></div>
            
            <div className="text-6xl mb-4 transform hover:scale-110 transition-transform cursor-default">{childUser.avatar}</div>
            <h2 className="text-2xl font-bold text-slate-800">{childUser.name}</h2>
            <div className="mt-4">
              <XPBar currentXP={childUser.xp} level={childUser.level} />
            </div>

            {/* TIME COIN WALLET */}
            <div className="mt-6 bg-slate-900 rounded-xl p-3 flex items-center justify-between text-white shadow-lg border border-slate-700">
              <div className="flex items-center gap-2">
                  <div className="p-2 bg-yellow-500 rounded-full text-yellow-900">
                      <Coins size={20} />
                  </div>
                  <div className="text-left leading-none">
                      <span className="block text-xs text-slate-400 font-bold uppercase tracking-wider">Time Coins</span>
                      <span className="text-lg font-pixel text-yellow-400">{childUser.timeCoins}</span>
                  </div>
              </div>
              <div className="text-right">
                  <span className="block text-[10px] text-slate-500">Daily Deposit</span>
              </div>
            </div>
          </div>
          
          <div className="bg-white/90 backdrop-blur-sm rounded-xl overflow-hidden shadow-lg">
             <PrivilegeTree currentLevel={childUser.level} />
          </div>
        </div>

        {/* Right Column: Quests */}
        <div className="lg:col-span-2 space-y-6">

          {/* HERO SECTION: ACTIVE QUEST */}
          {activeQuest ? (
            <div className="mb-8 animate-in slide-in-from-bottom duration-500">
              <h2 className={`text-xl font-bold flex items-center gap-2 mb-4 ${currentTheme.textColor} drop-shadow-md`}>
                <Sparkles /> Current Adventure
              </h2>
              <QuestCard
                task={activeQuest}
                role={UserRole.CHILD}
                isActive={true}
                onAccept={() => { }}
                onSubmit={onSubmit}
                onAbandon={onAbandonCurrent}
                onApprove={() => { }}
              />
            </div>
          ) : (
            <div className={`${currentTheme.primaryColor} bg-opacity-10 border border-white/20 backdrop-blur-md rounded-xl p-8 text-center mb-8 shadow-xl`}>
              <div className="text-white/80 mb-2 flex justify-center"><ScrollText size={48} /></div>
              <h2 className="text-2xl font-bold text-white mb-2 drop-shadow-md">
                 Adventure Awaits!
              </h2>
              <p className="text-white/90 max-w-md mx-auto font-medium">
                  The {currentTheme.name} theme is active. Check the Quest Book below to pick up a new contract and earn your glory!
              </p>
            </div>
          )}

          {/* --- QUEST BOOK (Task Hall) --- */}
          <div>
              <div className="flex justify-between items-center mb-4">
                  <h2 className={`text-lg font-bold flex items-center gap-2 ${currentTheme.textColor} drop-shadow-sm`}>
                    <BrainCircuit className="opacity-80" /> Quest Book
                  </h2>
              </div>

              {/* Book Container */}
              <div className="bg-[#fdfbf7] rounded-r-xl rounded-bl-xl rounded-tl-md shadow-2xl border-l-8 border-slate-700 relative min-h-[500px] flex flex-col">
                  {/* Book Binding Visuals */}
                  <div className="absolute left-0 top-4 bottom-4 w-1 bg-slate-600/50 rounded-full ml-[2px]"></div>

                  {/* Tabs Row */}
                  <div className="flex items-end gap-1 px-4 pt-4 border-b-2 border-[#e5e0d0] overflow-x-auto no-scrollbar">
                      {categories.map((cat, idx) => (
                          <button
                            key={cat}
                            onClick={() => setActiveCategoryIndex(idx)}
                            className={`px-3 py-2 rounded-t-lg text-xs font-bold flex items-center gap-1 transition-all ${
                                activeCategory === cat 
                                    ? 'bg-[#fdfbf7] text-slate-800 border-t-2 border-x-2 border-[#e5e0d0] translate-y-[2px] z-10' 
                                    : 'bg-[#ebe6d8] text-slate-500 hover:bg-[#f2efe4]'
                            }`}
                          >
                              {getCategoryIcon(cat)}
                              <span className="whitespace-nowrap">{cat === 'ALL' ? 'Overview' : cat}</span>
                          </button>
                      ))}
                  </div>

                  {/* Page Content */}
                  <div className="flex-1 p-6 relative">
                      {/* Page Header */}
                      <div className="flex justify-between items-center mb-6 pb-2 border-b border-slate-200">
                          <h3 className="font-pixel text-slate-800 text-lg flex items-center gap-2">
                             {getCategoryIcon(activeCategory)}
                             {getCategoryLabel(activeCategory)}
                          </h3>
                          <span className="text-xs font-bold text-slate-400 bg-slate-100 px-2 py-1 rounded-full">
                              Page {activeCategoryIndex + 1} of {categories.length}
                          </span>
                      </div>

                      {/* Tasks Grid */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 animate-in fade-in slide-in-from-right-4 duration-300" key={activeCategory}>
                          {bookTasks.length === 0 ? (
                            <div className="col-span-2 py-12 text-center opacity-60">
                                <ScrollText className="mx-auto text-slate-300 mb-2" size={48} />
                                <p className="text-slate-500 font-bold italic">This page is empty...</p>
                                <p className="text-slate-400 text-xs">No {activeCategory.toLowerCase()} quests available.</p>
                            </div>
                          ) : (
                            bookTasks.map(task => (
                                <QuestCard
                                    key={task.id}
                                    task={task}
                                    role={UserRole.CHILD}
                                    onAccept={onAcceptAttempt}
                                    onSubmit={onSubmit}
                                    onApprove={() => { }}
                                />
                            ))
                          )}
                      </div>
                  </div>

                  {/* Footer / Page Turners */}
                  <div className="p-4 bg-[#f4f1e8] rounded-br-xl rounded-bl-xl flex justify-between items-center text-slate-500">
                      <button 
                        onClick={handlePrevPage}
                        className="flex items-center gap-1 text-sm font-bold hover:text-slate-800 transition-colors"
                      >
                          <ChevronLeft size={18} /> Prev Page
                      </button>
                      
                      <div className="flex gap-1">
                          {categories.map((_, idx) => (
                              <div key={idx} className={`w-2 h-2 rounded-full ${idx === activeCategoryIndex ? 'bg-slate-800' : 'bg-slate-300'}`}></div>
                          ))}
                      </div>

                      <button 
                        onClick={handleNextPage}
                        className="flex items-center gap-1 text-sm font-bold hover:text-slate-800 transition-colors"
                      >
                          Next Page <ChevronRight size={18} />
                      </button>
                  </div>
              </div>
          </div>

          {/* History */}
          {(completedTasks.length > 0 || pendingTasks.length > 0) && (
            <div className="pt-8 border-t border-white/20">
              <h3 className="text-lg font-bold text-white/60 mb-4 flex items-center gap-2">
                  <HistoryIcon /> Quest Log (History)
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 opacity-75 hover:opacity-100 transition-all duration-300">
                {pendingTasks.map(task => (
                  <QuestCard key={task.id} task={task} role={UserRole.CHILD} onAccept={() => { }} onSubmit={() => { }} onApprove={() => { }} />
                ))}
                {completedTasks.map(task => (
                  <QuestCard key={task.id} task={task} role={UserRole.CHILD} onAccept={() => { }} onSubmit={() => { }} onApprove={() => { }} />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const HistoryIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 12"/><path d="M3 3v9h9"/><path d="M12 7v5l4 2"/></svg>
)

export default ChildDashboard;
