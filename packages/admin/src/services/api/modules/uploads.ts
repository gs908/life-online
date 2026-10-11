/**
 * /sys/uploads（契约 §12）—— 替换阶段⑤（docs/10 §4）
 * multipart 上传；任务证明 purpose=task_proof，展示用 access_url，提交任务用 object_key。
 */
import { upload } from '../http';
import type { UploadPurpose, UploadRead } from '../types';

export const uploadFile = (file: File, purpose: UploadPurpose, taskId?: string) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('purpose', purpose);
  // 任务证明上传携带任务号,后端按 `{prefix}/{用户}/{年}/{月}/{日}/{任务号}-{序号}.{扩展名}` 落存储
  if (taskId) formData.append('task_id', taskId);
  return upload<UploadRead>('/sys/uploads', formData);
};
