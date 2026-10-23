/**
 * /scn/ai（契约 §13）—— 替换阶段⑥（docs/10 §5）
 *
 * 本模块替代并最终取代 services/geminiService.ts：
 * - 删除 geminiService.ts 与 @google/genai 依赖、构建配置中的 API_KEY 注入
 *   （浏览器持有 LLM key 属于密钥泄漏）。
 * - AI 调用统一走后端，父母 token。
 * - evaluate-proof 当前为纯文本评分（后端未把图送入模型），UI 文案不得声称"AI 看图评分"。
 */
import { request } from '../http';
import type {
  EvaluateProofRequest,
  EvaluateProofResult,
  GeneratedQuest,
  GenerateQuestRequest,
} from '../types';

/** AI 生成任务文案。data 来自 LLM，运行时校验关键字段，异常时抛 ApiError('external_service_error') */
export const generateQuest = async (data: GenerateQuestRequest): Promise<GeneratedQuest> => {
  const result = await request<Partial<GeneratedQuest>>('/scn/ai/generate-quest', {
    method: 'POST',
    body: data,
  });
  // LLM 输出无静态 schema 强约束（契约 §13），运行时兜底校验
  const { title, description, lore_snippet, xp_reward, type } = result;
  if (!title || !description || !lore_snippet || typeof xp_reward !== 'number' || !type) {
    throw Object.assign(new Error('AI 返回内容不完整，请重试'), { name: 'AiFormatError' });
  }
  return result as GeneratedQuest;
};

/** AI 评分任务证明（父母）；结果仅供参考 */
export const evaluateProof = (data: EvaluateProofRequest) =>
  request<EvaluateProofResult>('/scn/ai/evaluate-proof', { method: 'POST', body: data });
