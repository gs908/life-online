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
  TaskListQuery,
  TaskRead,
  TaskSubmitRequest,
} from '../types';

export const listTasks = (query: TaskListQuery = {}) =>
  request<PageResult<TaskRead>>('/scn/task-instances', { query });

export const getTask = (taskId: string) =>
  request<TaskRead>(`/scn/task-instances/${encodeURIComponent(taskId)}`);

/** 创建 = 建模板 + 初始实例（无独立模板接口，docs/09 A6） */
export const createTask = (data: TaskCreate) =>
  request<TaskRead>('/scn/task-instances', { method: 'POST', body: data });

export const deleteTask = (taskId: string) =>
  request<null>(`/scn/task-instances/${encodeURIComponent(taskId)}`, { method: 'DELETE' });

/** 孩子接取（后端扣时间币押金；重复接取返回 409 conflict） */
export const startTask = (taskId: string) =>
  request<TaskRead>(`/scn/task-instances/${encodeURIComponent(taskId)}/start`, { method: 'POST' });

/** 孩子提交证明。proof_object_key 来自 POST /sys/uploads(purpose=task_proof)，不是 base64 */
export const submitTask = (taskId: string, data: TaskSubmitRequest) =>
  request<TaskRead>(`/scn/task-instances/${encodeURIComponent(taskId)}/submit`, {
    method: 'POST',
    body: data,
  });

/** 父母审核（后端发 XP、退/扣币；rating 1-5 必填） */
export const approveTask = (taskId: string, data: TaskApproveRequest) =>
  request<TaskRead>(`/scn/task-instances/${encodeURIComponent(taskId)}/approve`, {
    method: 'POST',
    body: data,
  });

/** 孩子放弃（后端罚币） */
export const abandonTask = (taskId: string) =>
  request<TaskRead>(`/scn/task-instances/${encodeURIComponent(taskId)}/abandon`, { method: 'POST' });
