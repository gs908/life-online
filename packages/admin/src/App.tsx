
import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { UserRole, TaskType, TaskStatus, RedemptionRecord } from './types';
import { THEMES } from './constants/themes';
import { Bell } from 'lucide-react';

// API Client（阶段②赛季 + 阶段③任务链路均已接入后端）
import { api, ApiError } from './services/api';
import type { TaskCreate, TaskRead, SeasonRead } from './services/api';

// Auth（阶段①：登录态与家庭上下文）
import { useAuth } from './auth/AuthContext';
import { mapUserRead } from './auth/mapUser';
import LoginPage from './components/LoginPage';

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
import CoinLogsModal from './components/modals/CoinLogsModal';
import SeasonConfigModal from './components/modals/SeasonConfigModal';

const App: React.FC = () => {
  const { t } = useTranslation();
  // --- AUTH（阶段①：真实登录态，Mock 用户已删除） ---
  const { status, user, family, logout, refreshUser } = useAuth();

  const currentUser = useMemo(() => (user ? mapUserRead(user) : null), [user]);

  // 冒险者视角用户：ADVENTURER 即本人；GUILD_MASTER 取家庭中的第一个冒险者
  // （家庭暂无冒险者时回退为本人，待任务接入阶段补"邀请孩子"引导）
  const childUser = useMemo(() => {
    if (!currentUser) return null;
    if (currentUser.role === UserRole.CHILD) return currentUser;
    const firstAdventurer = family?.adventurers?.[0];
    return firstAdventurer ? mapUserRead(firstAdventurer) : currentUser;
  }, [currentUser, family]);

  // --- STATE ---
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

  // 任务链路（阶段③）：请求 + 响应驱动，本地任务状态机已退役
  const [tasks, setTasks] = useState<TaskRead[]>([]);
  const [tasksLoading, setTasksLoading] = useState(true);
  const [redemptionHistory, setRedemptionHistory] = useState<RedemptionRecord[]>([]);

  // UI State
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isReviewModalOpen, setIsReviewModalOpen] = useState(false);
  const [isSubmitModalOpen, setIsSubmitModalOpen] = useState(false);
  const [isAbandonModalOpen, setIsAbandonModalOpen] = useState(false);
  const [isTimeConfigModalOpen, setIsTimeConfigModalOpen] = useState(false);
  const [isCoinLogsOpen, setIsCoinLogsOpen] = useState(false);
  const [isSeasonConfigModalOpen, setIsSeasonConfigModalOpen] = useState(false);

  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [pendingQuestId, setPendingQuestId] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<{ title: string, msg: string } | null>(null);

  const toast = useCallback((title: string, msg: string, ttl = 4000) => {
    setToastMessage({ title, msg });
    setTimeout(() => setToastMessage(null), ttl);
  }, []);

  /** 后端错误统一呈现：msg 为后端人话文案（docs/10 §2.4），网络错误兜底 */
  const showApiError = useCallback((error: unknown, title: string) => {
    if (error instanceof ApiError) {
      toast(title, error.message);
    } else {
      toast(title, t('toast.actionFailedMsg'));
    }
  }, [toast, t]);

  // --- 数据加载：激活赛季 + 任务列表（响应驱动） ---
  const loadBoard = useCallback(async () => {
    setTasksLoading(true);
    try {
      const season = await api.seasons.getActiveSeason();
      setActiveSeason(season);
      if (!season) {
        setTasks([]);
        return;
      }
      const result = await api.tasks.listTasks({ season_id: season.id, page_size: 200 });
      setTasks(result.items);
    } catch (error) {
      showApiError(error, t('toast.loadFailedTitle'));
    } finally {
      setTasksLoading(false);
    }
  }, [showApiError, t]);

  // 登录后拉取赛季上下文（赛季列表/错误态）与任务板（无激活赛季 → 家长端出现创建引导）
  useEffect(() => {
    if (status === 'authenticated') {
      loadSeasons();
      loadBoard();
    }
  }, [status, loadSeasons, loadBoard]);

  // --- EFFECT: TIMED TASK ALERTS（数据源改 TaskRead；本地倍率/押金逻辑已删） ---
  useEffect(() => {
    const checkTimers = setInterval(() => {
      const now = new Date();
      tasks.forEach(task => {
        if (task.type === TaskType.TIMED && task.required_start_time && task.status === TaskStatus.AVAILABLE) {
          const [h, m] = task.required_start_time.split(':').map(Number);
          const deadlineDate = new Date();
          deadlineDate.setHours(h, m, 0, 0);

          const diffMs = deadlineDate.getTime() - now.getTime();
          const diffMins = Math.round(diffMs / 60000);
          const remindMins = task.reminder_minutes_before || 15;

          if (diffMins === remindMins) {
            toast(
              t('toast.questClosingTitle'),
              task.reminder_message || t('toast.questClosingMsg', { minutes: remindMins, title: task.title }),
              8000
            );
          }
        }
      });
    }, 60000);
    return () => clearInterval(checkTimers);
  }, [tasks, t, toast]);

  // --- HANDLERS（全部走后端；押金/罚币/XP 由后端处理，变更后重拉列表与用户） ---

  const handleAddTask = async (payload: TaskCreate) => {
    try {
      await api.tasks.createTask(payload);
      setIsAddModalOpen(false);
      toast(t('toast.taskCreatedTitle'), t('toast.taskCreatedMsg'));
      await loadBoard();
    } catch (error) {
      // 422 validation_error 等：表单保留，toast 提示后端字段错误
      showApiError(error, t('toast.taskCreateFailedTitle'));
    }
  };

  const startQuest = async (id: string) => {
    try {
      await api.tasks.startTask(id); // 后端扣押金；余额不足时抛 validation_error
      await Promise.all([loadBoard(), refreshUser()]);
    } catch (error) {
      showApiError(error, t('toast.startFailedTitle'));
    }
  };

  const handleAcceptAttempt = (id: string) => {
    const activeQuest = tasks.find(t => t.status === TaskStatus.IN_PROGRESS && t.assignee_child_id === childUser?.childId);
    if (activeQuest) {
      if (activeQuest.id === id) return;
      // UI 门禁：同一时间一个任务（后端不限制，纯前端体验约束）
      setPendingQuestId(id);
      setSelectedTaskId(activeQuest.id);
      setIsAbandonModalOpen(true);
    } else {
      startQuest(id);
    }
  };

  const [abandoning, setAbandoning] = useState(false);

  const handleAbandonQuest = async () => {
    if (!selectedTaskId || abandoning) return;
    setAbandoning(true);
    try {
      const task = await api.tasks.abandonTask(selectedTaskId); // 后端罚币/退款
      // coin_delta = refund - deposit（后端语义）：负数=被扣罚金，0=全额退还
      if (task.coin_delta < 0) {
        toast(t('toast.penaltyTitle'), t('toast.penaltyMsg', { amount: -task.coin_delta }));
      } else {
        toast(t('toast.depositReturnedTitle'), t('toast.depositReturnedMsg', { deposit: task.time_deposit }));
      }
      await Promise.all([loadBoard(), refreshUser()]);
      if (pendingQuestId) {
        const next = pendingQuestId;
        setPendingQuestId(null);
        await startQuest(next);
      }
    } catch (error) {
      showApiError(error, t('toast.abandonFailedTitle'));
    } finally {
      setAbandoning(false);
      setIsAbandonModalOpen(false);
      setSelectedTaskId(null);
    }
  };

  const handleAbandonCurrent = (id: string) => {
    setSelectedTaskId(id);
    setPendingQuestId(null);
    setIsAbandonModalOpen(true);
  };

  const [submitting, setSubmitting] = useState(false);

  /** 提交流：先 POST /sys/uploads(task_proof) 拿 object_key，再 submit（docs/10 §4 阶段③） */
  const handleSubmitTask = async (file: File) => {
    if (!selectedTaskId || submitting) return;
    setSubmitting(true);
    try {
      const uploaded = await api.uploads.uploadFile(file, 'task_proof');
      await api.tasks.submitTask(selectedTaskId, { proof_object_key: uploaded.object_key });
      setIsSubmitModalOpen(false);
      setSelectedTaskId(null);
      toast(t('toast.taskSubmittedTitle'), t('toast.taskSubmittedMsg'));
      await loadBoard();
    } catch (error) {
      showApiError(error, t('toast.submitFailedTitle'));
    } finally {
      setSubmitting(false);
    }
  };

  const [approving, setApproving] = useState(false);

  const handleApproveTask = async (taskId: string, rating: number, comment: string) => {
    if (approving) return;
    setApproving(true);
    try {
      await api.tasks.approveTask(taskId, { rating, comment: comment || undefined }); // 后端发 XP、退/扣币
      setIsReviewModalOpen(false);
      toast(t('toast.approveSuccessTitle'), t('toast.approveSuccessMsg', { rating }));
      await Promise.all([loadBoard(), refreshUser()]);
    } catch (error) {
      showApiError(error, t('toast.approveFailedTitle'));
    } finally {
      setApproving(false);
    }
  };

  const handleRecordUsage = (privilegeTitle: string) => {
    const record: RedemptionRecord = {
      id: Math.random().toString(36).substr(2, 9),
      privilegeTitle,
      date: new Date().toISOString(),
      user: childUser?.name ?? ''
    };
    setRedemptionHistory(prev => [record, ...prev]);
    toast(t('toast.usageRecordedTitle'), t('toast.usageRecordedMsg', { title: privilegeTitle }), 3000);
  };

  const handleDeleteTask = async (id: string) => {
    if (!window.confirm(t('parent.deleteConfirm'))) return;
    try {
      await api.tasks.deleteTask(id);
      await loadBoard();
    } catch (error) {
      showApiError(error, t('toast.deleteFailedTitle'));
    }
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

  // --- HELPER DATA FOR RENDER（任务列表已按激活赛季服务端过滤） ---
  const currentSeasonTheme = THEMES[activeSeason?.theme_id ?? 'DEFAULT'] || THEMES.DEFAULT;
  const activeQuest = tasks.find(t => t.status === TaskStatus.IN_PROGRESS && t.assignee_child_id === childUser?.childId);
  const availableTasks = tasks.filter(t => t.status === TaskStatus.AVAILABLE);
  const completedTasks = tasks.filter(t => t.status === TaskStatus.COMPLETED);
  const pendingTasks = tasks.filter(t => t.status === TaskStatus.PENDING_REVIEW);

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

  const currentTheme = THEMES[activeSeason?.theme_id ?? 'DEFAULT'] || THEMES.DEFAULT;

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

      {/* HEADER（真实用户 + 真实激活赛季） */}
      <Header
        currentSeason={activeSeason?.name ?? t('header.noSeason')}
        currentUser={currentUser}
        onLogout={logout}
      />

      <main className="flex-1 overflow-y-auto w-full">
        {tasksLoading ? (
          <div className="h-full flex items-center justify-center" role="status" aria-live="polite">
            <div className="text-slate-400 text-sm animate-pulse">{t('common.loading')}</div>
          </div>
        ) : currentUser.role === UserRole.CHILD ? (
          <div className="max-w-7xl mx-auto p-4 md:p-6 lg:p-8">
             <ChildDashboard
                childUser={childUser}
                currentTheme={currentTheme}
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
                        tasks={tasks}
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
                        onViewCoinLogs={() => setIsCoinLogsOpen(true)}
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
        submitting={submitting}
      />

      <ReviewTaskModal
        isOpen={isReviewModalOpen}
        onClose={() => setIsReviewModalOpen(false)}
        task={tasks.find(t => t.id === selectedTaskId)}
        onApprove={handleApproveTask}
        approving={approving}
      />

      <AbandonQuestModal
        isOpen={isAbandonModalOpen}
        onClose={() => setIsAbandonModalOpen(false)}
        onConfirm={handleAbandonQuest}
        confirming={abandoning}
        taskTitle={tasks.find(t => t.id === selectedTaskId)?.title}
      />

      <TimeConfigModal
        isOpen={isTimeConfigModalOpen}
        onClose={() => setIsTimeConfigModalOpen(false)}
        onToast={showToast}
      />

      <CoinLogsModal
        isOpen={isCoinLogsOpen}
        onClose={() => setIsCoinLogsOpen(false)}
        family={family}
        onToast={showToast}
        onAdjusted={refreshUser}
      />

      <SeasonConfigModal
        isOpen={isSeasonConfigModalOpen}
        onClose={() => setIsSeasonConfigModalOpen(false)}
        seasons={seasons}
        openInCreate={!activeSeason && !seasonLoading}
        onRefresh={async () => {
          // 赛季创建/激活/停用都会改变任务板依赖的激活赛季，两处一起重拉
          await loadSeasons();
          await loadBoard();
        }}
        onToast={showToast}
      />
    </div>
  );
};

export default App;
