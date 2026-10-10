import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../../services/api';
import type { SeasonRead, ThemeId } from '../../services/api';
import { THEMES } from '../../constants/themes';
import { Palette, ScrollText, Check, X, Plus, Pencil, Trash2, Zap, CalendarDays } from 'lucide-react';

interface SeasonConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** 本家庭全部赛季（App 持有，含未激活） */
  seasons: SeasonRead[];
  /** 打开时直接进新建表单（无激活赛季的引导场景） */
  openInCreate?: boolean;
  /** CRUD 成功后由 App 重新拉取列表与激活赛季 */
  onRefresh: () => Promise<void>;
  onToast: (title: string, msg: string) => void;
}

type View = 'list' | 'form';

interface FormState {
  name: string;
  themeId: ThemeId;
  narrativeContext: string;
  startDate: string; // YYYY-MM-DD
  endDate: string; // '' = 未设置
}

/** validation_error（422）的 pydantic errors 数组 → 按 loc 末位字段名归组 */
function extractFieldErrors(data: unknown): Record<string, string> {
  if (!Array.isArray(data)) return {};
  const out: Record<string, string> = {};
  for (const item of data) {
    const loc = Array.isArray((item as { loc?: unknown })?.loc)
      ? ((item as { loc: unknown[] }).loc as unknown[])
      : [];
    const field = String(loc[loc.length - 1] ?? '');
    const msg = (item as { msg?: string })?.msg;
    if (field && msg) out[field] = msg;
  }
  return out;
}

const EMPTY_FORM: FormState = { name: '', themeId: 'DEFAULT', narrativeContext: '', startDate: '', endDate: '' };

