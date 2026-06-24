"use client";

import { useParams, useRouter } from "next/navigation";
import Header from "@/components/layout/Header";
import Link from "next/link";

// Захардкоженные данные для демо-сделки
const DEMO_DEAL_DATA = {
  DEAL_001: {
    id: "DEAL_001",
    contract: "DEAL_001",
    client_name: "Иванов Иван Иванович",
    email: "ivanov@example.com",
    phone: "+7 (999) 123-45-67",
    total_amount: 300000,
    paid_amount: 100000,
    rest_amount: 200000,
    term_months: 6,
    status: "В процессе",
    progress: 33,
    created_at: "2025-01-15",
    payments: [
      {
        month: "Январь 2026",
        date: "10.01.2026",
        amount: 50000,
        status: "paid"
      },
      {
        month: "Февраль 2026",
        date: "10.02.2026",
        amount: 50000,
        status: "paid"
      },
      {
        month: "Март 2026",
        date: "10.03.2026",
        amount: 50000,
        status: "pending"
      },
      {
        month: "Апрель 2026",
        date: "10.04.2026",
        amount: 50000,
        status: "pending"
      },
      {
        month: "Май 2026",
        date: "10.05.2026",
        amount: 50000,
        status: "pending"
      },
      {
        month: "Июнь 2026",
        date: "10.06.2026",
        amount: 50000,
        status: "pending"
      }
    ],
    payment_logs: [
      {
        id: 1,
        amount: 50000,
        status: "paid",
        source: "yookassa",
        payment_id: "payment_001_jan",
        created_at: "2026-01-10T10:30:00Z"
      },
      {
        id: 2,
        amount: 50000,
        status: "paid",
        source: "yookassa",
        payment_id: "payment_002_feb",
        created_at: "2026-02-10T11:15:00Z"
      }
    ]
  },
  DEAL_002: {
    id: "DEAL_002",
    contract: "DEAL_002",
    client_name: "Петрова Мария Сергеевна",
    email: "petrova@example.com",
    phone: "+7 (999) 234-56-78",
    total_amount: 500000,
    paid_amount: 250000,
    rest_amount: 250000,
    term_months: 10,
    status: "В процессе",
    progress: 50,
    created_at: "2025-02-01",
    payments: Array.from({ length: 10 }, (_, i) => ({
      month: `Месяц ${i + 1}`,
      date: `10.${String(i + 1).padStart(2, '0')}.2026`,
      amount: 50000,
      status: i < 5 ? "paid" : "pending"
    })),
    payment_logs: Array.from({ length: 5 }, (_, i) => ({
      id: i + 1,
      amount: 50000,
      status: "paid",
      source: "yookassa",
      payment_id: `payment_${i + 1}`,
      created_at: `2026-${String(i + 1).padStart(2, '0')}-10T10:00:00Z`
    }))
  }
};

