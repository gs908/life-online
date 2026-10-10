import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Camera } from 'lucide-react';

interface SubmitTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** 提交原始文件；上传（POST /sys/uploads）与 submit 由 App 编排（docs/10 §4 阶段③） */
  onSubmit: (file: File) => void;
  submitting?: boolean;
}

/** 提交任务证明（阶段③）：base64 方案已删除（docs/09 A2），改为上传真实文件换 object_key */
const SubmitTaskModal: React.FC<SubmitTaskModalProps> = ({ isOpen, onClose, onSubmit, submitting }) => {
  const { t } = useTranslation();
  const [proofFile, setProofFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setProofFile(null);
      setPreviewUrl(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setProofFile(file);
      // 本地预览用 dataURL，上传走原文件（multipart）
      const reader = new FileReader();
      reader.onloadend = () => setPreviewUrl(reader.result as string);
      reader.readAsDataURL(file);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl p-6">
        <h3 className="text-xl font-bold mb-4">{t('submitTask.title')}</h3>
        <p className="text-sm text-slate-600 mb-4">{t('submitTask.hint')}</p>

        <label className="block w-full h-48 border-2 border-dashed border-slate-300 rounded-xl flex-col items-center justify-center cursor-pointer hover:bg-slate-50 transition-colors mb-4 overflow-hidden">
          {previewUrl ? (
            <img src={previewUrl} alt={t('submitTask.proofAlt')} className="h-full w-full object-contain rounded-xl" />
          ) : (
            <div className="text-center text-slate-400 flex flex-col items-center justify-center h-full">
              <Camera size={48} className="mx-auto mb-2" />
              <span className="text-sm font-bold">{t('submitTask.takePhoto')}</span>
            </div>
          )}
          <input type="file" onChange={handleFileChange} className="hidden" accept="image/*" />
        </label>

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold">{t('common.cancel')}</button>
          <button
            onClick={() => proofFile && onSubmit(proofFile)}
            disabled={!proofFile || submitting}
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
