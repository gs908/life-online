
export enum UserRole {
  PARENT = 'GUILD_MASTER',
  CHILD = 'ADVENTURER'
}

export type ThemeId = 'DEFAULT' | 'FROSTBOUND' | 'INFERNO' | 'SYLVAN' | 'CYBERPUNK';

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

export interface Season {
  id: string;
  name: string; // e.g. "Winter Semester 2024"
  themeId: ThemeId;
  narrativeContext: string; // e.g. "Frost Giants are attacking the town."
  startDate: string;
  endDate?: string;
  isActive: boolean;
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
  name: string;
  role: UserRole;
  level: number;
  xp: number;
  avatar: string;
  locale?: string;
  privilegesUnlocked: number[]; // Array of levels
  
  // New Time Coin Logic
  timeCoins: number;
  dailyAbandonCount: number;
  lastLoginDate?: string; // To track daily resets
}

export interface Task {
  id: string;
  seasonId: string; // Link to specific season for history
  title: string;
  description: string; // Can be "lore" text
  xpReward: number;
  type: TaskType;
  status: TaskStatus;
  deadline?: string; // ISO string for strict deadline
  requiredStartTime?: string; // "HH:MM" format
  proofImage?: string; // Base64 data URI
  rating?: number; // 1-5 stars given by parent
  assigneeId?: string; // If null, anyone can pick it up
  loreSnippet?: string; // AI generated flavor text
  
  // Logic Fields
  startedAt?: string; // ISO String, set when status becomes IN_PROGRESS
  reminderMessage?: string; // "The mist is closing in! (15 mins left)"
  reminderMinutesBefore?: number; // Default 15
  
  // Coin Logic
  timeDeposit?: number; // Cost to accept task (default 10?)
}