export default function AdminDealDemoPage() {
  const params = useParams();
  const router = useRouter();
  const dealId = params.id;
  const deal = DEMO_DEAL_DATA[dealId];

  if (!deal) {
    return (
      <>
        <Header />
        <main className="p-6 bg-dashboard-bg min-h-screen">
          <div className="max-w-4xl mx-auto">
            <div className="bg-dashboard-card border border-slate-700/50 rounded-xl p-12 text-center">
              <div className="text-5xl mb-4">📋</div>
              <h3 className="text-xl font-semibold text-white mb-2">Сделка не найдена</h3>
              <p className="text-dashboard-text-muted mb-6">Сделка с ID {dealId} не существует</p>
              <Link
                href="/admin/demo"
                className="inline-block px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors"
              >
                Вернуться к списку
              </Link>
            </div>
          </div>
        </main>
      </>
    );
  }

  const paidCount = deal.payments.filter(p => p.status === "paid").length;
  const totalCount = deal.payments.length;

  return (
    <>
      <Header />
      <main className="p-4 sm:p-6 lg:p-8 bg-dashboard-bg min-h-screen">
        <div className="max-w-7xl mx-auto space-y-6">
          {/* Навигация назад */}
          <div>
            <Link
              href="/admin/demo"
              className="inline-flex items-center gap-2 text-dashboard-text-muted hover:text-white transition-colors"
            >
              ← Назад к списку сделок
            </Link>
          </div>

          {/* Заголовок */}
          <div className="mb-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h1 className="text-3xl font-bold text-white mb-2">Сделка {deal.contract}</h1>
                <p className="text-dashboard-text-muted">Детальная информация о рассрочке</p>
              </div>
              <div className="px-4 py-2 bg-purple-500/10 border border-purple-500/30 rounded-lg text-sm text-purple-300">
                🎨 Демо-режим
              </div>
            </div>
          </div>

          {/* Информация о клиенте и сделке */}
          <div className="bg-dashboard-card border border-slate-700/50 rounded-xl p-6 backdrop-blur-sm">
            <h2 className="text-xl font-semibold text-white mb-4">Информация о сделке</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <div>
                <p className="text-sm text-dashboard-text-muted mb-1">Клиент</p>
                <p className="text-lg font-medium text-white">{deal.client_name}</p>
                <p className="text-sm text-dashboard-text-muted mt-1">{deal.email}</p>
                <p className="text-sm text-dashboard-text-muted">{deal.phone}</p>
              </div>
              <div>
                <p className="text-sm text-dashboard-text-muted mb-1">Общая сумма</p>
                <p className="text-lg font-medium text-white">{deal.total_amount.toLocaleString('ru-RU')} ₽</p>
              </div>
              <div>
                <p className="text-sm text-dashboard-text-muted mb-1">Оплачено</p>
                <p className="text-lg font-medium text-green-400">{deal.paid_amount.toLocaleString('ru-RU')} ₽</p>
                <p className="text-xs text-dashboard-text-muted mt-1">Остаток: {deal.rest_amount.toLocaleString('ru-RU')} ₽</p>
              </div>
              <div>
                <p className="text-sm text-dashboard-text-muted mb-1">Срок</p>
                <p className="text-lg font-medium text-white">{deal.term_months} мес.</p>
                <p className="text-xs text-dashboard-text-muted mt-1">Прогресс: {deal.progress}%</p>
              </div>
            </div>

            {/* Прогресс бар */}
            <div className="mt-6 pt-6 border-t border-slate-700/50">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-dashboard-text-muted">Прогресс оплаты</span>
                <span className="text-sm font-medium text-white">
                  {paidCount} из {totalCount} платежей
                </span>
              </div>
              <div className="h-2 bg-slate-700/50 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-gradient-to-r from-purple-500 to-purple-600 transition-all"
                  style={{ width: `${deal.progress}%` }}
                />
              </div>
            </div>
          </div>

          {/* График платежей */}
          <div className="bg-dashboard-card border border-slate-700/50 rounded-xl p-6 backdrop-blur-sm">
            <h2 className="text-xl font-semibold text-white mb-4">График платежей</h2>
            <div className="overflow-x-auto light-scrollbar">
              <table className="w-full">
                <thead className="bg-slate-800/50 border-b border-slate-700/50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-dashboard-text-muted uppercase">Месяц</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-dashboard-text-muted uppercase">Дата</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-dashboard-text-muted uppercase">Сумма</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-dashboard-text-muted uppercase">Статус</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/50">
                  {deal.payments.map((payment, index) => {
                    const isPaid = payment.status === "paid";
                    return (
                      <tr 
                        key={index}
                        className={isPaid ? "opacity-60" : "hover:bg-slate-800/30"}
                      >
                        <td className="px-4 py-3">
                          <span className={isPaid ? "line-through text-slate-500" : "text-white"}>
                            {payment.month}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-dashboard-text-muted">
                          <span className={isPaid ? "line-through" : ""}>
                            {payment.date}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-medium text-white">
                          <span className={isPaid ? "line-through text-slate-500" : ""}>
                            {payment.amount.toLocaleString('ru-RU')} ₽
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                            isPaid
                              ? "bg-green-500/20 text-green-400"
                              : "bg-yellow-500/20 text-yellow-400"
                          }`}>
                            {isPaid ? "Оплачено" : "К оплате"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* История платежей */}
          <div className="bg-dashboard-card border border-slate-700/50 rounded-xl p-6 backdrop-blur-sm">
            <h2 className="text-xl font-semibold text-white mb-4">История оплат</h2>
            {deal.payment_logs && deal.payment_logs.length > 0 ? (
              <div className="overflow-x-auto light-scrollbar">
                <table className="w-full">
                  <thead className="bg-slate-800/50 border-b border-slate-700/50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-dashboard-text-muted uppercase">Дата</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-dashboard-text-muted uppercase">Сумма</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-dashboard-text-muted uppercase">Статус</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-dashboard-text-muted uppercase">Источник</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-dashboard-text-muted uppercase">Payment ID</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/50">
                    {deal.payment_logs.map((log) => (
                      <tr key={log.id} className="hover:bg-slate-800/30">
                        <td className="px-4 py-3 text-dashboard-text-muted">
                          {new Date(log.created_at).toLocaleString('ru-RU')}
                        </td>
                        <td className="px-4 py-3 font-medium text-white">
                          {log.amount.toLocaleString('ru-RU')} ₽
                        </td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                            log.status === "paid" 
                              ? "bg-green-500/20 text-green-400" 
                              : log.status === "pending"
                              ? "bg-yellow-500/20 text-yellow-400"
                              : "bg-red-500/20 text-red-400"
                          }`}>
                            {log.status === "paid" ? "Оплачено" : log.status === "pending" ? "В обработке" : "Ошибка"}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-dashboard-text-muted">{log.source}</td>
                        <td className="px-4 py-3 text-xs text-dashboard-text-muted font-mono">
                          {log.payment_id.substring(0, 12)}...
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-8 text-dashboard-text-muted">
                История платежей пуста
              </div>
            )}
          </div>
        </div>
      </main>
    </>
  );
}

