/**
 * UserRead（后端唯一形状，snake_case）→ 本地视图 User（camelCase）
 *
 * 阶段①过渡适配层：dashboards 仍消费本地 User（任务/时间币接入属阶段③④），
 * 本层只做字段名转换，不做业务计算。用户数据一律来自后端，Mock 用户已删除（docs/10 §4 阶段①）。
 */
import type { UserRead } from '../services/api';
import { User, UserRole } from '../types';

export function mapUserRead(u: UserRead): User {
  return {
    id: u.id,
    name: u.name,
    role: u.role === 'GUILD_MASTER' ? UserRole.PARENT : UserRole.CHILD,
    level: u.level,
    xp: u.xp,
    avatar: u.avatar || '⚔️',
    locale: u.locale,
    // 特权模板 ID（string[]）与本地旧数字等级不同维度；特权接入属阶段④，暂不透传
    privilegesUnlocked: [],
    timeCoins: u.time_coins,
    dailyAbandonCount: u.daily_abandon_count,
  };
}
