"use client";

export default function DealHeader({ deal }) {
  const totalAmount = deal.deal?.total_amount || 0;
  const paidAmount = deal.deal?.paid_amount || 0;
  const remaining = totalAmount - paidAmount;
  const paidPercent = totalAmount > 0 ? Math.round((paidAmount / totalAmount) * 100) : 0;

  return (
    <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700 rounded-xl p-6">
      <div className="mb-4">
        <h2 className="text-xl font-bold text-white">{deal.deal?.title || `Сделка #${deal.deal?.contract_number || "—"}`}</h2>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div>
          <p className="text-sm text-slate-400 mb-2">ID сделки</p>
          <p className="text-lg font-semibold text-white">#{deal.deal?.contract_number || "—"}</p>
          {deal.deal?.email && (
            <p className="text-sm text-slate-400 mt-1">{deal.deal.email}</p>
          )}
        </div>
        <div>
          <p className="text-sm text-slate-400 mb-2">Общая сумма</p>
          <p className="text-lg font-semibold text-white">
            {totalAmount.toLocaleString('ru-RU')} ₽
          </p>
        </div>
        <div>
          <p className="text-sm text-slate-400 mb-2">Оплачено</p>
          <p className="text-2xl font-bold text-emerald-400">
            {paidAmount.toLocaleString('ru-RU')} ₽
          </p>
          <p className="text-xs text-slate-500 mt-1">Остаток: {remaining.toLocaleString('ru-RU')} ₽</p>
          {deal.payments && (
            <p className="text-xs text-slate-400 mt-2">
              Оплачено: {deal.payments.filter(p => p.status === "paid").length} из {deal.payments.length} месяцев
            </p>
          )}
        </div>
        <div>
          <p className="text-sm text-slate-400 mb-2">Прогресс оплаты</p>
          <div className="flex items-center gap-3 mb-2">
            <div className="flex-1 bg-slate-700 rounded-full h-4 overflow-hidden shadow-inner">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  paidPercent >= 100 ? 'bg-emerald-500' : paidPercent > 50 ? 'bg-blue-500' : 'bg-purple-500'
                }`}
                style={{ width: `${Math.min(paidPercent, 100)}%` }}
              />
            </div>
            <span className={`text-lg font-bold min-w-[50px] text-right ${
              paidPercent >= 100 ? 'text-emerald-400' : paidPercent > 50 ? 'text-blue-400' : 'text-purple-400'
            }`}>
              {paidPercent}%
            </span>
          </div>
          <p className="text-xs text-slate-500">
            Срок: {deal.deal?.term_months || 0} мес.
          </p>
        </div>
      </div>
    </div>
  );
}

