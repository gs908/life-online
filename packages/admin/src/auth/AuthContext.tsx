/**
 * 登录态与家庭上下文（docs/10 §4 阶段①）
 *
 * 职责：
 * - 启动引导：本地存有 token 时经 /sys/auth/me + /sys/accounts/me + /sys/families/me 恢复会话
 *   （冒险者的 GET /sys/accounts/me 同时触发服务端每日重置，替代原前端本地比对逻辑）。
 * - dev-login 登录（开发期 H5 通道，docs/08 §2）。
 * - 401 单飞刷新失败 → token 层广播 onForcedLogout → 回登录页（广播源在 services/api/token.ts）。
 * - 登出：尽力而为调后端 + 清 token。
 */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { api, clearTokens, getAccessToken, NetworkError, onForcedLogout, saveTokenPair } from '../services/api';
import type { FamilyMembersRead, UserRead, UserRole } from '../services/api';

export type AuthStatus = 'loading' | 'anonymous' | 'authenticated';

interface AuthContextValue {
  status: AuthStatus;
  /** 当前登录用户（冒险者数据取自 GET /sys/accounts/me，已含服务端每日重置结果） */
  user: UserRead | null;
  /** 家庭上下文（含 guild_masters / adventurers 成员列表），登录后加载 */
  family: FamilyMembersRead | null;
  login: (role: UserRole, name?: string) => Promise<void>;
  logout: () => Promise<void>;
  /** 变更类操作（时间币等，阶段④起）后手动刷新当前用户数据 */
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth 必须在 <AuthProvider> 内使用');
  return ctx;
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [user, setUser] = useState<UserRead | null>(null);
  const [family, setFamily] = useState<FamilyMembersRead | null>(null);
  // StrictMode 双挂载下避免重复引导请求
  const bootstrapped = useRef(false);

  const loadSession = useCallback(async (): Promise<UserRead> => {
    const identity = await api.auth.getMe();
    // GET /sys/accounts/me 对冒险者触发服务端每日重置，返回重置后的最新数据
    const [account, familyResult] = await Promise.all([
      api.auth.getMyAccount().catch(() => null),
      api.auth.getMyFamily().catch(() => null),
    ]);
    const current = identity.role === 'ADVENTURER' && account ? account : identity;
    setUser(current);
    setFamily(familyResult);
    return current;
  }, []);

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;

    if (!getAccessToken()) {
      setStatus('anonymous');
      return;
    }

    loadSession()
      .then(() => setStatus('authenticated'))
      .catch((error) => {
        // 网络故障不清 token：下次刷新页面仍可恢复会话；其余（token 失效且刷新失败已由
        // http.ts 清掉；权限异常等）按未登录处理
        if (!(error instanceof NetworkError)) {
          clearTokens('manual');
        }
        setUser(null);
        setFamily(null);
        setStatus('anonymous');
      });
  }, [loadSession]);

  // token 层广播的强制登出（401 刷新失败）→ 回登录页
  useEffect(() => {
    return onForcedLogout(() => {
      setUser(null);
      setFamily(null);
      setStatus('anonymous');
    });
  }, []);

  const login = useCallback(
    async (role: UserRole, name?: string) => {
      setStatus('loading');
      try {
        const pair = await api.auth.devLogin({ role, name: name || undefined });
        saveTokenPair(pair);
        await loadSession();
        setStatus('authenticated');
      } catch (error) {
        setStatus('anonymous');
        throw error; // 登录页按 error_code 展示（DEV_LOGIN_ENABLED=false → permission_denied）
      }
    },
    [loadSession],
  );

  const logout = useCallback(async () => {
    try {
      await api.auth.logout();
    } catch {
      // 后端登出仅记日志，失败不阻塞本地清 token
    }
    clearTokens('manual'); // 触发 onForcedLogout → 状态归 anonymous
  }, []);

  const refreshUser = useCallback(async () => {
    await loadSession();
  }, [loadSession]);

  const value = useMemo(
    () => ({ status, user, family, login, logout, refreshUser }),
    [status, user, family, login, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
