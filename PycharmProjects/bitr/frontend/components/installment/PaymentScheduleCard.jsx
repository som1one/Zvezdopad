"use client";

export default function PaymentScheduleCard({ payments, onPay }) {
  const nextPayment = payments.find(p => p.status !== "paid");
  const paidCount = payments.filter(p => p.status === "paid").length;
  const totalCount = payments.length;

  // Прогресс считаем по суммам (чтобы partial корректно отражался)
  const totalSum = payments.reduce((s, p) => s + (Number(p?.amount) || 0), 0);
  const paidSum = payments.reduce((s, p) => {
    const amt = Number(p?.amount) || 0;
    const remaining = p?.remaining_in_month;
    const paidInMonth = p?.paid_in_month;
    if (typeof remaining === "number") return s + Math.max(0, amt - remaining);
    if (typeof paidInMonth === "number") return s + Math.min(amt, Math.max(0, paidInMonth));
    return s + (p?.status === "paid" ? amt : 0);
  }, 0);
  const progress = totalSum > 0 ? (paidSum / totalSum) * 100 : 0;

  const handlePayClick = (payment) => {
    if (payment.status !== "paid") {
      if (onPay) onPay(payment);
    }
  };

  return (
    <div className="bg-dashboard-card rounded-xl border border-slate-700/50 p-6 backdrop-blur-sm">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-xl font-semibold text-white mb-1">График платежей</h3>
          <p className="text-sm text-dashboard-text-muted">
            {paidCount} из {totalCount} платежей выполнено
          </p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold text-white">{Math.round(progress)}%</div>
          <div className="text-xs text-dashboard-text-muted">Прогресс</div>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="mb-6">
        <div className="h-2 bg-slate-700/50 rounded-full overflow-hidden">
          <div 
            className="h-full bg-gradient-to-r from-purple-500 to-purple-600 transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Payments List */}
      <div className="space-y-3 max-h-96 overflow-y-auto custom-scrollbar">
        {payments.map((payment, index) => {
          const isPaid = payment.status === "paid";
          const isNext = !isPaid && payment === nextPayment;
          const isPartial = payment.status === "partial";
          const remaining = Number(payment.remaining_in_month) || 0;
          
          return (
            <div
              key={index}
              className={`p-3 sm:p-4 rounded-lg border transition-all ${
                isPaid
                  ? "bg-slate-800/30 border-slate-700/30 opacity-60"
                  : isNext
                  ? "bg-purple-500/10 border-purple-500/30 ring-2 ring-purple-500/20"
                  : "bg-slate-800/50 border-slate-700/50 hover:bg-slate-800/70"
              }`}
            >
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 sm:gap-3">
                    <div className={`flex-shrink-0 w-8 h-8 sm:w-10 sm:h-10 rounded-lg flex items-center justify-center font-bold text-sm sm:text-base ${
                      isPaid
                        ? "bg-green-500/20 text-green-400"
                        : isNext
                        ? "bg-purple-500/20 text-purple-400"
                        : "bg-slate-700 text-slate-400"
                    }`}>
                      {isPaid ? "✓" : index + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`font-medium text-sm sm:text-base truncate ${
                          isPaid ? "line-through text-slate-500" : "text-white"
                        }`}>
                          {payment.month}
                        </span>
                        {isNext && (
                          <span className="px-2 py-0.5 text-xs font-semibold bg-purple-500/20 text-purple-400 rounded whitespace-nowrap">
                            Следующий
                          </span>
                        )}
                      </div>
                      <p className={`text-xs sm:text-sm mt-1 ${
                        isPaid ? "line-through text-slate-600" : "text-dashboard-text-muted"
                      }`}>
                        {payment.date}
                      </p>
                    </div>
                  </div>
                </div>
                <div className="flex sm:flex-col sm:text-right items-center sm:items-end justify-between sm:justify-start gap-2 sm:gap-1 sm:ml-4">
                  <div className={`text-base sm:text-lg font-bold ${
                    isPaid ? "line-through text-slate-600" : "text-white"
                  }`}>
                    {payment.amount.toLocaleString('ru-RU')} ₽
                  </div>
                  <div className="flex items-center gap-2">
                    {(isPaid || isPartial) && (
                      <span className={`px-2 py-1 text-xs font-medium rounded-full whitespace-nowrap ${
                        isPaid
                          ? "bg-green-500/20 text-green-400"
                          : "bg-yellow-500/20 text-yellow-400"
                      }`}>
                        {isPaid ? "Оплачено" : "Частично"}
                      </span>
                    )}
                    {!isPaid && (
                      <button
                        onClick={() => handlePayClick(payment)}
                        className="px-3 sm:px-4 py-1.5 text-xs sm:text-sm font-semibold bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors whitespace-nowrap"
                      >
                        {isPartial && remaining > 0 ? "Доплатить" : "Оплатить"}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

