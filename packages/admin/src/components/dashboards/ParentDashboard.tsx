import React from 'react';
import { useTranslation } from 'react-i18next';
import { User, UserRole, SeasonTheme } from '../../types';
import type { TaskRead, SeasonRead, PrivilegeRead, RedemptionRead } from '../../services/api';
import StatsBoard from '../StatsBoard';
import PrivilegeTree from '../PrivilegeTree';
import QuestCard from '../QuestCard';
import { isScheduled } from '../../utils/date';
import { History, Plus, Sparkles, Clock, Coins, Palette, Archive, Zap, Gift } from 'lucide-react';

interface ParentDashboardProps {
  childUser: User;
  tasks: TaskRead[];
  activeQuest: TaskRead | undefined;
  availableTasks: TaskRead[];
  pendingTasks: TaskRead[];
  /** 特权使用记录（GET /scn/privilege-uses，阶段④-b 后端化，替代 redemptionHistory Mock） */
  privilegeUses: RedemptionRead[];
  privilegeTemplates: PrivilegeRead[];
  unlockedTemplateIds: string[];
  privilegesLoading: boolean;
  /** 当前激活赛季；null = 家庭尚未创建/激活赛季（引导创建） */
  activeSeason: SeasonRead | null;
  currentTheme: SeasonTheme;
  seasonError: string | null;
  onRetrySeasons: () => void;
  onOpenSeasonConfig: () => void;
  onViewHistory: () => void;
  /** 任务板工具栏唯一入口：打开「创建新任务」弹窗（顶部选模板分两支） */
  onOpenAddModal: () => void;
  /** 微调已生成实例的难度/押金/经验值 */
  onTuneTask: (id: string) => void;
  /** 家庭本地时区的今天，YYYY-MM-DD：用于区分「已投放」与「已排期」 */
  today: string;
  onRecordUsage: (privilege: PrivilegeRead) => void;
  onReviewTask: (id: string) => void;
  onDeleteTask: (id: string) => void;
  onOpenTimeConfig: () => void;
  onViewCoinLogs: () => void;
  /** 打开权益设置弹窗 */
  onOpenPrivilegeConfig: () => void;
}

