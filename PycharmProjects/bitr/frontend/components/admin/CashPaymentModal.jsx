"use client";

import { useEffect, useMemo, useState } from "react";
import { getDeal, recordCashPayment } from "@/modules/admin/deals/api";

export default function CashPaymentModal({ dealId, onClose, onSuccess }) {
  const [deal, setDeal] = useState(null);
  const [selected, setSelected] = useState({}); // index -> amount
  const [comment, setComment] = useState("");
  const [paymentDate, setPaymentDate] = useState(() => {
    // Устанавливаем сегодняшнюю дату по умолчанию
    const today = new Date();
    return today.toISOString().split('T')[0];
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [loadingDeal, setLoadingDeal] = useState(true);

  const payments = useMemo(() => (Array.isArray(deal?.payments) ? deal.payments : []), [deal]);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoadingDeal(true);
      setError(null);
      try {
        const data = await getDeal(dealId);
        if (mounted) {
          setDeal(data);
          // предвыставим суммы для "частично" по остаткам (если есть)
          const init = {};
          (Array.isArray(data?.payments) ? data.payments : []).forEach((p) => {
            const idx = Number(p?.index ?? p?.month_index);
            if (!Number.isFinite(idx)) return;
            const amount = Number(p?.amount) || 0;
            const paidInMonth = Number(p?.paid_in_month ?? p?.paid_amount_for_month) || 0;
            const remainingInMonth = Math.max(0, amount - paidInMonth);
            if (p?.status === "partial" && remainingInMonth > 0) {
              init[idx] = remainingInMonth;
            }
          });
          setSelected(init);
        }
      } catch (e) {
        if (mounted) setError(e.message || "Не удалось загрузить график платежей");
      } finally {
        if (mounted) setLoadingDeal(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, [dealId]);

  const pendingMonths = useMemo(() => {
    return payments.filter((p) => p && p.status !== "paid");
  }, [payments]);

  const totalSelected = useMemo(() => {
    return Object.values(selected).reduce((sum, v) => sum + (Number(v) || 0), 0);
  }, [selected]);

  const remainingDeal = useMemo(() => {
    const total = Number(deal?.deal?.total_amount) || 0;
    const paid = Number(deal?.deal?.paid_amount) || 0;
    return Math.max(0, total - paid);
  }, [deal]);

  const toggleMonth = (p) => {
    const idx = Number(p?.index ?? p?.month_index);
    if (!Number.isFinite(idx)) return;
    setSelected((prev) => {
      const next = { ...prev };
      if (next[idx] != null) {
        delete next[idx];
      } else {
        const amount = Number(p?.amount) || 0;
        const paidInMonth = Number(p?.paid_in_month ?? p?.paid_amount_for_month) || 0;
        const remainingInMonth = Math.max(0, amount - paidInMonth);
        next[idx] = remainingInMonth || amount || 0;
      }
      return next;
    });
  };

  const setAmountForMonth = (idx, value) => {
    const n = Number(String(value).replace(/\s/g, "").replace(/[^\d]/g, "")) || 0;
    setSelected((prev) => ({ ...prev, [idx]: n }));
  };

  const formatAmount = (value) => {
    const numbers = String(value ?? "").replace(/\D/g, "");
    return numbers.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    const allocations = Object.entries(selected)
      .map(([idx, amt]) => ({ month_index: Number(idx), amount: Number(amt) || 0 }))
      .filter((a) => a.amount > 0);

    if (allocations.length === 0) {
      setError("Выберите месяц(ы) и укажите сумму");
      return;
    }

    if (totalSelected > remainingDeal) {
      setError(`Сумма (${totalSelected.toLocaleString("ru-RU")} ₽) превышает остаток (${remainingDeal.toLocaleString("ru-RU")} ₽)`);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await recordCashPayment(dealId, allocations, comment, paymentDate);
      onSuccess?.();
      onClose();
    } catch (err) {
      setError(err.message || "Ошибка при записи оплаты");
      console.error("cash_payment_error", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl">
        <h2 className="text-xl font-semibold mb-2 text-white">Оплата наличными</h2>
        <p className="text-sm text-slate-400 mb-4">Выберите месяцы и укажите суммы (можно частично)</p>
        
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="bg-slate-900/30 border border-slate-700/50 rounded-lg p-4">
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-400">Остаток по сделке</span>
              <span className="text-white font-semibold">{remainingDeal.toLocaleString("ru-RU")} ₽</span>
            </div>
            <div className="flex items-center justify-between text-sm mt-2">
              <span className="text-slate-400">Итого к записи</span>
              <span className="text-purple-300 font-bold">{totalSelected.toLocaleString("ru-RU")} ₽</span>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              За какие месяцы
            </label>
            <div className="max-h-64 overflow-y-auto space-y-2 pr-1 custom-scrollbar">
              {loadingDeal ? (
                <div className="text-slate-400 text-sm">Загрузка графика...</div>
              ) : pendingMonths.length === 0 ? (
                <div className="text-slate-400 text-sm">Нет месяцев к оплате (всё оплачено или график не создан)</div>
              ) : (
                pendingMonths.map((p) => {
                  const idx = Number(p?.index ?? p?.month_index);
                  const checked = Number.isFinite(idx) ? selected[idx] != null : false;
                  const amount = Number(p?.amount) || 0;
                  const paidInMonth = Number(p?.paid_in_month ?? p?.paid_amount_for_month) || 0;
                  const remainingInMonth = Math.max(0, amount - paidInMonth);
                  const defaultDue = remainingInMonth || amount || 0;
                  return (
                    <div key={idx} className={`border rounded-lg p-3 ${checked ? "border-purple-500/40 bg-purple-500/10" : "border-slate-700/50 bg-slate-900/20"}`}>
                      <div className="flex items-start justify-between gap-3">
                        <label className="flex items-start gap-3 cursor-pointer">
                          <input
                            type="checkbox"
                            className="mt-1"
                            checked={checked}
                            onChange={() => toggleMonth(p)}
                            disabled={loading}
                          />
                          <div>
                            <div className="text-white font-medium">{p.month}</div>
                            <div className="text-xs text-slate-400">
                              План: {Number(p.amount || 0).toLocaleString("ru-RU")} ₽
                              {paidInMonth ? ` · Уже внесено: ${paidInMonth.toLocaleString("ru-RU")} ₽` : ""}
                            </div>
                          </div>
                        </label>
                        <div className="min-w-[140px]">
                          <div className="text-xs text-slate-400 mb-1">Сумма</div>
                          <input
                            type="text"
                            value={formatAmount(checked ? selected[idx] : "")}
                            onChange={(e) => setAmountForMonth(idx, e.target.value)}
                            placeholder={defaultDue.toLocaleString("ru-RU")}
                            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
                            disabled={!checked || loading}
                          />
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Дата оплаты
            </label>
            <input
              type="date"
              value={paymentDate}
              onChange={(e) => setPaymentDate(e.target.value)}
              className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
              disabled={loading}
            />
            <p className="text-xs text-slate-400 mt-1">Выберите фактическую дату оплаты</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Комментарий (необязательно)
            </label>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Примечание к оплате..."
              rows={3}
              className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
              disabled={loading}
            />
          </div>

          {error && (
            <div className="bg-red-500/20 border border-red-500/30 text-red-400 px-4 py-3 rounded-lg">
              {error}
            </div>
          )}

          <div className="flex gap-3 justify-end">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="px-4 py-2 border border-slate-600 text-slate-300 rounded-lg hover:bg-slate-700 disabled:opacity-50 transition-colors"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={loading || loadingDeal || totalSelected <= 0}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 flex items-center gap-2 transition-colors"
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  Сохранение...
                </>
              ) : (
                "Записать оплату"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

