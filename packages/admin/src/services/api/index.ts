/**
 * 端无关 API Client 统一出口（docs/10-前端API接入计划.md）
 *
 * 使用约定：
 * - 组件/hook 只 import 本文件，不直接 import http.ts 或各模块内部。
 * - 调用方向：组件/hook → services/api → 后端 /api/v1。
 * - 错误统一为 ApiError / NetworkError / NeedInviteCodeError，UI 层按 error_code 分支（docs/10 §2.4）。
 * - 本目录为纯 TS、零 React 依赖；第二个端（孩子端/系统管理后台）立项时
 *   原样提升为 packages/api-client 独立包（token 存储经 StorageAdapter 注入）。
 */
export * from './types';
export { ApiError, NetworkError, NeedInviteCodeError } from './errors';
export type { ApiErrorCode } from './errors';
export {
  clearTokens,
  configureTokenStorage,
  getAccessToken,
  onForcedLogout,
  saveTokenPair,
} from './token';
export type { StorageAdapter } from './token';

import * as authApi from './modules/auth';
import * as aiApi from './modules/ai';
import * as coinsApi from './modules/coins';
import * as seasonsApi from './modules/seasons';
import * as tasksApi from './modules/tasks';
import * as uploadsApi from './modules/uploads';

export const api = {
  auth: authApi,
  seasons: seasonsApi,
  tasks: tasksApi,
  coins: coinsApi,
  uploads: uploadsApi,
  ai: aiApi,
};