const ParentDashboard: React.FC<ParentDashboardProps> = ({
  childUser,
  tasks,
  activeQuest,
  availableTasks,
  pendingTasks,
  privilegeUses,
  privilegeTemplates,
  unlockedTemplateIds,
  privilegesLoading,
  activeSeason,
  currentTheme,
  seasonError,
  onRetrySeasons,
  onOpenSeasonConfig,
  onViewHistory,
  onOpenAddModal,
  onTuneTask,
  today,
  onRecordUsage,
  onReviewTask,
  onDeleteTask,
  onOpenTimeConfig,
  onViewCoinLogs,
  onOpenPrivilegeConfig
}) => {
  const { t } = useTranslation();

  // 已排期（generated_for_date > 今天）与已投放分开呈现：前者孩子端看不到、也不能接取，
  // 混在「可接取」里会让家长误判成"孩子没做"（契约 §6B 防误判）。
  const scheduledTasks = availableTasks.filter(task => isScheduled(task, today));
  const deployedTasks = availableTasks.filter(task => !isScheduled(task, today));

  return (
    <div className="space-y-6">
      {/* Management Header */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800">{t('parent.management')}</h2>
          <div className="flex items-center gap-2 mt-1">
             {activeSeason ? (
               <>
                 <span className="text-xs font-bold bg-blue-100 text-blue-700 px-2 py-0.5 rounded">{activeSeason.name}</span>
                 {activeSeason.narrative_context && (
                   <span className="text-xs text-slate-400 truncate max-w-[200px]">"{activeSeason.narrative_context}"</span>
                 )}
               </>
             ) : (
               <span className="text-xs font-bold bg-amber-100 text-amber-700 px-2 py-0.5 rounded">{t('parent.noActiveSeason')}</span>
             )}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
             onClick={onOpenTimeConfig}
             className="bg-slate-50 text-slate-700 border border-slate-200 px-3 py-2 rounded-lg text-sm font-bold flex items-center gap-2 hover:bg-slate-100 transition-colors"
          >
             <Clock size={16} /> {t('parent.coins')}
          </button>
          <button
             onClick={onOpenPrivilegeConfig}
             className="bg-slate-50 text-slate-700 border border-slate-200 px-3 py-2 rounded-lg text-sm font-bold flex items-center gap-2 hover:bg-slate-100 transition-colors"
          >
             <Gift size={16} /> {t('parent.privilegeConfig')}
          </button>
          <button
             onClick={onViewCoinLogs}
             className="bg-slate-50 text-slate-700 border border-slate-200 px-3 py-2 rounded-lg text-sm font-bold flex items-center gap-2 hover:bg-slate-100 transition-colors"
          >
             <Coins size={16} /> {t('parent.coinLogs')}
          </button>
          <button
             onClick={onOpenSeasonConfig}
             className="bg-slate-50 text-slate-700 border border-slate-200 px-3 py-2 rounded-lg text-sm font-bold flex items-center gap-2 hover:bg-slate-100 transition-colors"
          >
             <Palette size={16} /> {t('parent.theme')}
          </button>
          <button
             onClick={onViewHistory}
             className="bg-slate-50 text-slate-700 border border-slate-200 px-3 py-2 rounded-lg text-sm font-bold flex items-center gap-2 hover:bg-slate-100 transition-colors"
          >
             <Archive size={16} /> {t('parent.history')}
          </button>
          <button
            onClick={onOpenAddModal}
            className="bg-slate-900 text-white px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2 hover:bg-slate-800 transition-colors shadow-lg shadow-slate-900/20"
          >
            <Plus size={16} /> {t('createTask.entry')}
          </button>
        </div>
      </div>

      {/* 赛季加载失败 / 无激活赛季引导（阶段②） */}
      {seasonError ? (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-center justify-between gap-4">
          <p className="text-sm font-bold text-red-700">{t('parent.seasonLoadFailed', { msg: seasonError })}</p>
          <button onClick={onRetrySeasons} className="bg-red-600 text-white text-sm font-bold px-4 py-2 rounded-lg hover:bg-red-700 shrink-0">
            {t('parent.retry')}
          </button>
        </div>
      ) : !activeSeason ? (
        <button
          onClick={onOpenSeasonConfig}
          className="w-full bg-gradient-to-r from-amber-50 to-orange-50 border-2 border-dashed border-amber-300 rounded-xl p-5 flex items-center justify-between gap-4 hover:border-amber-400 transition-colors group"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-amber-100 text-amber-600 flex items-center justify-center text-xl">{currentTheme.icon}</div>
            <div className="text-left">
              <p className="font-bold text-slate-800 text-sm">{t('parent.noActiveSeasonTitle')}</p>
              <p className="text-xs text-slate-500">{t('parent.noActiveSeasonHint')}</p>
            </div>
          </div>
          <span className="bg-amber-500 text-white text-sm font-bold px-4 py-2 rounded-lg flex items-center gap-2 group-hover:bg-amber-600 shrink-0">
            <Zap size={16} /> {t('parent.createSeasonNow')}
          </span>
        </button>
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* LEFT COLUMN: STATS & PRIVILEGES */}
        <div className="lg:col-span-1 space-y-6">
          <StatsBoard tasks={tasks} />

          <div className="bg-white p-4 rounded-xl shadow-md border border-slate-200">
            <h3 className="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2">
              <History className="text-purple-500" />
              {t('parent.consumptionHistory')}
            </h3>
            {privilegeUses.length === 0 ? (
              <p className="text-sm text-slate-400 italic text-center py-4">{t('parent.noPrivilegesUsed')}</p>
            ) : (
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {privilegeUses.map(r => (
                  <div key={r.id} className="text-xs bg-slate-50 p-2 rounded flex justify-between items-center">
                    <span className="font-bold text-slate-700">{r.privilege_title}</span>
                    <span className="text-slate-400">{new Date(r.used_at).toLocaleDateString()}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <PrivilegeTree
            templates={privilegeTemplates}
            unlockedTemplateIds={unlockedTemplateIds}
            currentLevel={childUser.level}
            loading={privilegesLoading}
            isAdmin={true}
            onRecordUsage={onRecordUsage}
            onOpenConfig={onOpenPrivilegeConfig}
          />
        </div>

        {/* RIGHT COLUMN: TASK MANAGEMENT */}
        <div className="lg:col-span-2">
          {/* Active Quest Monitoring */}
          {activeQuest && (
            <div className="mb-6">
              <h3 className="text-lg font-bold text-blue-800 mb-2 flex items-center gap-2">
                <Sparkles size={18} /> {t('parent.currentlyAdventuring')}
              </h3>
              <QuestCard
                task={activeQuest}
                role={UserRole.PARENT}
                isActive={true}
                onAccept={() => { }}
                onSubmit={() => { }}
                onApprove={() => { }}
              />
            </div>
          )}

          <h3 className="text-lg font-bold text-slate-700 mb-4">{t('parent.pendingReview')}</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
            {pendingTasks.map(task => (
              <QuestCard
                key={task.id}
                task={task}
                role={UserRole.PARENT}
                onAccept={() => { }}
                onSubmit={() => { }}
                onApprove={onReviewTask}
                onDelete={onDeleteTask}
              />
            ))}
            {pendingTasks.length === 0 && (
              <p className="text-slate-400 text-sm col-span-2 bg-slate-50 p-4 rounded border border-dashed text-center">{t('parent.noPendingReview')}</p>
            )}
          </div>

          <h3 className="text-lg font-bold text-slate-700 mb-4">{t('parent.availableQuestsBoard')}</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {deployedTasks.map(task => (
              <QuestCard
                key={task.id}
                task={task}
                role={UserRole.PARENT}
                onAccept={() => { }}
                onSubmit={() => { }}
                onApprove={() => { }}
                onDelete={onDeleteTask}
                onTune={onTuneTask}
              />
            ))}
            {deployedTasks.length === 0 && (
              <p className="text-slate-400 text-sm col-span-2 bg-slate-50 p-4 rounded border border-dashed text-center">
                {t('parent.noAvailableQuests')}
              </p>
            )}
          </div>

          {/* 已排期（未来日期，孩子端不可见也不可接取）：单列一组 + 角标，防"误判为生成失败" */}
          {scheduledTasks.length > 0 && (
            <>
              <h3 className="text-lg font-bold text-slate-700 mb-3 mt-8">
                {t('parent.scheduledQuests')}{' '}
                <span className="text-xs font-normal text-slate-400">{t('parent.scheduledQuestsHint')}</span>
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {scheduledTasks.map(task => (
                  <QuestCard
                    key={task.id}
                    task={task}
                    role={UserRole.PARENT}
                    scheduled
                    onAccept={() => { }}
                    onSubmit={() => { }}
                    onApprove={() => { }}
                    onDelete={onDeleteTask}
                    onTune={onTuneTask}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default ParentDashboard;
