
// ThemeId / Season 已删除（阶段②，docs/09 §4.6 不共存）：
// 赛季数据一律使用 services/api 的 SeasonRead / SeasonHistoryItem（snake_case），
// ThemeId 枚举以 services/api/types.ts 为准
import type { ThemeId } from './services/api/types';

export enum UserRole {
  PARENT = 'GUILD_MASTER',
  CHILD = 'ADVENTURER'
}

export interface SeasonTheme {
  id: ThemeId;
  name: string;
  primaryColor: string; // Tailwind class e.g. 'bg-blue-600'
  accentColor: string;
  backgroundColor: string;
  textColor: string;
  icon: string; // Emoji or Lucide name reference
  bgImage?: string; // CSS gradient or url
}

export enum TaskType {
  DAILY = 'DAILY',
  CHALLENGE = 'CHALLENGE',
  CHAIN = 'CHAIN', // Serial quest
  TIMED = 'TIMED', // Must start before X
  COOP = 'COOP'    // Multi-child or Parent-Child
}

export enum TaskStatus {
  AVAILABLE = 'AVAILABLE',
  IN_PROGRESS = 'IN_PROGRESS',
  PENDING_REVIEW = 'PENDING_REVIEW',
  COMPLETED = 'COMPLETED',
  EXPIRED = 'EXPIRED'
}

export interface Privilege {
  levelRequired: number;
  title: string;
  description: string;
  icon: string;
}

export interface RedemptionRecord {
  id: string;
  privilegeTitle: string;
  date: string; // ISO String
  cost?: string; // Optional context like "Monthly Use"
  user?: string;
}

export interface TimeConfig {
  defaultDailyAllowance: number;
  exceptions: Record<number, number>; // 0=Sunday, 1=Monday... key is day index, value is coin amount
}

export interface User {
  id: string;
  /** 冒险者扩展档案 ID（任务 target/assignee 用它，不是账号 id；docs/09 A4）。父母为 null */
  childId: string | null;
  name: string;
  role: UserRole;
  level: number;
  xp: number;
  avatar: string;
  locale?: string;
  // privilegesUnlocked 已删除（docs/09 P2 类型冲突：本地等级数组 vs 后端模板 ID 数组），
  // 特权接入属阶段④，届时按 /scn/privileges/unlocks 渲染

  // New Time Coin Logic
  timeCoins: number;
  dailyAbandonCount: number;
}

// Task 视图类型已删除（阶段③）：任务统一使用后端 TaskRead（services/api，snake_case 直传，
// docs/09 §1.6 A1-A6 / docs/10 §4 阶段③）。前端不再维护本地任务状态机。
