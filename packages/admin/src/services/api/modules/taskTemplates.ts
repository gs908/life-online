/**
 * /scn/task-templates（契约 §6A，DEV-35 块 A）
 *
 * 模板级接口只管模板与触发规则：POST 只建模板+触发规则，
 * 创建/改规则/激活后由后端生成器即时补一次生成（docs/12 块 A）。
 * 「一次性」任务不走这里 —— 走 /scn/task-instances（modules/tasks.ts createTask）。
 */
import { request } from '../http';
import type {
  TaskTemplateCreate,
  TaskTemplateDeprecateRequest,
  TaskTemplateListQuery,
  TaskTemplateRead,
  TaskTemplateRegenerateResult,
  TaskTemplateUpdate,
} from '../types';

/** 模板列表（含 triggers，不分页；is_active 不传 = 全部） */
export const listTemplates = (query: TaskTemplateListQuery = {}) =>
  request<TaskTemplateRead[]>('/scn/task-templates', { query });

export const getTemplate = (templateId: string) =>
  request<TaskTemplateRead>(`/scn/task-templates/${encodeURIComponent(templateId)}`);

/** 创建模板+触发规则并即时生成（父母） */
export const createTemplate = (data: TaskTemplateCreate) =>
  request<TaskTemplateRead>('/scn/task-templates', { method: 'POST', body: data });

/** 部分更新；triggers 传则整组替换，后端对合并后的完整模板复验 timed_mode（422） */
export const updateTemplate = (templateId: string, data: TaskTemplateUpdate) =>
  request<TaskTemplateRead>(`/scn/task-templates/${encodeURIComponent(templateId)}`, {
    method: 'PATCH',
    body: data,
  });

/** 废弃（停用+审计；既有实例不动） */
export const deprecateTemplate = (templateId: string, data: TaskTemplateDeprecateRequest = {}) =>
  request<TaskTemplateRead>(`/scn/task-templates/${encodeURIComponent(templateId)}/deprecate`, {
    method: 'POST',
    body: data,
  });

/** 重新启用并立即补生成（父母/管理端） */
export const activateTemplate = (templateId: string) =>
  request<TaskTemplateRead>(`/scn/task-templates/${encodeURIComponent(templateId)}/activate`, {
    method: 'POST',
  });

/** 终结未消费实例并立即生成（父母/管理端）。终结范围 AVAILABLE+IN_PROGRESS（PENDING_REVIEW
 *  保留审核机会、仍占槽位）；押金由后端全额退还。按响应 action 分支提示：
 *  created=正常成功；kept=待审核实例占用未新建；exists=已有当日实例未重复生成。 */
export const regenerateTemplate = (templateId: string) =>
  request<TaskTemplateRegenerateResult>(
    `/scn/task-templates/${encodeURIComponent(templateId)}/regenerate`,
    { method: 'POST', body: {} },
  );

/** 硬删（连同实例与规则；管理端=家庭 owner），不可恢复 */
export const deleteTemplate = (templateId: string) =>
  request<null>(`/scn/task-templates/${encodeURIComponent(templateId)}`, { method: 'DELETE' });
