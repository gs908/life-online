/**
 * /scn/seasons（契约 §5）—— 替换阶段②（docs/10 §4）
 */
import { request } from '../http';
import type { SeasonCreate, SeasonHistoryItem, SeasonRead, SeasonUpdate } from '../types';

export const listSeasons = (includeInactive = true) =>
  request<SeasonRead[]>('/scn/seasons', { query: { include_inactive: includeInactive } });

/** 无激活赛季时 data 为 null */
export const getActiveSeason = () => request<SeasonRead | null>('/scn/seasons/active');

/** 赛季历史 + 完成度统计（SeasonHistoryItem，替代 Mock 的 Season[]，docs/09 S3） */
export const getSeasonHistory = () => request<SeasonHistoryItem[]>('/scn/seasons/history');

export const getSeason = (seasonId: string) =>
  request<SeasonRead>(`/scn/seasons/${encodeURIComponent(seasonId)}`);

export const createSeason = (data: SeasonCreate) =>
  request<SeasonRead>('/scn/seasons', { method: 'POST', body: data });

export const updateSeason = (seasonId: string, data: SeasonUpdate) =>
  request<SeasonRead>(`/scn/seasons/${encodeURIComponent(seasonId)}`, { method: 'PATCH', body: data });

/** 激活（家庭内互斥，自动停用其他） */
export const activateSeason = (seasonId: string) =>
  request<SeasonRead>(`/scn/seasons/${encodeURIComponent(seasonId)}/activate`, { method: 'POST' });

export const deleteSeason = (seasonId: string) =>
  request<null>(`/scn/seasons/${encodeURIComponent(seasonId)}`, { method: 'DELETE' });
