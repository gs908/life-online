import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Camera, Film, X } from 'lucide-react';

/** 与后端 server/config.yaml upload 段对齐（无配置下发接口，前端镜像默认值） */
export const MAX_PROOF_FILES = 9;
export const MAX_PROOF_FILE_MB = 50;

interface ProofItem {
  file: File;
  /** 本地预览 object URL（图片直接展示；视频取首帧元数据） */
  previewUrl: string;
  isVideo: boolean;
}

interface SubmitTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  /**
   * 提交所选文件；上传（POST /sys/uploads 循环）与 submit 由 App 编排（docs/10 §4 阶段③）。
   * reportProgress：整体上传进度 0-100（当前文件百分比 + 已完成文件数折算），由 App 逐个上传时回调。
   */
  onSubmit: (files: File[], reportProgress: (percent: number) => void) => void;
  submitting?: boolean;
}

/**
 * 提交任务证明（DEV-33 块 E 多证据）：多选图片+视频、逐个预览/删除、整体上传进度。
 *
 * React 19.x 约束（"Expected static flag was missing" 踩坑记录）：
 * 1. 本组件由 App.tsx 无条件渲染（始终挂载），所有 hooks 必须在
 *    `if (!isOpen) return null` 之前无条件调用，否则 React 在 isOpen 变化时
 *    检测到 hooks 数量不一致，抛出 "Expected static flag was missing"。
 * 2. `useEffect([isOpen])` 中在 isOpen=true 时调 setState 会在 React 19.2
 *    并发渲染下损坏 fiber 静态标记（commit 帧内调 setState）。重置逻辑改为
 *    在 cleanup（isOpen true→false）里执行。
 * 3. `reportProgressRef.current` 在 `isOpen=false` 时必须置为 no-op，
 *    否则 App.tsx 的 `handleSubmitTask` 在 `setIsSubmitModalOpen(false)` 后
 *    仍可能触发 ref 里的 `setProgress`，对已"null 渲染"的组件调 setState
 *    同样导致 React 19.x fiber 损坏。
 */
