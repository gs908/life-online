
import React, { useState, useEffect } from 'react';
import { User, Task, Season, UserRole, TaskType, TaskStatus, RedemptionRecord, TimeConfig } from './types';
import { THEMES } from './constants/themes';
import { Bell } from 'lucide-react';

// Components
import Header from './components/Header';
import ChildDashboard from './components/dashboards/ChildDashboard';
import ParentDashboard from './components/dashboards/ParentDashboard';
import SeasonHistory from './components/dashboards/SeasonHistory';

// Modals
import AddTaskModal from './components/modals/AddTaskModal';
import SubmitTaskModal from './components/modals/SubmitTaskModal';
import ReviewTaskModal from './components/modals/ReviewTaskModal';
import AbandonQuestModal from './components/modals/AbandonQuestModal';
import TimeConfigModal from './components/modals/TimeConfigModal';
import SeasonConfigModal from './components/modals/SeasonConfigModal';

// --- MOCK DATA ---
const DEFAULT_TIME_CONFIG: TimeConfig = {
    defaultDailyAllowance: 100,
    exceptions: { 0: 200, 6: 200 } // Weekend bonus
};

const DEFAULT_SEASON: Season = {
  id: 'season_1',
  name: 'Winter Semester 2024',
  themeId: 'FROSTBOUND',
  narrativeContext: 'The Frost Giants are encroaching on the village. We must strengthen our defenses and gather supplies before the Long Night.',
  startDate: new Date().toISOString(),
  isActive: true
};

const MOCK_USERS: User[] = [
  { 
      id: 'u1', 
      name: 'Parent (Guild Master)', 
      role: UserRole.PARENT, 
      level: 99, 
      xp: 0, 
      avatar: '👑', 
      privilegesUnlocked: [], 
      timeCoins: 9999, 
      dailyAbandonCount: 0 
  },
  { 
      id: 'u2', 
      name: 'Leo (Adventurer)', 
      role: UserRole.CHILD, 
      level: 2, 
      xp: 1250, 
      avatar: '⚔️', 
      privilegesUnlocked: [1, 2],
      timeCoins: 100, // Initial balance
      dailyAbandonCount: 0,
      lastLoginDate: new Date().toDateString()
  },
];

const INITIAL_TASKS: Task[] = [
  {
    id: 't1',
    title: 'Fortify the Bedding',
    description: 'Make the bed neatly.',
    loreSnippet: 'A well-kept barracks boosts morale against the cold.',
    xpReward: 50,
    type: TaskType.DAILY,
    status: TaskStatus.AVAILABLE,
    seasonId: 'season_1',
    timeDeposit: 10
  },
  {
    id: 't2',
    title: 'Decipher the Runes (Math)',
    description: 'Complete math worksheet.',
    loreSnippet: 'Calculate the trajectory of the ice catapults.',
    xpReward: 150,
    type: TaskType.CHALLENGE,
    status: TaskStatus.AVAILABLE,
    seasonId: 'season_1',
    timeDeposit: 20
  },
  {
    id: 't3',
    title: 'Bardic Practice',
    description: '30 mins of piano.',
    xpReward: 100,
    type: TaskType.TIMED,
    requiredStartTime: '18:00',
    reminderMessage: "The Ice Queen demands a song before sunset!",
    reminderMinutesBefore: 30,
    status: TaskStatus.AVAILABLE,
    seasonId: 'season_1',
    timeDeposit: 30
  }
];

