
import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { User, Task, UserRole, TaskType, TaskStatus, RedemptionRecord, TimeConfig } from './types';
import { THEMES } from './constants/themes';
import { Bell } from 'lucide-react';

// Auth（阶段①：登录态与家庭上下文）
import { useAuth } from './auth/AuthContext';
import { mapUserRead } from './auth/mapUser';
import LoginPage from './components/LoginPage';

// API（阶段②：赛季接入真实后端）
import { api, ApiError } from './services/api';
import type { SeasonRead } from './services/api';

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
  const { t } = useTranslation();
  // --- AUTH（阶段①：真实登录态，Mock 用户已删除） ---
  const { status, user, family, logout } = useAuth();

  const currentUser = useMemo(() => (user ? mapUserRead(user) : null), [user]);

  // 冒险者视角用户：ADVENTURER 即本人；GUILD_MASTER 取家庭中的第一个冒险者
  // （家庭暂无冒险者时回退为本人，待任务接入阶段补"邀请孩子"引导）
  const childUserFromAuth = useMemo(() => {
    if (!currentUser) return null;
    if (currentUser.role === UserRole.CHILD) return currentUser;
    const firstAdventurer = family?.adventurers?.[0];
    return firstAdventurer ? mapUserRead(firstAdventurer) : currentUser;
  }, [currentUser, family]);

  // --- STATE ---
  // 本地镜像：任务全链路（阶段③）接入后端后，以下本地增减逻辑整体退役
  const [childUser, setChildUser] = useState<User | null>(childUserFromAuth);

  useEffect(() => {
    setChildUser(childUserFromAuth);
  }, [childUserFromAuth]);

  // Season State（阶段②：真实后端；DEFAULT_SEASON 已下线）
  const [activeSeason, setActiveSeason] = useState<SeasonRead | null>(null);
  const [seasons, setSeasons] = useState<SeasonRead[]>([]);
  const [seasonError, setSeasonError] = useState<string | null>(null);
  const [seasonLoading, setSeasonLoading] = useState(true);
  const [showSeasonHistory, setShowSeasonHistory] = useState(false);

  const loadSeasons = useCallback(async () => {
    setSeasonLoading(true);
    setSeasonError(null);
    try {
      const [active, list] = await Promise.all([
        api.seasons.getActiveSeason(),
        api.seasons.listSeasons(true),
      ]);
      setActiveSeason(active);
      setSeasons(list);
    } catch (error) {
      setSeasonError(error instanceof ApiError ? error.message : t('parent.seasonLoadFailedPlain'));
    } finally {
      setSeasonLoading(false);
    }
  }, [t]);

  // 登录后拉取赛季上下文（无激活赛季 → 家长端出现创建引导）
  useEffect(() => {
    if (status === 'authenticated') {
      loadSeasons();
    }
  }, [status, loadSeasons]);

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
              title: t('toast.questClosingTitle'),
              msg: task.reminderMessage || t('toast.questClosingMsg', { minutes: remindMins, title: task.title })
            });
            setTimeout(() => setToastMessage(null), 8000);
          }
        }
      });
    }, 60000);
    return () => clearInterval(checkTimers);
  }, [tasks, t]);

  // --- HANDLERS ---

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
        setToastMessage({ title: t('toast.insufficientCoinsTitle'), msg: t('toast.insufficientCoinsMsg', { deposit }) });
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
            setToastMessage({ title: t('toast.penaltyTitle'), msg: t('toast.penaltyMsg', { amount: deposit - refund }) });
            setTimeout(() => setToastMessage(null), 4000);
        } else {
            setToastMessage({ title: t('toast.depositReturnedTitle'), msg: t('toast.depositReturnedMsg', { deposit }) });
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
          setToastMessage({ title: t('toast.levelUpTitle'), msg: t('toast.levelUpMsg', { name: prev.name, level: newLevel }) });
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
    setToastMessage({ title: t('toast.usageRecordedTitle'), msg: t('toast.usageRecordedMsg', { title: privilegeTitle }) });
    setTimeout(() => setToastMessage(null), 3000);
  };

  const handleDeleteTask = (id: string) => {
    setTasks(prev => prev.filter(t => t.id !== id));
  };

  const handleTimeConfigSave = (newConfig: TimeConfig) => {
      setTimeConfig(newConfig);
      setToastMessage({ title: t('toast.configSavedTitle'), msg: t('toast.configSavedMsg') });
      setTimeout(() => setToastMessage(null), 3000);
  };

  // 统一 toast（赛季 CRUD 成功反馈从 Modal 回流，避免多个 setTimeout 各自为政）
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showToast = useCallback((title: string, msg: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToastMessage({ title, msg });
    toastTimer.current = setTimeout(() => setToastMessage(null), 4000);
  }, []);
  useEffect(() => () => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
  }, []);

  // --- HELPER DATA FOR RENDER ---
  const currentSeasonTheme = THEMES[activeSeason?.theme_id ?? 'DEFAULT'] || THEMES.DEFAULT;
  const filteredTasks = activeSeason ? tasks.filter(t => t.seasonId === activeSeason.id) : [];
  const activeQuest = filteredTasks.find(t => t.status === TaskStatus.IN_PROGRESS && t.assigneeId === childUser?.id);
  const availableTasks = filteredTasks.filter(t => t.status === TaskStatus.AVAILABLE);
  const completedTasks = filteredTasks.filter(t => t.status === TaskStatus.COMPLETED);
  const pendingTasks = filteredTasks.filter(t => t.status === TaskStatus.PENDING_REVIEW);

  // 登录门卫：loading → 启动屏；anonymous → 登录页（401 刷新失败也会广播回这里）
  if (status === 'loading') {
    return (
      <div className="h-full flex items-center justify-center bg-slate-900" role="status" aria-live="polite">
        <div className="text-slate-400 text-sm animate-pulse">{t('common.loading')}</div>
      </div>
    );
  }
  if (status === 'anonymous' || !currentUser || !childUser) {
    return <LoginPage />;
  }

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

      {/* HEADER（真实用户；角色切换已删除，换角色 = 登出后以另一角色重新登录） */}
      <Header
        currentSeason={activeSeason?.name ?? t('header.noSeason')}
        currentUser={currentUser}
        onLogout={logout}
      />

      <main className="flex-1 overflow-y-auto w-full">
        {currentUser.role === UserRole.CHILD ? (
          <div className="max-w-7xl mx-auto p-4 md:p-6 lg:p-8">
             <ChildDashboard
                childUser={childUser}
                currentTheme={currentSeasonTheme}
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
                        currentTheme={currentSeasonTheme}
                        seasonError={seasonError}
                        onRetrySeasons={loadSeasons}
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
        narrativeContext={activeSeason?.narrative_context ?? ''}
        seasonId={activeSeason?.id ?? ''}
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
        seasons={seasons}
        openInCreate={!activeSeason && !seasonLoading}
        onRefresh={loadSeasons}
        onToast={showToast}
      />
    </div>
  );
};

export default App;
