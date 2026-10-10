/**
 * /scn/time-coin-logs、/scn/time-configs（契约 §8、§11）—— 替换阶段④（docs/10 §4）
 * 特权 /scn/privileges、/scn/privilege-uses（契约 §9、§10）随本阶段接入。
 */
import { request } from '../http';
import type {
  CoinAdjustRequest,
  CoinLogQuery,
  CoinTransactionRead,
  PageResult,
  PrivilegeRead,
  RedemptionCreate,
  RedemptionRead,
  TimeConfigRead,
  TimeConfigUpdate,
  UserPrivilegeRead,
} from '../types';

// ---- 时间币流水 ----

export const listCoinLogs = (query: CoinLogQuery = {}) =>
  request<PageResult<CoinTransactionRead>>('/scn/time-coin-logs', { query });

/** 人工调整（父母）：amount 正加负减 */
export const adjustCoins = (data: CoinAdjustRequest) =>
  request<CoinTransactionRead>('/scn/time-coin-logs/adjust', { method: 'POST', body: data });

// ---- 时间币配置 ----

export const getMyTimeConfig = () => request<TimeConfigRead>('/scn/time-configs/me');

/** PUT 对 exceptions 是整体替换：保存时必须提交完整数组（docs/09 C3） */
export const updateMyTimeConfig = (data: TimeConfigUpdate) =>
  request<TimeConfigRead>('/scn/time-configs/me', { method: 'PUT', body: data });

// ---- 特权 ----

/** 特权模板树（系统+本家庭，后端已按 level_required 排序）；特权树按 level_required 分组渲染 */
export const listPrivilegeTemplates = () => request<PrivilegeRead[]>('/scn/privileges/templates');

export const listPrivilegeUnlocks = (childId?: string) =>
  request<UserPrivilegeRead[]>('/scn/privileges/unlocks', { query: { child_id: childId } });

/** 使用一次已解锁特权，返回使用记录 */
export const usePrivilege = (data: RedemptionCreate) =>
  request<RedemptionRead>('/scn/privileges/uses', { method: 'POST', body: data });

// ---- 特权使用记录 ----

export const listPrivilegeUses = (query: { page?: number; page_size?: number; child_id?: string } = {}) =>
  request<PageResult<RedemptionRead>>('/scn/privilege-uses', { query });

/** 手工记录一次使用（自由文本特权） */
export const createPrivilegeUse = (data: RedemptionCreate) =>
  request<RedemptionRead>('/scn/privilege-uses', { method: 'POST', body: data });