const App: React.FC = () => {
  // --- STATE ---
  const [currentUser, setCurrentUser] = useState<User>(MOCK_USERS[0]);
  const [childUser, setChildUser] = useState<User>(MOCK_USERS[1]);
  
  // Season State
  const [activeSeason, setActiveSeason] = useState<Season>(DEFAULT_SEASON);
  const [seasonHistory, setSeasonHistory] = useState<Season[]>([]);
  const [showSeasonHistory, setShowSeasonHistory] = useState(false);

  const [tasks, setTasks] = useState<Task[]>(INITIAL_TASKS);
  const [redemptionHistory, setRedemptionHistory] = useState<RedemptionRecord[]>([]);
  const [timeConfig, setTimeConfig] = useState<TimeConfig>(DEFAULT_TIME_CONFIG);

  // UI State
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isReviewModalOpen, setIsReviewModalOpen] = useState(false);
  const [isSubmitModalOpen, setIsSubmitModalOpen] = useState(false);
  const [isAbandonModalOpen, setIsAbandonModalOpen] = useState(false);
  const [isTimeConfigModalOpen, setIsTimeConfigModalOpen] = useState(false);
  const [isSeasonConfigModalOpen, setIsSeasonConfigModalOpen] = useState(false);

  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [pendingQuestId, setPendingQuestId] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<{ title: string, msg: string } | null>(null);

  // --- EFFECT: DAILY RESET ---
  useEffect(() => {
    const todayStr = new Date().toDateString();
    if (childUser.lastLoginDate !== todayStr) {
        // Perform Daily Reset
        const dayIndex = new Date().getDay();
        const dailyAllowance = timeConfig.exceptions[dayIndex] ?? timeConfig.defaultDailyAllowance;

        setChildUser(prev => ({
            ...prev,
            timeCoins: dailyAllowance,
            dailyAbandonCount: 0,
            lastLoginDate: todayStr
        }));

        setToastMessage({ title: "New Day!", msg: `Daily Time Coins reset to ${dailyAllowance}.` });
        setTimeout(() => setToastMessage(null), 5000);
    }
  }, [timeConfig, childUser.lastLoginDate]);

  // --- EFFECT: TIMED TASK ALERTS ---
  useEffect(() => {
    const checkTimers = setInterval(() => {
      const now = new Date();
      tasks.forEach(task => {
        if (task.type === TaskType.TIMED && task.requiredStartTime && task.status === TaskStatus.AVAILABLE) {
          const [h, m] = task.requiredStartTime.split(':').map(Number);
          const deadlineDate = new Date();
          deadlineDate.setHours(h, m, 0, 0);

          const diffMs = deadlineDate.getTime() - now.getTime();
          const diffMins = Math.round(diffMs / 60000);
          const remindMins = task.reminderMinutesBefore || 15;

          if (diffMins === remindMins) {
            setToastMessage({
              title: "Quest Opportunity Closing!",
              msg: task.reminderMessage || `You have ${remindMins} minutes to start ${task.title}!`
            });
            setTimeout(() => setToastMessage(null), 8000);
          }
        }
      });
    }, 60000);
    return () => clearInterval(checkTimers);
  }, [tasks]);

  // --- HANDLERS ---

  const switchUser = (role: UserRole) => {
    if (role === UserRole.PARENT) setCurrentUser(MOCK_USERS[0]);
    else setCurrentUser(childUser);
  };

  const handleAddTask = (newTask: Task) => {
    setTasks([...tasks, newTask]);
    setIsAddModalOpen(false);
  };

  const startQuest = (id: string) => {
    const task = tasks.find(t => t.id === id);
    if (!task) return;

    // DEPOSIT CHECK
    const deposit = task.timeDeposit || 10;
    if (childUser.timeCoins < deposit) {
        setToastMessage({ title: "Insufficient Coins", msg: `You need ${deposit} Time Coins to accept this quest.` });
        setTimeout(() => setToastMessage(null), 4000);
        return;
    }

    // Deduct Deposit
    setChildUser(prev => ({ ...prev, timeCoins: prev.timeCoins - deposit }));

    setTasks(prev => prev.map(t =>
      t.id === id
        ? { ...t, status: TaskStatus.IN_PROGRESS, assigneeId: childUser.id, startedAt: new Date().toISOString() }
        : t
    ));
  };

  const handleAcceptAttempt = (id: string) => {
    const activeQuest = tasks.find(t => t.status === TaskStatus.IN_PROGRESS && t.assigneeId === childUser.id);
    if (activeQuest) {
      if (activeQuest.id === id) return;
      setPendingQuestId(id);
      setSelectedTaskId(activeQuest.id);
      setIsAbandonModalOpen(true);
    } else {
      startQuest(id);
    }
  };

  const handleAbandonQuest = () => {
    if (!selectedTaskId) return;

    const task = tasks.find(t => t.id === selectedTaskId);
    if (task) {
        // Refund Logic
        const deposit = task.timeDeposit || 10;
        let refund = deposit;
        
        // Penalty if abandoned > 3 times
        if (childUser.dailyAbandonCount >= 3) {
            refund = Math.floor(deposit * 0.6); // 40% penalty, so 60% refund
            setToastMessage({ title: "Penalty Applied", msg: `Frequent abandonment! Lost ${deposit - refund} coins.` });
            setTimeout(() => setToastMessage(null), 4000);
        } else {
            setToastMessage({ title: "Deposit Returned", msg: `${deposit} coins refunded.` });
            setTimeout(() => setToastMessage(null), 3000);
        }

        setChildUser(prev => ({ 
            ...prev, 
            timeCoins: prev.timeCoins + refund,
            dailyAbandonCount: prev.dailyAbandonCount + 1 
        }));
    }

    setTasks(prev => prev.map(t =>
      t.id === selectedTaskId
        ? { ...t, status: TaskStatus.AVAILABLE, assigneeId: undefined, startedAt: undefined }
        : t
    ));

    if (pendingQuestId) {
       // Ideally we auto-trigger startQuest(pendingQuestId) but state updates are async.
       // For UX simplicity, we just clear pending and let user select new quest.
       setPendingQuestId(null);
    }

    setIsAbandonModalOpen(false);
    setSelectedTaskId(null);
  };

  const handleAbandonCurrent = (id: string) => {
    setSelectedTaskId(id);
    setPendingQuestId(null);
    setIsAbandonModalOpen(true);
  };

  const handleSubmitTask = (proofImage: string | null) => {
    if (!selectedTaskId) return;
    setTasks(prev => prev.map(t => t.id === selectedTaskId ? { ...t, status: TaskStatus.PENDING_REVIEW, proofImage: proofImage || undefined } : t));
    setIsSubmitModalOpen(false);
  };

  const handleApproveTask = (taskId: string, rating: number, comment: string) => {
    const task = tasks.find(t => t.id === taskId);
    if (!task) return;

    // REFUND DEPOSIT
    const deposit = task.timeDeposit || 10;
    setChildUser(prev => ({ ...prev, timeCoins: prev.timeCoins + deposit }));

    // XP Logic
    let multiplier = 1;
    if (rating === 5) multiplier *= 1.2;
    else if (rating === 4) multiplier *= 1.1;
    else if (rating < 3) multiplier *= 0.8;

    if (task.requiredStartTime) {
      const [h, m] = task.requiredStartTime.split(':').map(Number);
      const deadline = new Date();
      deadline.setHours(h, m, 0, 0);
      if (new Date() > deadline) multiplier *= 0.8;
    }

    if (task.startedAt) {
      const diffMins = (new Date().getTime() - new Date(task.startedAt).getTime()) / 60000;
      if (diffMins < 60) multiplier *= 1.1;
    }

    const finalXP = Math.round(task.xpReward * multiplier);

    setTasks(prev => prev.map(t => t.id === taskId ? { ...t, status: TaskStatus.COMPLETED, rating } : t));

    setChildUser(prev => {
        const newXP = prev.xp + finalXP;
        const xpNeeded = prev.level * 1000;
        let newLevel = prev.level;
        let remainingXP = newXP;
    
        if (remainingXP >= xpNeeded) {
          newLevel += 1;
          remainingXP = remainingXP - xpNeeded;
          setToastMessage({ title: "LEVEL UP!", msg: `${prev.name} is now Level ${newLevel}!` });
          setTimeout(() => setToastMessage(null), 5000);
        }
        return { ...prev, xp: remainingXP, level: newLevel };
    });

    setIsReviewModalOpen(false);
  };

  const handleRecordUsage = (privilegeTitle: string) => {
    const record: RedemptionRecord = {
      id: Math.random().toString(36).substr(2, 9),
      privilegeTitle,
      date: new Date().toISOString(),
      user: childUser.name
    };
    setRedemptionHistory(prev => [record, ...prev]);
    setToastMessage({ title: "Usage Recorded", msg: `${privilegeTitle} consumed.` });
    setTimeout(() => setToastMessage(null), 3000);
  };

  const handleDeleteTask = (id: string) => {
    setTasks(prev => prev.filter(t => t.id !== id));
  };

  const handleTimeConfigSave = (newConfig: TimeConfig) => {
      setTimeConfig(newConfig);
      setToastMessage({ title: "Config Saved", msg: "Time coin settings updated." });
      setTimeout(() => setToastMessage(null), 3000);
  };

  const handleSeasonSave = (newSeason: Season) => {
    setActiveSeason(newSeason);
    setToastMessage({ title: "Season Updated", msg: `Theme changed to ${THEMES[newSeason.themeId].name}` });
    setTimeout(() => setToastMessage(null), 3000);
  };

  // --- HELPER DATA FOR RENDER ---
  const filteredTasks = tasks.filter(t => t.seasonId === activeSeason.id);
  const activeQuest = filteredTasks.find(t => t.status === TaskStatus.IN_PROGRESS && t.assigneeId === childUser.id);
  const availableTasks = filteredTasks.filter(t => t.status === TaskStatus.AVAILABLE);
  const completedTasks = filteredTasks.filter(t => t.status === TaskStatus.COMPLETED);
  const pendingTasks = filteredTasks.filter(t => t.status === TaskStatus.PENDING_REVIEW);

  return (
    <div className="flex flex-col h-full font-sans relative">

      {/* TOAST NOTIFICATION */}
      {toastMessage && (
        <div className="absolute top-4 left-1/2 transform -translate-x-1/2 z-[200] w-11/12 max-w-md animate-in slide-in-from-top-4 duration-300">
          <div className="bg-slate-800 text-white rounded-lg shadow-2xl p-4 border-l-4 border-yellow-500 flex gap-3">
            <div className="p-2 bg-slate-700 rounded-full h-fit">
              <Bell size={20} className="text-yellow-400 animate-pulse" />
            </div>
            <div>
              <h4 className="font-bold text-yellow-400">{toastMessage.title}</h4>
              <p className="text-sm text-slate-200">{toastMessage.msg}</p>
            </div>
          </div>
        </div>
      )}

      {/* HEADER (Note: Header takes simple SeasonType logic in original, we can update or just pass a derived value/string) */}
      <Header
        currentSeason={activeSeason.name as any} // Cast for visual compatibility or update Header later
        currentUser={currentUser}
        onSwitchUser={switchUser}
      />

      <main className="flex-1 overflow-y-auto w-full">
        {currentUser.role === UserRole.CHILD ? (
          <div className="max-w-7xl mx-auto p-4 md:p-6 lg:p-8">
             <ChildDashboard
                childUser={childUser}
                currentTheme={THEMES[activeSeason.themeId] || THEMES.DEFAULT}
                tasks={tasks}
                activeQuest={activeQuest}
                availableTasks={availableTasks}
                completedTasks={completedTasks}
                pendingTasks={pendingTasks}
                onAcceptAttempt={handleAcceptAttempt}
                onSubmit={(id) => { setSelectedTaskId(id); setIsSubmitModalOpen(true); }}
                onAbandonCurrent={handleAbandonCurrent}
             />
          </div>
        ) : (
          <div className="bg-slate-100 min-h-full p-4 md:p-6 lg:p-8">
             <div className="max-w-7xl mx-auto">
                 {showSeasonHistory ? (
                     <SeasonHistory 
                        historySeasons={seasonHistory} 
                        allTasks={tasks} 
                        onBack={() => setShowSeasonHistory(false)} 
                     />
                 ) : (
                     <ParentDashboard
                        childUser={childUser}
                        tasks={filteredTasks}
                        activeQuest={activeQuest}
                        availableTasks={availableTasks}
                        pendingTasks={pendingTasks}
                        redemptionHistory={redemptionHistory}
                        activeSeason={activeSeason}
                        onOpenSeasonConfig={() => setIsSeasonConfigModalOpen(true)}
                        onViewHistory={() => setShowSeasonHistory(true)}
                        onOpenAddModal={() => setIsAddModalOpen(true)}
                        onRecordUsage={handleRecordUsage}
                        onReviewTask={(id) => { setSelectedTaskId(id); setIsReviewModalOpen(true); }}
                        onDeleteTask={handleDeleteTask}
                        onOpenTimeConfig={() => setIsTimeConfigModalOpen(true)}
                     />
                 )}
             </div>
          </div>
        )}
      </main>

      {/* --- MODALS --- */}
      <AddTaskModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onAdd={handleAddTask}
        narrativeContext={activeSeason.narrativeContext}
        seasonId={activeSeason.id}
        childLevel={childUser.level}
      />

      <SubmitTaskModal
        isOpen={isSubmitModalOpen}
        onClose={() => setIsSubmitModalOpen(false)}
        onSubmit={handleSubmitTask}
      />

      <ReviewTaskModal
        isOpen={isReviewModalOpen}
        onClose={() => setIsReviewModalOpen(false)}
        task={tasks.find(t => t.id === selectedTaskId)}
        onApprove={handleApproveTask}
      />

      <AbandonQuestModal
        isOpen={isAbandonModalOpen}
        onClose={() => setIsAbandonModalOpen(false)}
        onConfirm={handleAbandonQuest}
        taskTitle={tasks.find(t => t.id === selectedTaskId)?.title}
      />

      <TimeConfigModal
        isOpen={isTimeConfigModalOpen}
        onClose={() => setIsTimeConfigModalOpen(false)}
        config={timeConfig}
        onSave={handleTimeConfigSave}
      />

      <SeasonConfigModal
        isOpen={isSeasonConfigModalOpen}
        onClose={() => setIsSeasonConfigModalOpen(false)}
        currentSeason={activeSeason}
        onSave={handleSeasonSave}
      />
    </div>
  );
};

export default App;
