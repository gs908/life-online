/**
 * /scn/task-instances（契约 §6）—— 替换阶段③（docs/10 §4）
 *
 * 注意：接取扣押金、审核发 XP/退扣币、放弃罚币全部由后端完成；
 * 前端 App.tsx 中的本地状态机（startQuest/handleApproveTask/handleAbandonQuest）
 * 在本阶段接入时整体删除，余额与任务状态以响应/重新拉取为准。
 */
import { request } from '../http';
import type {
  PageResult,
  TaskApproveRequest,
  TaskCreate,
  TaskDepositPreviewRequest,
  TaskDepositPreviewResponse,
  TaskInstancePatch,
  TaskListQuery,
  TaskProofRead,
  TaskRead,
  TaskRejectRequest,
  TaskSubmitRequest,
} from '../types';

export const listTasks = (query: TaskListQuery = {}) =>
  request<PageResult<TaskRead>>('/scn/task-instances', { query });

export const getTask = (taskId: string) =>
  request<TaskRead>(`/scn/task-instances/${encodeURIComponent(taskId)}`);

/** 创建 = 建模板 + 初始实例（无独立模板接口，docs/09 A6） */
export const createTask = (data: TaskCreate) =>
  request<TaskRead>('/scn/task-instances', { method: 'POST', body: data });

/** 微调实例（契约 §6B）：难度 / 押金 / 经验值三个快照字段。
 *
 * - **只放用户真的改过的字段**；没动过的不放进 body（未提供 = 保持不变）。
 * - **绝不传 `null`** —— 三个字段都是快照，`null` 一律 422（不存在"清除覆盖"）。
 * - 「恢复默认」= 先取模板当前值，再把该数值作为显式数字提交。
 * - 只允许改这三个字段；实例 `season_id` 不可改。 */
export const patchTask = (taskId: string, data: TaskInstancePatch) =>
  request<TaskRead>(`/scn/task-instances/${encodeURIComponent(taskId)}`, {
    method: 'PATCH',
    body: data,
  });

/** 管理端表单实时预览押金（父母权限）：押金 = 耗时驱动，难度不影响押金（DEV-34 块 C） */
export const previewDeposit = (data: TaskDepositPreviewRequest) =>
  request<TaskDepositPreviewResponse>('/scn/task-templates/preview-deposit', {
    method: 'POST',
    body: data,
  });

export const deleteTask = (taskId: string) =>
  request<null>(`/scn/task-instances/${encodeURIComponent(taskId)}`, { method: 'DELETE' });

/** 孩子接取（后端扣时间币押金；重复接取返回 409 conflict） */
export const startTask = (taskId: string) =>
  request<TaskRead>(`/scn/task-instances/${encodeURIComponent(taskId)}/start`, { method: 'POST' });

/** 孩子提交证明（DEV-33 块 E 多证据）。object_keys 来自 POST /sys/uploads(purpose=task_proof)，不是 base64 */
export const submitTask = (taskId: string, data: TaskSubmitRequest) =>
  request<TaskRead>(`/scn/task-instances/${encodeURIComponent(taskId)}/submit`, {
    method: 'POST',
    body: data,
  });

/** 任务证据列表（DEV-33 块 E，docs/07 A7.2）：未软删、按提交顺序；TaskRead.proofs 的独立刷新入口 */
export const listTaskProofs = (taskId: string) =>
  request<TaskProofRead[]>(`/scn/task-instances/${encodeURIComponent(taskId)}/proofs`);

/** 父母审核（后端发 XP、退/扣币；rating 1-5 必填） */
export const approveTask = (taskId: string, data: TaskApproveRequest) =>
  request<TaskRead>(`/scn/task-instances/${encodeURIComponent(taskId)}/approve`, {
    method: 'POST',
    body: data,
  });

/** 父母驳回（DEV-57）：后端切回 IN_PROGRESS、写 review_comment、清 submitted_at；COOP 参与者回 JOINED。
 *  不动押金/XP（docs/13 §3.1）。 */
export const rejectTask = (taskId: string, data: TaskRejectRequest) =>
  request<TaskRead>(`/scn/task-instances/${encodeURIComponent(taskId)}/reject`, {
    method: 'POST',
    body: data,
  });

/** 孩子放弃（后端罚币） */
export const abandonTask = (taskId: string) =>
  request<TaskRead>(`/scn/task-instances/${encodeURIComponent(taskId)}/abandon`, { method: 'POST' });
