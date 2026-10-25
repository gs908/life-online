
import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { UserRole, TaskType, TaskStatus } from './types';
import { THEMES } from './constants/themes';
import { Bell } from 'lucide-react';

// API Client（阶段②赛季 + 阶段③任务链路均已接入后端）
import { api, ApiError } from './services/api';
import type { AddTaskSubmit } from './components/modals/AddTaskModal';
import type { TaskCreate, TaskRead, SeasonRead, PrivilegeRead, RedemptionRead, UserPrivilegeRead, TaskTemplateRead, TaskGenerateResult } from './services/api';
import { localToday } from './utils/date';

// Auth（阶段①：登录态与家庭上下文）
import { useAuth } from './auth/AuthContext';
import { mapUserRead } from './auth/mapUser';
import LoginPage from './components/LoginPage';

// Components
import Header from './components/Header';
import ChildDashboard from './components/dashboards/ChildDashboard';
import ParentDashboard from './components/dashboards/ParentDashboard';
import SeasonHistory from './components/dashboards/SeasonHistory';
import TaskTemplateManager from './components/TaskTemplateManager';
import type { TaskTemplateCategoryIntent } from './components/taskTemplateUtils';

// Modals
import AddTaskModal from './components/modals/AddTaskModal';
import TuneTaskModal from './components/modals/TuneTaskModal';
import SubmitTaskModal from './components/modals/SubmitTaskModal';
import ReviewTaskModal from './components/modals/ReviewTaskModal';
import AbandonQuestModal from './components/modals/AbandonQuestModal';
import TimeConfigModal from './components/modals/TimeConfigModal';
import CoinLogsModal from './components/modals/CoinLogsModal';
import SeasonConfigModal from './components/modals/SeasonConfigModal';
import PrivilegeConfigModal from './components/modals/PrivilegeConfigModal';

/**
 * 同一时间一个任务（前端体验约束，后端不限制）。被驳回的任务优先作为「当前任务」，
 * 避免多模板并存时被另一个普通 IN_PROGRESS 顶掉而看不到驳回原因（DEV-57）。
 */