const SeasonConfigModal: React.FC<SeasonConfigModalProps> = ({
  isOpen,
  onClose,
  seasons,
  openInCreate = false,
  onRefresh,
  onToast,
}) => {
  const { t } = useTranslation();
  const [view, setView] = useState<View>('list');
  const [editing, setEditing] = useState<SeasonRead | null>(null); // form 视图下 null = 新建
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null); // 请求级错误（conflict 等）
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({}); // 422 内联纠错
  const [confirmTarget, setConfirmTarget] = useState<{ action: 'activate' | 'delete'; season: SeasonRead } | null>(null);
  const [acting, setActing] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setConfirmTarget(null);
    setFormError(null);
    setFieldErrors({});
    if (openInCreate) {
      setView('form');
      setEditing(null);
      setForm({ ...EMPTY_FORM, startDate: new Date().toISOString().slice(0, 10) });
    } else {
      setView('list');
    }
  }, [isOpen, openInCreate]);

  if (!isOpen) return null;

  // 激活的排最前，其余按开始日期倒序（与后端列表顺序解耦，展示口径本地定）
  const sortedSeasons = [...seasons].sort((a, b) => {
    if (a.is_active !== b.is_active) return a.is_active ? -1 : 1;
    return b.start_date.localeCompare(a.start_date);
  });

  const openCreate = () => {
    setEditing(null);
    setForm({ ...EMPTY_FORM, startDate: new Date().toISOString().slice(0, 10) });
    setFormError(null);
    setFieldErrors({});
    setView('form');
  };

  const openEdit = (season: SeasonRead) => {
    setEditing(season);
    setForm({
      name: season.name,
      themeId: season.theme_id,
      narrativeContext: season.narrative_context,
      startDate: season.start_date.slice(0, 10),
      endDate: season.end_date ? season.end_date.slice(0, 10) : '',
    });
    setFormError(null);
    setFieldErrors({});
    setView('form');
  };

  /** ApiError → 展示文案：conflict 必须原样透出后端 msg（单激活约束），其余按 error_code 兜底 */
  const describeError = (error: unknown): string => {
    if (error instanceof ApiError) {
      switch (error.errorCode) {
        case 'conflict':
          return error.message; // "该家庭已存在激活中的赛季..."
        case 'permission_denied':
          return t('seasonConfig.errPermission');
        case 'not_found':
          return t('seasonConfig.errNotFound');
        case 'validation_error':
          return t('seasonConfig.errValidation');
        default:
          return error.message || t('seasonConfig.errGeneric');
      }
    }
    return t('seasonConfig.errGeneric');
  };

  const handleSave = async () => {
    if (submitting) return;
    setFormError(null);
    setFieldErrors({});
    setSubmitting(true);
    try {
      const { name, themeId, narrativeContext, startDate, endDate } = form;
      const endDatePart = endDate ? { end_date: endDate } : {};
      let saved: SeasonRead;
      if (editing) {
        // SeasonUpdate 无 start_date（契约：开始日期创建后不可变更，docs/08 §5）
        saved = await api.seasons.updateSeason(editing.id, {
          name: name.trim(),
          theme_id: themeId,
          narrative_context: narrativeContext.trim(),
          ...endDatePart,
        });
      } else {
        // 后端 create 默认 is_active=true 并自动停用原激活赛季（docs/09 §5 D2）
        saved = await api.seasons.createSeason({
          name: name.trim(),
          theme_id: themeId,
          narrative_context: narrativeContext.trim(),
          start_date: startDate,
          ...endDatePart,
        });
      }
      await onRefresh();
      onToast(
        t('toast.seasonUpdatedTitle'),
        editing
          ? t('toast.seasonUpdatedMsg', { theme: THEMES[saved.theme_id]?.name ?? saved.theme_id })
          : t('seasonConfig.createdToast', { name: saved.name }),
      );
      setView('list');
    } catch (error) {
      if (error instanceof ApiError && error.errorCode === 'validation_error') {
        setFieldErrors(extractFieldErrors(error.data));
      }
      setFormError(describeError(error));
    } finally {
      setSubmitting(false);
    }
  };

  const handleConfirmAction = async () => {
    if (!confirmTarget || acting) return;
    setActing(true);
    const { action, season } = confirmTarget;
    try {
      if (action === 'activate') {
        await api.seasons.activateSeason(season.id);
      } else {
        await api.seasons.deleteSeason(season.id);
      }
      await onRefresh();
      onToast(
        t(action === 'activate' ? 'seasonConfig.activatedToast' : 'seasonConfig.deletedToast'),
        t(action === 'activate' ? 'seasonConfig.activatedToastMsg' : 'seasonConfig.deletedToastMsg', { name: season.name }),
      );
      setConfirmTarget(null);
    } catch (error) {
      // 冲突/权限等在确认弹层位置就地呈现，不关闭弹层
      setFormError(describeError(error));
      setConfirmTarget(null);
    } finally {
      setActing(false);
    }
  };

  const renderFieldError = (field: string) =>
    fieldErrors[field] ? <p className="text-xs text-red-600 mt-1">{fieldErrors[field]}</p> : null;

  // ---- 表单视图 ----
  if (view === 'form') {
    const isEdit = editing !== null;
    return (
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200 flex flex-col max-h-[90vh]">
          <div className="bg-slate-900 text-white p-4 flex justify-between items-center shrink-0">
            <h3 className="font-bold text-lg flex items-center gap-2">
              <Palette size={20} /> {isEdit ? t('seasonConfig.editTitle') : t('seasonConfig.createTitle')}
            </h3>
            <button onClick={() => setView('list')} aria-label={t('seasonConfig.backToList')}><X /></button>
          </div>

          <div className="p-6 overflow-y-auto space-y-6">
            {formError && (
              <div role="alert" className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm font-bold">
                {formError}
              </div>
            )}

            {/* 基础信息 */}
            <div className="space-y-4">
              <div>
                <label htmlFor="season-name" className="block text-sm font-bold text-slate-700 mb-1">{t('seasonConfig.seasonName')}</label>
                <input
                  id="season-name"
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full border border-slate-300 rounded-lg p-2 font-bold focus:ring-2 focus:ring-blue-500 outline-none"
                  placeholder={t('seasonConfig.seasonNamePlaceholder')}
                />
                {renderFieldError('name')}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="season-start" className="block text-sm font-bold text-slate-700 mb-1">{t('seasonConfig.startDate')}</label>
                  <input
                    id="season-start"
                    type="date"
                    required
                    disabled={isEdit}
                    value={form.startDate}
                    onChange={(e) => setForm({ ...form, startDate: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2 focus:ring-2 focus:ring-blue-500 outline-none disabled:bg-slate-100 disabled:text-slate-400"
                  />
                  {isEdit && <p className="text-xs text-slate-500 mt-1">{t('seasonConfig.startDateLockHint')}</p>}
                  {renderFieldError('start_date')}
                </div>
                <div>
                  <label htmlFor="season-end" className="block text-sm font-bold text-slate-700 mb-1">{t('seasonConfig.endDate')}</label>
                  <input
                    id="season-end"
                    type="date"
                    value={form.endDate}
                    onChange={(e) => setForm({ ...form, endDate: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2 focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                  {isEdit && form.endDate && (
                    <p className="text-xs text-slate-500 mt-1">{t('seasonConfig.endDateLockHint')}</p>
                  )}
                  {renderFieldError('end_date')}
                </div>
              </div>

              <div>
                <label htmlFor="season-lore" className="block text-sm font-bold text-slate-700 mb-1 flex items-center gap-2">
                  <ScrollText size={16} /> {t('seasonConfig.narrativeContext')}
                </label>
                <textarea
                  id="season-lore"
                  value={form.narrativeContext}
                  onChange={(e) => setForm({ ...form, narrativeContext: e.target.value })}
                  className="w-full h-24 border border-slate-300 rounded-lg p-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none resize-none"
                  placeholder={t('seasonConfig.narrativePlaceholder')}
                />
                <p className="text-xs text-slate-500 mt-1">{t('seasonConfig.aiHint')}</p>
              </div>
            </div>

            {/* 主题选择 */}
            <div>
              <h4 className="text-sm font-bold text-slate-700 mb-3">{t('seasonConfig.visualTheme')}</h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {(Object.values(THEMES) as (typeof THEMES)[ThemeId][]).map((theme) => (
                  <div
                    key={theme.id}
                    onClick={() => setForm({ ...form, themeId: theme.id })}
                    className={`cursor-pointer rounded-xl p-3 border-2 transition-all relative overflow-hidden group
                      ${form.themeId === theme.id ? 'border-blue-500 shadow-lg scale-105' : 'border-slate-200 hover:border-blue-300'}
                    `}
                  >
                    <div className={`absolute inset-0 opacity-10 ${theme.primaryColor}`}></div>
                    <div className="flex items-center gap-3 relative z-10">
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xl shadow-sm ${theme.primaryColor} text-white`}>
                        {theme.icon}
                      </div>
                      <div>
                        <h5 className="font-bold text-slate-800 text-sm">{theme.name}</h5>
                        <p className="text-xs text-slate-500">{t('seasonConfig.previewStyle')}</p>
                      </div>
                      {form.themeId === theme.id && <div className="absolute right-0 top-0 p-1 bg-blue-500 text-white rounded-bl-lg"><Check size={12} /></div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {!isEdit && (
              <p className="text-xs text-slate-500 bg-blue-50 border border-blue-100 rounded-lg p-3">
                {t('seasonConfig.createAutoActivateHint')}
              </p>
            )}
          </div>

          <div className="p-4 bg-slate-50 border-t flex justify-end gap-2 shrink-0">
            <button onClick={() => setView('list')} className="px-4 py-2 text-slate-600 font-bold hover:bg-slate-200 rounded-lg">{t('common.cancel')}</button>
            <button
              onClick={handleSave}
              disabled={submitting || !form.name.trim() || !form.startDate}
              className="px-6 py-2 bg-green-600 text-white font-bold rounded-lg hover:bg-green-700 shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? t('seasonConfig.saving') : isEdit ? t('seasonConfig.saveEdit') : t('seasonConfig.save')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ---- 列表视图 ----
  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200 flex flex-col max-h-[90vh]">
        <div className="bg-slate-900 text-white p-4 flex justify-between items-center shrink-0">
          <h3 className="font-bold text-lg flex items-center gap-2">
            <Palette size={20} /> {t('seasonConfig.title')}
          </h3>
          <button onClick={onClose}><X /></button>
        </div>

        <div className="p-6 overflow-y-auto space-y-4">
          {formError && (
            <div role="alert" className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm font-bold">
              {formError}
            </div>
          )}

          {sortedSeasons.length === 0 ? (
            <div className="text-center py-12 bg-slate-50 rounded-xl border-2 border-dashed border-slate-300">
              <CalendarDays className="mx-auto text-slate-300 mb-3" size={40} />
              <p className="text-slate-500 font-bold">{t('seasonConfig.emptyTitle')}</p>
              <p className="text-slate-400 text-sm">{t('seasonConfig.emptyHint')}</p>
            </div>
          ) : (
            <ul className="space-y-3">
              {sortedSeasons.map((season) => {
                const theme = THEMES[season.theme_id] || THEMES.DEFAULT;
                return (
                  <li
                    key={season.id}
                    className={`rounded-xl border p-4 flex flex-col sm:flex-row sm:items-center gap-3 ${
                      season.is_active ? 'border-green-300 bg-green-50/50' : 'border-slate-200 bg-white'
                    }`}
                  >
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xl shadow-sm shrink-0 ${theme.primaryColor} text-white`}>
                      {theme.icon}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h4 className="font-bold text-slate-800 truncate">{season.name}</h4>
                        {season.is_active ? (
                          <span className="text-[10px] font-bold bg-green-600 text-white px-2 py-0.5 rounded-full">{t('seasonConfig.activeBadge')}</span>
                        ) : (
                          <span className="text-[10px] font-bold bg-slate-200 text-slate-500 px-2 py-0.5 rounded-full">{t('seasonConfig.inactiveBadge')}</span>
                        )}
                      </div>
                      <p className="text-xs text-slate-400 font-mono mt-0.5">
                        {season.start_date.slice(0, 10)} ~ {season.end_date ? season.end_date.slice(0, 10) : '∞'} · {theme.name}
                      </p>
                    </div>
                    <div className="flex gap-2 shrink-0">
                      {!season.is_active && (
                        <button
                          onClick={() => { setFormError(null); setConfirmTarget({ action: 'activate', season }); }}
                          className="px-3 py-1.5 bg-blue-600 text-white text-xs font-bold rounded-lg hover:bg-blue-700 flex items-center gap-1"
                        >
                          <Zap size={12} /> {t('seasonConfig.activate')}
                        </button>
                      )}
                      <button
                        onClick={() => openEdit(season)}
                        className="px-3 py-1.5 bg-slate-100 text-slate-700 text-xs font-bold rounded-lg hover:bg-slate-200 flex items-center gap-1"
                      >
                        <Pencil size={12} /> {t('seasonConfig.edit')}
                      </button>
                      <button
                        onClick={() => { setFormError(null); setConfirmTarget({ action: 'delete', season }); }}
                        className="px-3 py-1.5 bg-red-50 text-red-600 text-xs font-bold rounded-lg hover:bg-red-100 flex items-center gap-1"
                      >
                        <Trash2 size={12} /> {t('seasonConfig.delete')}
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <button
            onClick={openCreate}
            className="w-full py-3 border-2 border-dashed border-slate-300 rounded-xl text-slate-500 font-bold text-sm hover:border-blue-400 hover:text-blue-600 transition-colors flex items-center justify-center gap-2"
          >
            <Plus size={16} /> {t('seasonConfig.createTitle')}
          </button>
        </div>

        <div className="p-4 bg-slate-50 border-t flex justify-end shrink-0">
          <button onClick={onClose} className="px-4 py-2 text-slate-600 font-bold hover:bg-slate-200 rounded-lg">{t('common.close')}</button>
        </div>
      </div>

      {/* 激活 / 删除确认层 */}
      {confirmTarget && (
        <div className="fixed inset-0 bg-black/40 z-[60] flex items-center justify-center p-4" role="dialog" aria-modal="true">
          <div className="bg-white rounded-xl w-full max-w-sm p-5 shadow-2xl animate-in fade-in zoom-in duration-150">
            <h4 className={`font-bold text-base mb-2 flex items-center gap-2 ${confirmTarget.action === 'delete' ? 'text-red-600' : 'text-blue-700'}`}>
              {confirmTarget.action === 'delete' ? <Trash2 size={16} /> : <Zap size={16} />}
              {t(confirmTarget.action === 'delete' ? 'seasonConfig.deleteConfirmTitle' : 'seasonConfig.activateConfirmTitle')}
            </h4>
            <p className="text-sm text-slate-600 mb-4">
              {t(
                confirmTarget.action === 'delete'
                  ? 'seasonConfig.deleteConfirmBody'
                  : 'seasonConfig.activateConfirmBody',
                { name: confirmTarget.season.name },
              )}
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setConfirmTarget(null)} className="px-4 py-2 text-slate-600 font-bold hover:bg-slate-100 rounded-lg text-sm">
                {t('common.cancel')}
              </button>
              <button
                onClick={handleConfirmAction}
                disabled={acting}
                className={`px-4 py-2 text-white font-bold rounded-lg text-sm disabled:opacity-50 ${
                  confirmTarget.action === 'delete' ? 'bg-red-600 hover:bg-red-700' : 'bg-blue-600 hover:bg-blue-700'
                }`}
              >
                {acting ? t('seasonConfig.saving') : t('common.confirm')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SeasonConfigModal;
