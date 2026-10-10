import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../../services/api';
import type { CoinTransactionRead, FamilyMembersRead } from '../../services/api';
import { Coins, X, ChevronLeft, ChevronRight, ArrowDownCircle, ArrowUpCircle, Wallet } from 'lucide-react';

interface CoinLogsModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** 家庭成员（筛选用 adventurers 的 child_id/名字） */
  family: FamilyMembersRead | null;
  onToast: (title: string, msg: string) => void;
  /** 调整成功后余额变化，由 App refetch UserRead.time_coins */
  onAdjusted: () => Promise<void> | void;
}

const PAGE_SIZE = 20;

/**
 * 时间币流水（阶段④，契约 §8）：GET /scn/time-coin-logs 分页 + POST /scn/time-coin-logs/adjust（父母）。
 * 不传 child_id 返回全家流水（按 created_at 倒序）；新代码不读兼容字段 user_id/task_id（docs/10 §2.2）。
 */
const CoinLogsModal: React.FC<CoinLogsModalProps> = ({ isOpen, onClose, family, onToast, onAdjusted }) => {
  const { t } = useTranslation();
  const [items, setItems] = useState<CoinTransactionRead[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [childFilter, setChildFilter] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // 人工调整表单（父母）
  const [adjustChild, setAdjustChild] = useState<string>('');
  const [adjustAmount, setAdjustAmount] = useState<string>('');
  const [adjustNote, setAdjustNote] = useState('');
  const [adjustError, setAdjustError] = useState<string | null>(null);
  const [adjusting, setAdjusting] = useState(false);

  const adventurers = family?.adventurers ?? [];
  const childName = useCallback(
    (childId: string) => adventurers.find(a => a.child_id === childId)?.name ?? childId,
    [adventurers]
  );

  const loadLogs = useCallback(async (targetPage: number, childId: string) => {
    setLoading(true);
    setLoadError(null);
    try {
      const result = await api.coins.listCoinLogs({
        page: targetPage,
        page_size: PAGE_SIZE,
        child_id: childId || undefined,
      });
      setItems(result.items);
      setTotal(result.total);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : t('coinLogs.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (!isOpen) return;
    setPage(1);
    setChildFilter('');
    setAdjustChild(adventurers[0]?.child_id ?? '');
    setAdjustAmount('');
    setAdjustNote('');
    setAdjustError(null);
    loadLogs(1, '');
    // adventurers 由 family 派生，重开时仅取首项做默认值，不随其变化重置表单
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    loadLogs(page, childFilter);
  }, [isOpen, page, childFilter, loadLogs]);

  if (!isOpen) return null;

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const handleAdjust = async () => {
    if (adjusting) return;
    const amount = parseInt(adjustAmount, 10);
    // 后端不校验 amount≠0，前端拦截 0/空
    if (!adjustChild || isNaN(amount) || amount === 0) {
      setAdjustError(t('coinLogs.adjustAmountInvalid'));
      return;
    }
    setAdjusting(true);
    setAdjustError(null);
    try {
      await api.coins.adjustCoins({
        child_id: adjustChild,
        amount,
        note: adjustNote.trim() || undefined,
      });
      onToast(t('coinLogs.adjustDoneTitle'), t('coinLogs.adjustDoneMsg', { amount, name: childName(adjustChild) }));
      setAdjustAmount('');
      setAdjustNote('');
      // 流水回到第一页重拉；余额一律以后端为准（refetch UserRead）
      if (page === 1) {
        await loadLogs(1, childFilter);
      } else {
        setPage(1); // 触发分页 effect 重拉
      }
      await onAdjusted();
    } catch (err) {
      // 422=调整后余额为负等校验失败，展示后端人话文案
      setAdjustError(err instanceof ApiError ? err.message : t('toast.actionFailedMsg'));
    } finally {
      setAdjusting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] animate-in zoom-in duration-200">
        <div className="bg-slate-900 text-white p-4 flex justify-between items-center shrink-0">
          <h3 className="font-bold text-lg flex items-center gap-2"><Coins size={20} /> {t('coinLogs.title')}</h3>
          <button onClick={onClose}><X size={20} /></button>
        </div>

        <div className="p-5 space-y-5 overflow-y-auto flex-1">
          {/* 筛选：按孩子（多孩子家庭才有意义，单孩子也不影响） */}
          <div className="flex items-center gap-3">
            <label className="text-sm font-bold text-slate-700 shrink-0">{t('coinLogs.filterChild')}</label>
            <select
              value={childFilter}
              onChange={(e) => { setChildFilter(e.target.value); setPage(1); }}
              className="flex-1 border border-slate-200 rounded-lg p-2 text-sm"
            >
              <option value="">{t('coinLogs.filterAll')}</option>
              {adventurers.map(a => (
                <option key={a.child_id} value={a.child_id ?? ''}>{a.name}</option>
              ))}
            </select>
          </div>

          {/* 人工调整（父母） */}
          <div className="bg-blue-50 p-4 rounded-xl border border-blue-100 space-y-3">
            <label className="block text-sm font-bold text-blue-900">{t('coinLogs.adjustTitle')}</label>
            <div className="flex flex-wrap gap-2">
              <select
                value={adjustChild}
                onChange={(e) => setAdjustChild(e.target.value)}
                className="flex-1 min-w-[120px] border border-blue-200 rounded-lg p-2 text-sm bg-white"
              >
                {adventurers.map(a => (
                  <option key={a.child_id} value={a.child_id ?? ''}>{a.name}</option>
                ))}
              </select>
              <input
                type="number"
                value={adjustAmount}
                onChange={(e) => setAdjustAmount(e.target.value)}
                placeholder={t('coinLogs.adjustAmountPlaceholder')}
                className="w-32 border border-blue-200 rounded-lg p-2 text-sm font-bold"
              />
              <input
                type="text"
                value={adjustNote}
                onChange={(e) => setAdjustNote(e.target.value)}
                placeholder={t('coinLogs.adjustNotePlaceholder')}
                className="flex-1 min-w-[140px] border border-blue-200 rounded-lg p-2 text-sm"
              />
              <button
                onClick={handleAdjust}
                disabled={adjusting || !adjustChild}
                className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-blue-700 disabled:opacity-50 shrink-0"
              >
                {adjusting ? t('common.loading') : t('coinLogs.adjustSubmit')}
              </button>
            </div>
            {adjustError && <p className="text-xs text-red-600 font-bold">{adjustError}</p>}
          </div>

          {/* 流水列表 */}
          {loading ? (
            <div className="text-center py-10 text-slate-400 font-bold animate-pulse">{t('common.loading')}</div>
          ) : loadError ? (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-center">
              <p className="text-red-600 font-bold text-sm">{loadError}</p>
              <button onClick={() => loadLogs(page, childFilter)} className="mt-2 text-sm text-red-700 font-bold hover:underline">
                {t('parent.retry')}
              </button>
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-10 bg-slate-50 rounded-xl border-2 border-dashed border-slate-300">
              <Wallet className="mx-auto text-slate-300 mb-3" size={40} />
              <p className="text-slate-500 font-bold text-sm">{t('coinLogs.emptyTitle')}</p>
              <p className="text-slate-400 text-xs mt-1">{t('coinLogs.emptyHint')}</p>
            </div>
          ) : (
            <div className="space-y-2">
              {items.map(tx => (
                <div key={tx.id} className="flex items-center justify-between gap-3 bg-slate-50 border border-slate-100 rounded-lg p-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={`p-2 rounded-full shrink-0 ${tx.amount >= 0 ? 'bg-green-100 text-green-600' : 'bg-red-100 text-red-500'}`}>
                      {tx.amount >= 0 ? <ArrowDownCircle size={18} /> : <ArrowUpCircle size={18} />}
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm font-bold text-slate-700">
                        {t(`coinLogType.${tx.type}`)} · {childName(tx.child_id)}
                      </div>
                      <div className="text-xs text-slate-400 truncate">
                        {new Date(tx.created_at).toLocaleString()}{tx.note ? ` · ${tx.note}` : ''}
                      </div>
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className={`text-sm font-bold ${tx.amount >= 0 ? 'text-green-600' : 'text-red-500'}`}>
                      {tx.amount >= 0 ? '+' : ''}{tx.amount}
                    </div>
                    <div className="text-xs text-slate-400">{t('coinLogs.balanceAfter')}: {tx.balance_after}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 分页 */}
        <div className="p-4 bg-slate-50 border-t flex items-center justify-between shrink-0">
          <span className="text-xs text-slate-500 font-bold">
            {t('coinLogs.totalCount', { total })} · {t('child.pageOf', { current: page, total: totalPages })}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1 || loading}
              className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm font-bold text-slate-600 hover:bg-slate-100 disabled:opacity-40 flex items-center gap-1"
            >
              <ChevronLeft size={14} /> {t('child.prevPage')}
            </button>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages || loading}
              className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm font-bold text-slate-600 hover:bg-slate-100 disabled:opacity-40 flex items-center gap-1"
            >
              {t('child.nextPage')} <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CoinLogsModal;