const pickActiveQuest = (tasks: TaskRead[], childId: string | null | undefined) => {
  const inProgress = tasks.filter(t => t.status === TaskStatus.IN_PROGRESS && t.assignee_child_id === childId);
  return inProgress.find(t => t.rejected) ?? inProgress[0];
};

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

  // 特权链路（阶段④-b，契约 §9/§10）：模板树 + 已解锁 + 使用记录，全部后端（redemptionHistory Mock 已退役）
  const [privilegeTemplates, setPrivilegeTemplates] = useState<PrivilegeRead[]>([]);
  const [privilegeUnlocks, setPrivilegeUnlocks] = useState<UserPrivilegeRead[]>([]);
  const [privilegeUses, setPrivilegeUses] = useState<RedemptionRead[]>([]);
  const [privilegesLoading, setPrivilegesLoading] = useState(true);

  // UI State
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isReviewModalOpen, setIsReviewModalOpen] = useState(false);
  const [isSubmitModalOpen, setIsSubmitModalOpen] = useState(false);
  const [isAbandonModalOpen, setIsAbandonModalOpen] = useState(false);
  const [isTimeConfigModalOpen, setIsTimeConfigModalOpen] = useState(false);
  const [isCoinLogsOpen, setIsCoinLogsOpen] = useState(false);
  const [isSeasonConfigModalOpen, setIsSeasonConfigModalOpen] = useState(false);
  const [isPrivilegeConfigOpen, setIsPrivilegeConfigOpen] = useState(false);

  // 父母端视图 Tab（DEV-35：任务板 / 任务模板管理，Miss.D「独立 Tab」）
  const [parentView, setParentView] = useState<'board' | 'templates'>('board');
  // 任务模板链路：AddTaskModal 双出口（instance/template/update）+ 管理视图重拉信号
  const [editingTemplate, setEditingTemplate] = useState<TaskTemplateRead | null>(null);
  const [addModalDefaultCategory, setAddModalDefaultCategory] = useState<TaskTemplateCategoryIntent>('once');
  const [templateActionBusy, setTemplateActionBusy] = useState(false);
  const [templatesRefreshSignal, setTemplatesRefreshSignal] = useState(0);

  // 契约 §6B：选模板 → 生成（含目标日期与微调）+ 生成后微调
  /** 由 AddTaskModal 新建非 once 模板后的生成成功回调（DEV-51） */
  const [instancesRefreshSignal, setInstancesRefreshSignal] = useState(0);
  const [tuningTask, setTuningTask] = useState<TaskRead | null>(null);
  // 每次渲染取一次（纯字符串计算）：不要用 useMemo([]) 冻结在挂载那一刻，
  // 否则跨零点后「已排期 / 已投放」分组会错。字符串按值比较，不会造成额外重渲染。
  const today = localToday();

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

  // 特权数据（阶段④-b）：模板 + 已解锁 + 使用记录；解锁集合随冒险者档案变化，故依赖 childId
  const loadPrivileges = useCallback(async () => {
    setPrivilegesLoading(true);
    try {
      const childId = childUser?.childId ?? undefined;
      const [templates, unlocks, uses] = await Promise.all([
        api.coins.listPrivilegeTemplates(),
        api.coins.listPrivilegeUnlocks(childId),
        api.coins.listPrivilegeUses({ child_id: childId, page_size: 20 }),
      ]);
      setPrivilegeTemplates(templates);
      setPrivilegeUnlocks(unlocks);
      setPrivilegeUses(uses.items);
    } catch (error) {
      showApiError(error, t('toast.loadFailedTitle'));
    } finally {
      setPrivilegesLoading(false);
    }
  }, [childUser?.childId, showApiError, t]);

  useEffect(() => {
    if (status === 'authenticated' && childUser) {
      loadPrivileges();
    }
  }, [status, childUser, loadPrivileges]);

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

  /** @returns 是否创建成功（失败已 toast，弹窗保留） */
  const handleAddTask = async (payload: TaskCreate): Promise<boolean> => {
    try {
      await api.tasks.createTask(payload);
      setIsAddModalOpen(false);
      toast(t('toast.taskCreatedTitle'), t('toast.taskCreatedMsg'));
      await loadBoard();
      return true;
    } catch (error) {
      // 422 validation_error 等：表单保留，toast 提示后端字段错误
      showApiError(error, t('toast.taskCreateFailedTitle'));
      return false;
    }
  };

  // DEV-35 块 A：AddTaskModal 双出口统一分发（一次性→实例；日常/挑战/限时→模板；编辑→PATCH）
  const handleTemplateAction = async (action: AddTaskSubmit) => {
    setTemplateActionBusy(true);
    try {
      if (action.mode === 'instance') {
        const ok = await handleAddTask(action.task);
        // task-instances 路径同样会落一条模板，仅在创建成功时让管理视图列表重拉
        if (ok) setTemplatesRefreshSignal(signal => signal + 1);
        return;
      }
      if (action.mode === 'template') {
        await api.taskTemplates.createTemplate(action.template);
        setIsAddModalOpen(false);
        toast(t('toast.templateCreatedTitle'), t('toast.templateCreatedMsg'));
      } else {
        await api.taskTemplates.updateTemplate(action.templateId, action.patch);
        setIsAddModalOpen(false);
        setEditingTemplate(null);
        toast(t('toast.templateUpdatedTitle'), t('toast.templateUpdatedMsg'));
      }
      setTemplatesRefreshSignal(signal => signal + 1);
    } catch (error) {
      // 422（timed_mode 一致性 / 触发规则按 kind 校验）：表单保留，toast 透出后端人话文案
      showApiError(error, t('toast.templateSaveFailedTitle'));
    } finally {
      setTemplateActionBusy(false);
    }
  };

  const openCreateModal = (defaultCategory: TaskTemplateCategoryIntent) => {
    setEditingTemplate(null);
    setAddModalDefaultCategory(defaultCategory);
    setIsAddModalOpen(true);
  };

  const openEditModal = (template: TaskTemplateRead) => {
    setEditingTemplate(template);
    setIsAddModalOpen(true);
  };

  const closeAddModal = () => {
    setIsAddModalOpen(false);
    setEditingTemplate(null);
  };

  // 选模板 → 生成（契约 §6B）：template 非空 = 从模板行进入；null = 从任务板进入先选模板
  const openGenerateModal = (template: TaskTemplateRead | null) => {
    // DEV-51：合并到 AddTaskModal 后不再单独打开弹窗；任务板入口直接打开新建弹窗并默认 daily
    if (template) {
      // 已选模板场景：直接生成（旧路径保留入口，但此处走 AddTaskModal 的 onSubmitGenerated）
      setAddModalDefaultCategory('daily');
      setIsAddModalOpen(true);
      return;
    }
    setAddModalDefaultCategory('daily');
    setIsAddModalOpen(true);
  };

  /** 新建模板后生成的成功回调（DEV-51） */
  const handleGeneratedFromCreate = async (result: TaskGenerateResult) => {
    const date = result.generated_for_date;
    if (result.instance_id === null) {
      toast(t('toast.taskGeneratedTitle'), t('generateTask.resultSkipped'));
    } else if (date === null) {
      toast(t('toast.taskGeneratedTitle'), t('generateTask.resultReused'));
    } else if (date <= today) {
      toast(t('toast.taskGeneratedTitle'), t('toast.taskGeneratedDeployedMsg', { date }));
    } else {
      toast(t('toast.taskGeneratedTitle'), t('toast.taskGeneratedScheduledMsg', { date }));
    }
    setInstancesRefreshSignal(signal => signal + 1);
    await loadBoard();
  };

  const startQuest = async (id: string) => {
    try {
      await api.tasks.startTask(id); // 后端扣押金；余额不足时抛 validation_error
      await Promise.all([loadBoard(), refreshUser()]);
    } catch (error) {
      // 已排期守卫（契约 §6B）：未来日期的实例孩子端列表看不到，直接按 id 接取会被 409 拒绝。
      // 正常路径撞不到，一旦触发即说明列表陈旧 → 按业务提示呈现并重拉列表。
      if (error instanceof ApiError && error.httpStatus === 409) {
        toast(t('toast.startFailedTitle'), error.message);
        await loadBoard();
        return;
      }
      showApiError(error, t('toast.startFailedTitle'));
    }
  };

  const handleAcceptAttempt = (id: string) => {
    const activeQuest = pickActiveQuest(tasks, childUser?.childId);
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

  /**
   * 提交流（DEV-33 块 E 多证据）：逐个 POST /sys/uploads(task_proof) 收集 object_key，
   * 再一次性 submit proof_object_keys（docs/10 §4 阶段③）。
   */
  const handleSubmitTask = async (files: File[], reportProgress: (percent: number) => void) => {
    if (!selectedTaskId || submitting || !files.length) return;
    setSubmitting(true);
    try {
      // DEV-30: 携带 taskId 使 object_key 含任务实例标识；串行上传让进度条单调递增
      const objectKeys: string[] = [];
      for (let i = 0; i < files.length; i++) {
        const uploaded = await api.uploads.uploadFileWithProgress(
          files[i],
          'task_proof',
          selectedTaskId,
          (filePercent) => reportProgress(Math.round(((i + filePercent / 100) / files.length) * 100)),
        );
        objectKeys.push(uploaded.object_key);
      }
      await api.tasks.submitTask(selectedTaskId, { proof_object_keys: objectKeys });
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

  /** 驳回（DEV-57）：后端退回 IN_PROGRESS 并写 review_comment，不动押金/XP（docs/13 §3.1），
   *  故只需刷新任务板，无需 refreshUser。comment 由弹窗保证非空。 */
  const handleRejectTask = async (taskId: string, comment: string) => {
    if (approving) return;
    setApproving(true);
    try {
      await api.tasks.rejectTask(taskId, { comment });
      setIsReviewModalOpen(false);
      toast(t('toast.rejectSuccessTitle'), t('toast.rejectSuccessMsg'));
      await loadBoard();
    } catch (error) {
      showApiError(error, t('toast.rejectFailedTitle'));
    } finally {
      setApproving(false);
    }
  };

  /** 记录一次特权使用（POST /scn/privileges/uses，返回使用记录）；成功后余额/流水一律 refetch，禁止本地加减 */
  const handleRecordUsage = async (privilege: PrivilegeRead) => {
    try {
      const record = await api.coins.usePrivilege({
        privilege_template_id: privilege.id,
        child_id: childUser?.childId ?? undefined,
      });
      toast(t('toast.usageRecordedTitle'), t('toast.usageRecordedMsg', { title: record.privilege_title }), 3000);
      await Promise.all([loadPrivileges(), refreshUser()]);
    } catch (error) {
      // 403（孩子越权）/ 422（未解锁等）：后端人话文案直接透出（docs/10 §2.4）
      showApiError(error, t('toast.privilegeUseFailedTitle'));
    }
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
  const activeQuest = pickActiveQuest(tasks, childUser?.childId);
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
                privilegeTemplates={privilegeTemplates}
                unlockedTemplateIds={privilegeUnlocks.map(u => u.privilege_template_id)}
                privilegesLoading={privilegesLoading}
                onAcceptAttempt={handleAcceptAttempt}
                onSubmit={(id) => { setSelectedTaskId(id); setIsSubmitModalOpen(true); }}
                onAbandonCurrent={handleAbandonCurrent}
             />
          </div>
        ) : (
          <div className="bg-slate-100 min-h-full p-4 md:p-6 lg:p-8">
             <div className="max-w-7xl mx-auto">
                 {/* 父母端 Tab：任务板 / 任务模板（DEV-35，Miss.D「父母端独立 Tab」） */}
                 <div className="flex gap-1 mb-4" role="tablist" aria-label={t('parent.management')}>
                    {([['board', 'parent.tabBoard'], ['templates', 'parent.tabTemplates']] as const).map(([key, labelKey]) => (
                      <button
                        key={key}
                        role="tab"
                        aria-selected={parentView === key}
                        onClick={() => setParentView(key)}
                        className={`px-4 py-2 rounded-lg text-sm font-bold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600 ${
                          parentView === key
                            ? 'bg-white text-slate-800 shadow-sm border border-slate-200'
                            : 'text-slate-500 hover:text-slate-700'
                        }`}
                      >
                        {t(labelKey)}
                      </button>
                    ))}
                 </div>
                 {showSeasonHistory ? (
                     <SeasonHistory
                        onBack={() => setShowSeasonHistory(false)}
                     />
                 ) : parentView === 'templates' ? (
                     <TaskTemplateManager
                        canHardDelete={Boolean(family && user && family.family.owner_id === user.id)}
                        onToast={showToast}
                        onOpenCreate={() => openCreateModal('daily')}
                        onEditTemplate={openEditModal}
                        onOpenGenerate={(template) => openGenerateModal(template)}
                        refreshSignal={templatesRefreshSignal}
                        instancesRefreshSignal={instancesRefreshSignal}
                        onInstancesChanged={loadBoard}
                     />
                 ) : (
                     <ParentDashboard
                        childUser={childUser}
                        tasks={tasks}
                        activeQuest={activeQuest}
                        availableTasks={availableTasks}
                        pendingTasks={pendingTasks}
                        privilegeUses={privilegeUses}
                        privilegeTemplates={privilegeTemplates}
                        unlockedTemplateIds={privilegeUnlocks.map(u => u.privilege_template_id)}
                        privilegesLoading={privilegesLoading}
                        activeSeason={activeSeason}
                        currentTheme={currentSeasonTheme}
                        seasonError={seasonError}
                        onRetrySeasons={loadSeasons}
                        onOpenSeasonConfig={() => setIsSeasonConfigModalOpen(true)}
                        onViewHistory={() => setShowSeasonHistory(true)}
                        onOpenAddModal={() => openCreateModal('once')}
                        onOpenGenerate={() => openGenerateModal(null)}
                        onTuneTask={(id) => setTuningTask(tasks.find(item => item.id === id) ?? null)}
                        today={today}
                        onRecordUsage={handleRecordUsage}
                        onReviewTask={(id) => { setSelectedTaskId(id); setIsReviewModalOpen(true); }}
                        onDeleteTask={handleDeleteTask}
                        onOpenTimeConfig={() => setIsTimeConfigModalOpen(true)}
                        onViewCoinLogs={() => setIsCoinLogsOpen(true)}
                        onOpenPrivilegeConfig={() => setIsPrivilegeConfigOpen(true)}
                     />
                 )}
             </div>
          </div>
        )}
      </main>

      {/* --- MODALS --- */}
      <AddTaskModal
        isOpen={isAddModalOpen}
        onClose={closeAddModal}
        onSubmit={handleTemplateAction}
        seasonId={activeSeason?.id ?? ''}
        childLevel={childUser?.level ?? 1}
        submitting={templateActionBusy}
        editingTemplate={editingTemplate}
        defaultCategory={addModalDefaultCategory}
        onSubmitGenerated={handleGeneratedFromCreate}
        onToast={showToast}
        today={today}
      />

      {/* 契约 §6B：生成后微调（PATCH /scn/task-instances/{id}） */}
      <TuneTaskModal
        isOpen={tuningTask !== null}
        onClose={() => setTuningTask(null)}
        task={tuningTask}
        onSaved={loadBoard}
        onToast={showToast}
      />

      <SubmitTaskModal
        key={`submit-task-modal-${isSubmitModalOpen ? "open" : "closed"}`}
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
        onReject={handleRejectTask}
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

      <PrivilegeConfigModal
        isOpen={isPrivilegeConfigOpen}
        onClose={() => setIsPrivilegeConfigOpen(false)}
        templates={privilegeTemplates}
        onSaved={(next) => setPrivilegeTemplates(next)}
        onToast={showToast}
      />
    </div>
  );
};

export default App;
