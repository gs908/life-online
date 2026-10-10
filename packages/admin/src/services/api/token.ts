/**
 * token 存取与刷新（docs/10 §2.3）
 *
 * 端无关设计：核心层不 import 任何平台 API，存储经 StorageAdapter 注入。
 * - H5：localStorage
 * - 小程序：wx.getStorageSync/setStorageSync 适配
 * 提升为 packages/api-client 时，本文件随包迁移，无需改动。
 */
import type { TokenPair } from './types';

export interface StorageAdapter {
  get(key: string): string | null;
  set(key: string, value: string): void;
  remove(key: string): void;
}

/** H5 默认实现；小程序端注入 wx storage 适配 */
const localStorageAdapter: StorageAdapter = {
  get: (key) => {
    try {
      return globalThis.localStorage?.getItem(key) ?? null;
    } catch {
      return null; // 隐私模式等场景
    }
  },
  set: (key, value) => {
    try {
      globalThis.localStorage?.setItem(key, value);
    } catch {
      /* ignore */
    }
  },
  remove: (key) => {
    try {
      globalThis.localStorage?.removeItem(key);
    } catch {
      /* ignore */
    }
  },
};

const ACCESS_KEY = 'lg.access_token';
const REFRESH_KEY = 'lg.refresh_token';

let storage: StorageAdapter = localStorageAdapter;
let accessToken: string | null = null;
let refreshTimer: ReturnType<typeof setTimeout> | null = null;

/** 登出/刷新彻底失败时广播，由应用层（AuthProvider）监听跳登录页 */
type LogoutListener = (reason: 'manual' | 'refresh_failed') => void;
const logoutListeners = new Set<LogoutListener>();

export function configureTokenStorage(adapter: StorageAdapter): void {
  storage = adapter;
}

export function onForcedLogout(listener: LogoutListener): () => void {
  logoutListeners.add(listener);
  return () => logoutListeners.delete(listener);
}

export function getAccessToken(): string | null {
  if (accessToken === null) {
    accessToken = storage.get(ACCESS_KEY);
  }
  return accessToken;
}

export function getRefreshToken(): string | null {
  return storage.get(REFRESH_KEY);
}

export function saveTokenPair(pair: TokenPair): void {
  accessToken = pair.access_token;
  storage.set(ACCESS_KEY, pair.access_token);
  storage.set(REFRESH_KEY, pair.refresh_token);
  scheduleProactiveRefresh(pair.access_expires_in);
}

export function clearTokens(reason: 'manual' | 'refresh_failed' = 'manual'): void {
  accessToken = null;
  storage.remove(ACCESS_KEY);
  storage.remove(REFRESH_KEY);
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
  logoutListeners.forEach((fn) => fn(reason));
}

/** 提前 60s 主动刷新，避免请求中途过期 */
function scheduleProactiveRefresh(accessExpiresIn: number): void {
  if (refreshTimer) clearTimeout(refreshTimer);
  const delayMs = Math.max((accessExpiresIn - 60) * 1000, 5_000);
  refreshTimer = setTimeout(() => {
    // 循环依赖避免：refreshTokens 由 http.ts 注入（见 setRefreshExecutor）
    refreshExecutor?.().catch(() => {
      /* 失败由 http.ts 的 401 兜底处理 */
    });
  }, delayMs);
}

let refreshExecutor: (() => Promise<void>) | null = null;

/** http.ts 注入实际刷新执行器（含 single-flight），避免模块循环依赖 */
export function setRefreshExecutor(executor: () => Promise<void>): void {
  refreshExecutor = executor;
}
