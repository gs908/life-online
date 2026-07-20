
import React, { useState, useRef } from 'react';
import { Camera } from 'lucide-react';

interface SubmitTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (proofImage: string | null) => void;
}

const SubmitTaskModal: React.FC<SubmitTaskModalProps> = ({ isOpen, onClose, onSubmit }) => {
  const [proofImage, setProofImage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setProofImage(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl p-6">
        <h3 className="text-xl font-bold mb-4">Complete Quest</h3>
        <p className="text-sm text-slate-600 mb-4">Upload a photo to prove your deed, adventurer!</p>

        <input type="file" ref={fileInputRef} onChange={handleFileChange} className="hidden" accept="image/*" />

        <div
          onClick={() => fileInputRef.current?.click()}
          className="w-full h-48 border-2 border-dashed border-slate-300 rounded-xl flex flex-col items-center justify-center cursor-pointer hover:bg-slate-50 transition-colors mb-4"
        >
          {proofImage ? (
            <img src={proofImage} alt="Proof" className="h-full w-full object-contain rounded-xl" />
          ) : (
            <div className="text-center text-slate-400">
              <Camera size={48} className="mx-auto mb-2" />
              <span className="text-sm font-bold">Tap to take photo</span>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2">
          <button onClick={() => { setProofImage(null); onClose(); }} className="px-4 py-2 text-slate-600 font-bold">Cancel</button>
          <button onClick={() => onSubmit(proofImage)} disabled={!proofImage} className="px-4 py-2 bg-green-600 text-white font-bold rounded disabled:opacity-50">Submit</button>
        </div>
      </div>
    </div>
  );
};

export default SubmitTaskModal;
