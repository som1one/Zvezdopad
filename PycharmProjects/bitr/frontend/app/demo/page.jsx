"use client";

import { useState } from "react";
import dynamicImport from "next/dynamic";
import Header from "@/components/layout/Header";
import SummaryCards from "@/components/installment/SummaryCards";
import PaymentScheduleCard from "@/components/installment/PaymentScheduleCard";
import DemoPaymentModal from "@/components/payments/DemoPaymentModal";

// Импортируем напрямую - компонент сам обрабатывает SSR
import SimpleProgressChart from "@/components/installment/SimpleProgressChart";

export const dynamic = 'force-dynamic';

// Захардкоженные данные для демонстрации дизайна
const DEMO_DEAL = {
  total: 300000,
  paid: 100000,
  rest: 200000,
  term: 6,
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
  ]
};

export default function DemoPage() {
  const [payAmount, setPayAmount] = useState(null);
  const deal = DEMO_DEAL;
  const hasPayments = deal.payments && deal.payments.length > 0;
  const allPaid = deal.payments?.every(p => p.status === "paid");

  return (
    <>
      <Header />
      <main className="p-4 sm:p-6 lg:p-8 bg-dashboard-bg min-h-screen pb-24 md:pb-8">
        <div className="max-w-7xl mx-auto space-y-6">
          {/* Заголовок страницы */}
          <div className="mb-8">
            <h2 className="text-3xl font-bold text-white mb-2">Детали рассрочки</h2>
            <p className="text-dashboard-text-muted">Обзор платежей и прогресс погашения</p>
            <div className="mt-4 px-4 py-2 bg-purple-500/10 border border-purple-500/30 rounded-lg text-sm text-purple-300">
              🎨 Демо-страница с захардкоженными данными для демонстрации дизайна
            </div>
          </div>

          {/* Карточки с метриками */}
          <SummaryCards deal={deal} />

          {/* Основной контент - две колонки */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* График прогресса */}
            {hasPayments && (
              <div className="lg:col-span-2">
                <SimpleProgressChart payments={deal.payments} />
              </div>
            )}

            {/* График платежей */}
            {hasPayments ? (
              <div className="lg:col-span-2">
                <PaymentScheduleCard 
                  payments={deal.payments} 
                  onPay={(payment) => {
                    if (payment.status !== "paid") {
                      setPayAmount(payment.amount);
                    }
                  }}
                />
              </div>
            ) : (
              <div className="lg:col-span-2">
                <div className="bg-dashboard-card border border-slate-700/50 rounded-xl p-12 text-center">
                  <div className="text-5xl mb-4">📅</div>
                  <h3 className="text-xl font-semibold text-white mb-2">График платежей не создан</h3>
                  <p className="text-dashboard-text-muted">Обратитесь к администратору для настройки графика</p>
                </div>
              </div>
            )}
          </div>

          {/* Баннер о полной оплате */}
          {allPaid && hasPayments && (
            <div className="bg-gradient-to-r from-green-500/20 to-emerald-500/20 border border-green-500/30 rounded-xl p-6 text-center backdrop-blur-sm">
              <div className="text-5xl mb-4">🎉</div>
              <h3 className="text-2xl font-bold text-white mb-2">Рассрочка полностью оплачена!</h3>
              <p className="text-dashboard-text-muted">Все платежи успешно выполнены</p>
            </div>
          )}
        </div>
      </main>

      {/* Sticky CTA для мобильных */}
      {!allPaid && hasPayments && (
        <div className="fixed bottom-0 left-0 right-0 md:hidden bg-dashboard-card border-t border-slate-700/50 shadow-2xl p-4 z-50 backdrop-blur-sm">
          <button
            onClick={() => {
              const nextPayment = deal.payments.find(p => p.status === "pending");
              if (nextPayment) setPayAmount(nextPayment.amount);
            }}
            className="w-full py-4 bg-gradient-to-r from-purple-600 to-purple-700 hover:from-purple-700 hover:to-purple-800 text-white rounded-xl font-bold text-lg transition-all shadow-lg"
          >
            {(() => {
              const nextPayment = deal.payments.find(p => p.status === "pending");
              return nextPayment ? `Оплатить ${nextPayment.amount.toLocaleString('ru-RU')} ₽` : "Оплатить";
            })()}
          </button>
        </div>
      )}

      {/* Payment Modal */}
      {payAmount && (
        <DemoPaymentModal
          amount={payAmount}
          onClose={() => setPayAmount(null)}
        />
      )}
    </>
  );
}

