/// <reference types="vite/client" />
/**
 * 请求核心（docs/10 §2.2、§2.3）
 *
 * 职责：BASE_URL 前缀、Bearer 注入、{code:0} 解包、ApiError 抛出、
 * 401 单飞刷新（single-flight）→ 重放原请求一次 → 仍失败则广播登出。
 * 不做 401 以外的自动重试。
 */
import { ApiError, NeedInviteCodeError, NetworkError } from './errors';
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  saveTokenPair,
  setRefreshExecutor,
} from './token';
import type { ApiResponse, RefreshRequest, TokenPair } from './types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  /** 查询参数（接口 DTO 直接传入）；undefined/null/空串会被丢弃，其余值 String() 序列化 */
  query?: object;
  body?: unknown;
  /** multipart 上传（/sys/uploads）；body 必须是 FormData */
  formData?: FormData;
  /** 401 刷新重放内部使用，业务代码不要传 */
  _isRetry?: boolean;
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = `${BASE_URL}${path}`;
  if (!query) return url;
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') {
      qs.set(key, String(value));
    }
  }
  const s = qs.toString();
  return s ? `${url}?${s}` : url;
}

async function parseEnvelope<T>(response: Response): Promise<ApiResponse<T>> {
  let payload: ApiResponse<T>;
  try {
    payload = (await response.json()) as ApiResponse<T>;
  } catch {
    throw new NetworkError(response);
  }
  // 契约 §0.2：成功 code === 0；失败 code === 1（或其他非 0），data 里带 error_code
  if (payload.code !== 0) {
    const errorCode =
      (payload.data as { error_code?: string } | null)?.error_code ?? 'app_error';
    if (errorCode === 'need_invite_code') throw new NeedInviteCodeError(response.status);
    throw new ApiError(errorCode, payload.msg || '请求失败', response.status, payload.data);
  }
  return payload;
}

async function rawRequest<T>(path: string, options: RequestOptions): Promise<ApiResponse<T>> {
  const headers: Record<string, string> = {};
  const token = getAccessToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers,
      body: options.formData ?? (options.body !== undefined ? JSON.stringify(options.body) : undefined),
    });
  } catch (cause) {
    throw new NetworkError(cause);
  }

  if (response.status === 401 && !options._isRetry) {
    await refreshTokens(); // 失败会抛 ApiError('unauthorized') 并广播登出
    return rawRequest<T>(path, { ...options, _isRetry: true });
  }

  return parseEnvelope<T>(response);
}

/** 业务入口：直接返回 data（已解包），错误一律抛 ApiError/NetworkError */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const envelope = await rawRequest<T>(path, options);
  return envelope.data;
}

// ---- 401 单飞刷新 ----

let refreshInFlight: Promise<void> | null = null;

async function doRefresh(): Promise<void> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) throw new ApiError('unauthorized', '未登录', 401);

  const body: RefreshRequest = { refresh_token: refreshToken };
  let response: Response;
  try {
    // 不带 Authorization、不走 401 重放（_isRetry）
    response = await fetch(buildUrl('/sys/auth/refresh'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (cause) {
    throw new NetworkError(cause);
  }

  const envelope = await parseEnvelope<TokenPair>(response);
  saveTokenPair(envelope.data);
}

/** 并发 401 只触发一次刷新；刷新失败清 token 并广播登出 */
export function refreshTokens(): Promise<void> {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().catch((error) => {
      clearTokens('refresh_failed');
      throw error instanceof ApiError ? error : new ApiError('unauthorized', '登录已过期', 401);
    }).finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

setRefreshExecutor(refreshTokens);

/** multipart 上传（/sys/uploads）：不设 Content-Type，交给浏览器补 boundary */
export async function upload<T>(path: string, formData: FormData): Promise<T> {
  return request<T>(path, { method: 'POST', formData });
}
