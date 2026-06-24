"use client";

import { useState } from "react";
import Link from "next/link";
import CashPaymentModal from "./CashPaymentModal";
import { Wallet, ArrowUpRight } from "lucide-react";

export default function DealsTable({ deals, onRefresh }) {
  const [selectedDeal, setSelectedDeal] = useState(null);
  const getStatusBadge = (status, paidPercent) => {
    if (status === "not_configured") {
      return (
        <span className="px-3 py-1 text-xs font-medium rounded-full bg-slate-800 text-slate-300 border border-slate-600/60">
          Не настроено
        </span>
      );
    }
    // Определяем статус на основе процента оплаты, если статус не указан
    let actualStatus = status;
    if (paidPercent >= 100) {
      actualStatus = "paid";
    } else if (paidPercent > 0) {
      actualStatus = "active";
    } else {
      actualStatus = "pending";
    }

    const statusMap = {
      paid: { text: "Завершена", class: "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" },
      active: { text: "В процессе", class: "bg-blue-500/20 text-blue-400 border border-blue-500/30" },
      pending: { text: "Не оплачено", class: "bg-slate-700 text-slate-400 border border-slate-600" },
      overdue: { text: "Просрочена", class: "bg-red-500/20 text-red-400 border border-red-500/30" }
    };
    const statusInfo = statusMap[actualStatus] || statusMap.active;
    return (
      <span className={`px-3 py-1 text-xs font-medium rounded-full ${statusInfo.class}`}>
        {statusInfo.text}
      </span>
    );
  };

  const getProgressColor = (percent) => {
    if (percent >= 100) return "bg-emerald-500";
    if (percent >= 75) return "bg-green-500";
    if (percent >= 50) return "bg-blue-500";
    if (percent >= 25) return "bg-yellow-500";
    if (percent > 0) return "bg-orange-500";
    return "bg-purple-500";
  };

  const formatAmount = (amount) => {
    if (amount === 0) return <span className="text-slate-500">—</span>;
    return <span className="font-semibold text-white">{amount.toLocaleString('ru-RU')} ₽</span>;
  };

  return (
    <>
      <div className="overflow-hidden">
        <div className="overflow-x-auto custom-scrollbar">
          <table className="w-full text-sm">
            <thead className="bg-slate-900/50 border-b border-slate-700">
              <tr>
                <th className="px-6 py-4 text-left text-xs font-bold uppercase text-slate-400 tracking-wider">
                  КЛИЕНТ
                </th>
                <th className="px-6 py-4 text-left text-xs font-bold uppercase text-slate-400 tracking-wider">
                  СУММА
                </th>
                <th className="px-6 py-4 text-left text-xs font-bold uppercase text-slate-400 tracking-wider">
                  ОПЛАЧЕНО
                </th>
                <th className="px-6 py-4 text-left text-xs font-bold uppercase text-slate-400 tracking-wider">
                  ОСТАТОК
                </th>
                <th className="px-6 py-4 text-left text-xs font-bold uppercase text-slate-400 tracking-wider">
                  СРОК
                </th>
                <th className="px-6 py-4 text-left text-xs font-bold uppercase text-slate-400 tracking-wider">
                  ПРОГРЕСС
                </th>
                <th className="px-6 py-4 text-left text-xs font-bold uppercase text-slate-400 tracking-wider">
                  СТАТУС
                </th>
                <th className="px-6 py-4 text-left text-xs font-bold uppercase text-slate-400 tracking-wider">
                  ДЕЙСТВИЯ
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {deals.map((d, index) => {
                const totalAmount = d.total_amount || 0;
                const paidAmount = d.paid_amount || 0;
                const initialPayment = Number(d.initial_payment) || 0;

                const termMonths = Number(d.term_months) || 0;
                const hasSchedule = termMonths > 0;

                // Для сделок без графика (term=0) НЕ показываем сумму рассрочки "по графику",
                // чтобы не вводить в заблуждение (иначе это выглядит как общая сумма сделки).
                const rawInstallmentAmount = Math.max(0, totalAmount - initialPayment);
                const installmentAmount = hasSchedule ? rawInstallmentAmount : 0;
                const paidInstallment = hasSchedule
                  ? Math.min(rawInstallmentAmount, Math.max(0, paidAmount))
                  : 0;
                const remainingInstallment = hasSchedule ? Math.max(0, installmentAmount - paidInstallment) : 0;
                const paidPercent = installmentAmount > 0 ? Math.round((paidInstallment / installmentAmount) * 100) : 0;

                const isFullyPaid = remainingInstallment <= 0 && installmentAmount > 0;
                const hasInstallment = rawInstallmentAmount > 0;
                const displayStatus = hasSchedule ? d.status : "not_configured";

                return (
                  <tr 
                    key={d.deal_id} 
                    className="hover:bg-slate-800/30 transition-all duration-200 group border-b border-slate-700/30"
                  >
                    <td className="px-6 py-4">
                      <Link
                        href={`/admin/deals/${d.deal_id}`}
                        prefetch={false}
                        className="block text-white hover:text-purple-400 hover:underline font-medium transition-colors"
                      >
                        {d.title || "Без названия"}
                      </Link>
                      {d.email && (
                        <div className="text-xs text-slate-400 mt-1">
                          {d.email}
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="font-semibold text-white">
                        {formatAmount(installmentAmount)}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {paidInstallment > 0 ? (
                        <span className="font-bold text-base text-emerald-400">
                          {paidInstallment.toLocaleString('ru-RU')} ₽
                        </span>
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {remainingInstallment > 0 ? (
                        <span className="text-slate-400">
                          {remainingInstallment.toLocaleString('ru-RU')} ₽
                        </span>
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-slate-300 font-medium">
                      {d.term_months} мес.
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3 min-w-[140px]">
                        <div className="flex-1 bg-slate-700 rounded-full h-2.5 overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-500 ease-out ${getProgressColor(paidPercent)}`}
                            style={{ width: `${Math.min(paidPercent, 100)}%` }}
                          />
                        </div>
                        <span className={`text-sm font-bold min-w-[40px] text-right ${paidPercent >= 100 ? 'text-emerald-400' : paidPercent > 0 ? 'text-purple-400' : 'text-slate-500'}`}>
                          {paidPercent}%
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {getStatusBadge(displayStatus, paidPercent)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        <Link
                          href={`/admin/deals/${d.deal_id}`}
                          prefetch={false}
                          className="px-3 py-1.5 bg-slate-800/70 hover:bg-slate-700 text-white text-xs font-medium rounded-lg transition-colors flex items-center gap-1.5 border border-slate-600/60"
                        >
                          <ArrowUpRight className="w-3.5 h-3.5" />
                          Открыть
                        </Link>

                        <button
                          onClick={() => setSelectedDeal(d)}
                          disabled={isFullyPaid || !hasInstallment || !hasSchedule}
                          className="px-3 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:bg-slate-700 disabled:text-slate-400 disabled:cursor-not-allowed text-white text-xs font-medium rounded-lg transition-colors flex items-center gap-1.5"
                          title={
                            !hasInstallment
                              ? "Сначала задайте сумму рассрочки (общая сумма и первоначальный взнос)"
                              : !hasSchedule
                                ? "Сначала задайте срок (месяцы), чтобы появился график"
                                : isFullyPaid
                                  ? "Рассрочка уже оплачена"
                                  : "Записать оплату наличными"
                          }
                        >
                          <Wallet className="w-3.5 h-3.5" />
                          Наличный
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {selectedDeal && (
        <CashPaymentModal
          dealId={selectedDeal.deal_id}
          onClose={() => setSelectedDeal(null)}
          onSuccess={() => {
            setSelectedDeal(null);
            onRefresh?.();
          }}
        />
      )}
    </>
  );
}

