import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { api, type PrivilegeRead } from '../../services/api';
import { X, Plus, Pencil, Trash2, Check, Save, AlertCircle } from 'lucide-react';

interface PrivilegeFormState {
  title: string;
  description: string;
  icon: string;
  level_required: number;
}

interface PrivilegeConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  templates: PrivilegeRead[];
  /** 保存/删除成功后由父级重拉模板列表（服务端为准，不再本地拼装） */
  onSaved: () => void | Promise<void>;
  onToast: (title: string, msg: string) => void;
}

const EMPTY_FORM: PrivilegeFormState = {
  title: '',
  description: '',
  icon: '⭐',
  level_required: 1,
};

const ICON_OPTIONS = ['⭐', '🌳', '🍔', '🏪', '🎮', '🚲', '👑', '🎁', '🏆', '💎'];

const PrivilegeConfigModal: React.FC<PrivilegeConfigModalProps> = ({
  isOpen,
  onClose,
  templates,
  onSaved,
  onToast,
}) => {
  const { t } = useTranslation();
  const [localTemplates, setLocalTemplates] = useState<PrivilegeRead[]>([]);
  const [view, setView] = useState<'list' | 'form'>('list');
  const [editing, setEditing] = useState<PrivilegeRead | null>(null);
  const [form, setForm] = useState<PrivilegeFormState>({ ...EMPTY_FORM });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setLocalTemplates([...templates]);
    setView('list');
    setEditing(null);
    setForm({ ...EMPTY_FORM });
    setFormError(null);
    setDeleting(null);
  }, [isOpen, templates]);

  if (!isOpen) return null;

  const openCreate = () => {
    setEditing(null);
    setForm({ ...EMPTY_FORM });
    setView('form');
    setFormError(null);
  };

  const openEdit = (tpl: PrivilegeRead) => {
    setEditing(tpl);
    setForm({
      title: tpl.title,
      description: tpl.description,
      icon: tpl.icon,
      level_required: tpl.level_required,
    });
    setView('form');
    setFormError(null);
  };

  const handleFieldChange = (field: keyof PrivilegeFormState, value: string | number) => {
    setForm(prev => ({ ...prev, [field]: value }));
    setFormError(null);
  };

  const handleSave = async () => {
    if (saving) return;
    const title = form.title.trim();
    if (!title) {
      setFormError(t('privilegeConfig.titleRequired'));
      return;
    }
    if (form.level_required < 1) {
      setFormError(t('privilegeConfig.levelRequiredMin'));
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      const payload = {
        title,
        description: form.description,
        icon: form.icon,
        level_required: form.level_required,
      };
      if (editing) {
        await api.coins.updatePrivilegeTemplate(editing.id, payload);
      } else {
        await api.coins.createPrivilegeTemplate(payload);
      }
      await onSaved();
      onToast(
        editing ? t('toast.privilegeUpdatedTitle') : t('toast.privilegeCreatedTitle'),
        editing ? t('toast.privilegeUpdatedMsg', { title }) : t('toast.privilegeCreatedMsg', { title }),
      );
      setView('list');
      setEditing(null);
      setForm({ ...EMPTY_FORM });
    } catch (err) {
      setFormError(err instanceof Error ? err.message : t('privilegeConfig.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (deleting) return;
    if (!window.confirm(t('privilegeConfig.confirmDelete'))) return;
    setDeleting(id);
    try {
      await api.coins.deletePrivilegeTemplate(id);
      await onSaved();
      onToast(t('toast.privilegeDeletedTitle'), t('toast.privilegeDeletedMsg'));
    } catch (err) {
      onToast(
        t('toast.deleteFailedTitle'),
        err instanceof Error ? err.message : t('privilegeConfig.deleteFailed'),
      );
    } finally {
      setDeleting(null);
    }
  };

  const handleCancel = () => {
    setView('list');
    setEditing(null);
    setForm({ ...EMPTY_FORM });
    setFormError(null);
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden animate-in zoom-in duration-200 max-h-[90vh] flex flex-col">
        <div className="bg-slate-900 text-white p-4 flex justify-between items-center shrink-0">
          <h3 className="font-bold text-lg flex items-center gap-2">
            {view === 'form' ? (editing ? t('privilegeConfig.editTitle') : t('privilegeConfig.createTitle')) : t('privilegeConfig.title')}
          </h3>
          <button onClick={onClose}><X size={20} /></button>
        </div>

        <div className="p-6 overflow-y-auto flex-1">
          {view === 'list' ? (
            <>
              {localTemplates.length === 0 ? (
                <div className="text-center py-10 text-slate-400">
                  <p className="font-bold">{t('privilegeConfig.empty')}</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {localTemplates.map(tpl => (
                    <div key={tpl.id} className="flex items-center gap-3 p-3 rounded-xl border border-slate-200 bg-slate-50 hover:bg-white hover:shadow-md transition-all">
                      <span className="text-2xl w-8 text-center">{tpl.icon}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-sm text-slate-800 truncate">{tpl.title}</span>
                          {tpl.is_system && <span className="text-xs bg-slate-200 text-slate-500 px-1 rounded">{t('privilegeConfig.systemBadge')}</span>}
                          {!tpl.is_active && <span className="text-xs bg-red-100 text-red-600 px-1 rounded">{t('privilegeConfig.inactiveBadge')}</span>}
                        </div>
                        <p className="text-xs text-slate-500 truncate">{tpl.description || '—'}</p>
                        <p className="text-xs text-slate-400 mt-0.5">{t('common.levelShort')} {tpl.level_required}</p>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          onClick={() => openEdit(tpl)}
                          disabled={tpl.is_system}
                          className="p-1.5 text-slate-400 hover:text-blue-600 rounded-lg hover:bg-blue-50 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                          title={t('privilegeConfig.edit')}
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          onClick={() => handleDelete(tpl.id)}
                          disabled={tpl.is_system || deleting === tpl.id}
                          className="p-1.5 text-slate-400 hover:text-red-600 rounded-lg hover:bg-red-50 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                          title={t('privilegeConfig.delete')}
                        >
                          {deleting === tpl.id ? <AlertCircle size={14} className="animate-pulse" /> : <Trash2 size={14} />}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <div className="mt-4 pt-4 border-t border-slate-200">
                <p className="text-xs text-slate-400 mb-3">{t('privilegeConfig.systemHint')}</p>
                <button
                  onClick={openCreate}
                  className="w-full py-3 border-2 border-dashed border-slate-300 rounded-xl text-sm font-bold text-slate-500 hover:border-green-400 hover:text-green-600 transition-colors flex items-center justify-center gap-2"
                >
                  <Plus size={16} /> {t('privilegeConfig.addNew')}
                </button>
              </div>
            </>
          ) : (
            <div className="space-y-4">
              {formError && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700 font-bold flex items-center gap-2">
                  <AlertCircle size={16} /> {formError}
                </div>
              )}

              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1">{t('privilegeConfig.icon')}</label>
                <div className="flex flex-wrap gap-2">
                  {ICON_OPTIONS.map(icon => (
                    <button
                      key={icon}
                      onClick={() => handleFieldChange('icon', icon)}
                      className={`w-9 h-9 text-xl rounded-lg border-2 flex items-center justify-center transition-all ${
                        form.icon === icon ? 'border-blue-500 bg-blue-50 scale-110' : 'border-slate-200 hover:border-slate-300'
                      }`}
                    >
                      {icon}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1">{t('privilegeConfig.titleLabel')}</label>
                <input
                  type="text"
                  value={form.title}
                  onChange={e => handleFieldChange('title', e.target.value)}
                  placeholder={t('privilegeConfig.titlePlaceholder')}
                  className="w-full p-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1">{t('privilegeConfig.descriptionLabel')}</label>
                <textarea
                  value={form.description}
                  onChange={e => handleFieldChange('description', e.target.value)}
                  placeholder={t('privilegeConfig.descriptionPlaceholder')}
                  rows={2}
                  className="w-full p-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                />
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1">{t('privilegeConfig.levelRequired')}</label>
                <input
                  type="number"
                  min={1}
                  max={99}
                  value={form.level_required}
                  onChange={e => handleFieldChange('level_required', Math.max(1, parseInt(e.target.value) || 1))}
                  className="w-full p-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
          )}
        </div>

        <div className="p-4 bg-slate-50 border-t flex justify-between items-center shrink-0">
          {view === 'form' ? (
            <>
              <button
                onClick={handleCancel}
                className="px-4 py-2 text-slate-600 font-bold hover:bg-slate-200 rounded-lg transition-colors"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-6 py-2 bg-green-600 text-white font-bold rounded-lg hover:bg-green-700 shadow-md flex items-center gap-2 disabled:opacity-50"
              >
                <Save size={16} /> {saving ? t('common.loading') : t('privilegeConfig.save')}
              </button>
            </>
          ) : (
            <button
              onClick={onClose}
              className="px-6 py-2 bg-slate-900 text-white font-bold rounded-lg hover:bg-slate-800 shadow-md flex items-center gap-2 ml-auto"
            >
              <Check size={16} /> {t('common.close')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default PrivilegeConfigModal;