const SubmitTaskModal: React.FC<SubmitTaskModalProps> = ({ isOpen, onClose, onSubmit, submitting }) => {
  const { t } = useTranslation();
  const [proofs, setProofs] = useState<ProofItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);

  /** ref 镜像 proofs 列表，供 unmount cleanup 回收 object URL（不触发 setState） */
  const proofsRef = useRef<ProofItem[]>([]);

  /**
   * ref 镜像 setProgress 包装。
   * 关键：isOpen=false 时置为 no-op，防止 App 侧异步回调在 modal 已关闭后仍触发 setProgress。
   */
  const reportProgressRef = useRef<(p: number) => void>(() => {});
  reportProgressRef.current = isOpen
    ? (p: number) => setProgress(Math.min(100, Math.max(0, p)))
    : () => {};

  /** 组件完全卸载时统一回收 object URL */
  useEffect(() => {
    return () => {
      proofsRef.current.forEach((p) => URL.revokeObjectURL(p.previewUrl));
      proofsRef.current = [];
    };
  }, []);

  /**
   * isOpen true→false（弹窗关闭）时 cleanup 执行：
   * 重置 proofs/error/progress 为初始值，下次打开时自动是干净状态。
   * 不在 effect 体内（isOpen false→true）调 setState。
   */
  useEffect(() => {
    if (isOpen) {
      proofsRef.current = proofs;
    }
    return () => {
      setProofs([]);
      proofsRef.current = [];
      setError(null);
      setProgress(null);
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const acceptType = 'image/*,video/*';

  const isSupported = (file: File) =>
    /^image\//.test(file.type) || /^video\//.test(file.type);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(e.target.files ?? []) as File[];
    e.target.value = ''; // 允许重复选择同一文件
    if (!picked.length) return;

    const next: ProofItem[] = [];
    for (const file of picked) {
      if (!isSupported(file)) {
        setError(t('submitTask.unsupportedType', { name: file.name }));
        break;
      }
      if (file.size > MAX_PROOF_FILE_MB * 1024 * 1024) {
        setError(t('submitTask.fileTooLarge', { name: file.name, limit: MAX_PROOF_FILE_MB }));
        break;
      }
      if (proofs.length + next.length >= MAX_PROOF_FILES) {
        setError(t('submitTask.tooManyFiles', { count: MAX_PROOF_FILES }));
        break;
      }
      next.push({
        file,
        previewUrl: URL.createObjectURL(file),
        isVideo: /^video\//.test(file.type),
      });
    }
    if (next.length) {
      const updated = [...proofs, ...next];
      setProofs(updated);
      proofsRef.current = updated;
      setError(null);
    }
  };

  const removeProof = (index: number) => {
    URL.revokeObjectURL(proofsRef.current[index].previewUrl);
    const updated = proofsRef.current.filter((_, i) => i !== index);
    proofsRef.current = updated;
    setProofs(updated);
    setError(null);
  };

  const canSubmit = proofs.length > 0 && !submitting;

  const handleSubmit = () => {
    if (!canSubmit) return;
    onSubmit(
      proofs.map((p) => p.file),
      (percent) => reportProgressRef.current(percent),
    );
  };

  const thumbnails = useMemo(
    () =>
      proofs.map((p, i) => (
        <div key={`${p.file.name}-${i}`} className="relative w-20 h-20 rounded-lg overflow-hidden border border-slate-200 group">
          {p.isVideo ? (
            <video src={p.previewUrl} muted preload="metadata" className="h-full w-full object-cover" />
          ) : (
            <img src={p.previewUrl} alt={p.file.name} className="h-full w-full object-cover" />
          )}
          {p.isVideo && (
            <Film size={14} className="absolute top-1 left-1 text-white drop-shadow" aria-hidden />
          )}
          <button
            type="button"
            onClick={() => removeProof(i)}
            disabled={submitting}
            aria-label={t('submitTask.removeFile', { name: p.file.name })}
            className="absolute top-0.5 right-0.5 bg-black/60 text-white rounded-full p-0.5 hover:bg-black/80 disabled:opacity-50"
          >
            <X size={12} />
          </button>
        </div>
      )),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [proofs, submitting, t],
  );

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl p-6">
        <h3 className="text-xl font-bold mb-4">{t('submitTask.title')}</h3>
        <p className="text-sm text-slate-600 mb-4">{t('submitTask.hint')}</p>

        {proofs.length < MAX_PROOF_FILES && (
          <label className="block w-full h-24 border-2 border-dashed border-slate-300 rounded-xl cursor-pointer hover:bg-slate-50 transition-colors mb-3">
            <div className="text-center text-slate-400 flex flex-col items-center justify-center h-full">
              <Camera size={28} className="mb-1" />
              <span className="text-sm font-bold">
                {proofs.length ? t('submitTask.addMore', { count: MAX_PROOF_FILES - proofs.length }) : t('submitTask.takePhoto')}
              </span>
            </div>
            <input
              type="file"
              multiple
              accept={acceptType}
              onChange={handleFileChange}
              disabled={submitting}
              className="hidden"
            />
          </label>
        )}

        {proofs.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-3" role="list" aria-label={t('submitTask.proofListAlt')}>
            {thumbnails}
          </div>
        )}

        {progress !== null && (
          <div className="mb-3" aria-live="polite">
            <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
              <div className="h-full bg-green-500 transition-all duration-200" style={{ width: `${progress}%` }} />
            </div>
            <p className="text-xs text-slate-500 mt-1">{t('submitTask.uploading', { percent: progress })}</p>
          </div>
        )}

        {error && (
          <p className="text-xs text-red-600 bg-red-50 rounded p-2 mb-3" data-testid="submit-task-error">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold">{t('common.cancel')}</button>
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="px-4 py-2 bg-green-600 text-white font-bold rounded disabled:opacity-50"
          >
            {submitting ? t('submitTask.submitting') : t('common.submit')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SubmitTaskModal;
