"use client";

export default function AdminPaymentsTable({ payments }) {
  if (!payments || payments.length === 0) {
    return (
      <div className="p-8 text-center text-slate-400">
        График платежей не создан
      </div>
    );
  }

  return (
    <div className="overflow-hidden">
      <div className="overflow-x-auto custom-scrollbar">
        <table className="w-full text-sm">
          <thead className="bg-slate-900/50 border-b border-slate-700">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-bold uppercase text-slate-400 tracking-wider">Месяц</th>
              <th className="px-6 py-3 text-left text-xs font-bold uppercase text-slate-400 tracking-wider">Дата</th>
              <th className="px-6 py-3 text-left text-xs font-bold uppercase text-slate-400 tracking-wider">Сумма</th>
              <th className="px-6 py-3 text-left text-xs font-bold uppercase text-slate-400 tracking-wider">Статус</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/50">
            {payments.map((p, index) => (
              <tr 
                key={index} 
                className={`hover:bg-slate-800/30 transition-colors ${
                  p.status === "paid" ? "opacity-75" : ""
                }`}
              >
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className={`text-white ${p.status === "paid" ? "line-through text-slate-500" : ""}`}>
                    {p.month}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className={`text-slate-300 ${p.status === "paid" ? "line-through text-slate-500" : ""}`}>
                    {p.date}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className={`font-semibold ${p.status === "paid" ? "line-through text-slate-500" : "text-white"}`}>
                    {p.amount.toLocaleString('ru-RU')} ₽
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className={`px-3 py-1 text-xs font-medium rounded-full border ${
                    p.status === "paid" 
                      ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" 
                      : p.status === "partial"
                      ? "bg-yellow-500/20 text-yellow-400 border-yellow-500/30"
                      : "bg-blue-500/20 text-blue-400 border-blue-500/30"
                  }`}>
                    {p.status === "paid" ? "Оплачено" : p.status === "partial" ? "Частично" : "К оплате"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

