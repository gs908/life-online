/**
 * /sys/auth、/sys/accounts、/sys/families（契约 §2–§4）—— 替换阶段①（docs/10 §4）
 */
import { request } from '../http';
import type {
  AdventurerCreate,
  FamilyJoinRequest,
  FamilyMembersRead,
  FamilyRead,
  RefreshRequest,
  TokenPair,
  UserRead,
  UserUpdate,
  WechatJscodeRequest,
} from '../types';

// ---- 认证 /sys/auth ----

/** 小程序 code 换 token。openid 无账号时抛 NeedInviteCodeError → 引导邀请码加入 */
export const wechatLogin = (data: WechatJscodeRequest) =>
  request<TokenPair>('/sys/auth/wechat/jscode', { method: 'POST', body: data });

export const refreshTokenPair = (data: RefreshRequest) =>
  request<TokenPair>('/sys/auth/refresh', { method: 'POST', body: data });

/** 登出（后端仅记日志，客户端清 token） */
export const logout = () => request<null>('/sys/auth/logout', { method: 'POST' });

export const getMe = () => request<UserRead>('/sys/auth/me');

// ---- 账号 /sys/accounts ----

/** 冒险者触发服务端每日重置（津贴发放、abandon 清零）——替代前端本地重置逻辑（docs/09 P5） */
export const getMyAccount = () => request<UserRead>('/sys/accounts/me');

export const updateMyAccount = (data: UserUpdate) =>
  request<UserRead>('/sys/accounts/me', { method: 'PATCH', body: data });

export const createAdventurer = (data: AdventurerCreate) =>
  request<UserRead>('/sys/accounts/adventurers', { method: 'POST', body: data });

// ---- 家庭 /sys/families ----

export const createFamily = (name: string) =>
  request<FamilyRead>('/sys/families', { method: 'POST', body: { name } });

export const getMyFamily = () => request<FamilyMembersRead>('/sys/families/me');

/** 生成邀请码（父母）；默认 ADVENTURER、72h 有效 */
export const createFamilyInvite = (role: 'GUILD_MASTER' | 'ADVENTURER' = 'ADVENTURER', expires_in_hours = 72) =>
  request<{ id: string; family_id: string; code: string; role: string; expires_at: string }>(
    '/sys/families/invites',
    { method: 'POST', body: { role, expires_in_hours } },
  );

/** 邀请码加入（无账号场景，微信登录被拒后的后路） */
export const joinFamily = (data: FamilyJoinRequest) =>
  request<TokenPair>('/sys/families/join', { method: 'POST', body: data });
