"use client";

import { useState, useEffect } from "react";
import { useInstallment } from "@/modules/installment/hooks";
import Header from "@/components/layout/Header";
import SummaryCards from "@/components/installment/SummaryCards";
import PaymentScheduleCard from "@/components/installment/PaymentScheduleCard";
import PaymentModal from "@/components/payments/PaymentModal";
import DealDetailsCard from "@/components/admin/DealDetailsCard";
import { Loader, ErrorState, EmptyState } from "@/components/ui/State";
import ErrorBoundary from "@/components/ui/ErrorBoundary";

export const dynamic = 'force-dynamic';

export default function InstallmentPage() {
  const { deal, loading, error, refetch } = useInstallment();
  const [payAmount, setPayAmount] = useState(null);
  const [clientError, setClientError] = useState(null);

  // Обработка клиентских ошибок
  useEffect(() => {
    const handleError = (event) => {
      console.error("Client-side error:", event.error);
      setClientError(event.error?.message || "Произошла ошибка при отображении страницы");
    };

    const handleUnhandledRejection = (event) => {
      console.error("Unhandled promise rejection:", event.reason);
      setClientError(event.reason?.message || "Произошла ошибка при загрузке данных");
    };

    window.addEventListener("error", handleError);
    window.addEventListener("unhandledrejection", handleUnhandledRejection);

    return () => {
      window.removeEventListener("error", handleError);
      window.removeEventListener("unhandledrejection", handleUnhandledRejection);
    };
  }, []);

  if (loading) {
    return (
      <>
        <Header />
        <main className="p-6 bg-dashboard-bg min-h-screen">
          <div className="flex items-center justify-center min-h-[60vh]">
            <div className="text-center">
              <div className="w-16 h-16 border-4 border-purple-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
              <p className="text-dashboard-text-muted">Загрузка данных о рассрочке...</p>
            </div>
          </div>
        </main>
      </>
    );
  }

  // Показываем клиентскую ошибку, если есть
  if (clientError) {
    return (
      <>
        <Header />
        <main className="p-6 bg-dashboard-bg min-h-screen">
          <div className="max-w-2xl mx-auto mt-12">
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-center">
              <div className="text-4xl mb-4">⚠️</div>
              <h3 className="text-xl font-semibold text-white mb-2">Ошибка приложения</h3>
              <p className="text-dashboard-text-muted mb-4">{clientError}</p>
              <div className="space-y-2">
                <button
                  onClick={() => {
                    setClientError(null);
                    window.location.reload();
                  }}
                  className="px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors mr-2"
                >
                  Перезагрузить страницу
                </button>
                <button
                  onClick={() => setClientError(null)}
                  className="px-6 py-2 bg-slate-600 hover:bg-slate-700 text-white rounded-lg font-semibold transition-colors"
                >
                  Закрыть
                </button>
              </div>
              <p className="text-xs text-dashboard-text-muted mt-4">
                Откройте консоль браузера (F12) для подробностей
              </p>
            </div>
          </div>
        </main>
      </>
    );
  }

  if (error) {
    // Проверяем, если ошибка связана с отсутствием рассрочки или авторизацией
    const isAuthError = error.includes("не найден") || error.includes("авторизация") || error.includes("401") || error.includes("403");
    const isNotFoundError = error.includes("404") || error.includes("не найдена");
    
    return (
      <>
        <Header />
        <main className="p-6 bg-dashboard-bg min-h-screen">
          <div className="max-w-2xl mx-auto mt-12">
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-center">
              <div className="text-4xl mb-4">⚠️</div>
              <h3 className="text-xl font-semibold text-white mb-2">
                {isAuthError ? "Требуется вход" : isNotFoundError ? "Рассрочка не найдена" : "Ошибка загрузки"}
              </h3>
              <p className="text-dashboard-text-muted mb-4">{error}</p>
              <div className="space-y-2">
                {isAuthError ? (
                  <a
                    href="/auth/login"
                    className="inline-block px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors mr-2"
                  >
                    Войти
                  </a>
                ) : (
                  <button
                    onClick={() => {
                      refetch();
                    }}
                    className="px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors mr-2"
                  >
                    Попробовать снова
                  </button>
                )}
                <button
                  onClick={() => window.location.href = "/"}
                  className="px-6 py-2 bg-slate-600 hover:bg-slate-700 text-white rounded-lg font-semibold transition-colors"
                >
                  На главную
                </button>
              </div>
            </div>
          </div>
        </main>
      </>
    );
  }

  if (!deal) {
    return (
      <>
        <Header />
        <main className="p-6 bg-dashboard-bg min-h-screen">
          <div className="max-w-2xl mx-auto mt-12">
            <div className="bg-dashboard-card border border-slate-700/50 rounded-xl p-6 text-center">
              <div className="text-4xl mb-4">📋</div>
              <h3 className="text-xl font-semibold text-white mb-2">Рассрочка не найдена</h3>
              <p className="text-dashboard-text-muted">Данные о рассрочке отсутствуют</p>
            </div>
          </div>
        </main>
      </>
    );
  }

  const hasPayments = deal.payments && deal.payments.length > 0;
  const allPaid = deal.payments?.every(p => p.status === "paid");

  return (
    <ErrorBoundary>
      <Header />
      <main className="p-4 sm:p-6 lg:p-8 bg-dashboard-bg min-h-screen pb-24 md:pb-8">
        <div className="max-w-7xl mx-auto space-y-6">
          {/* Заголовок страницы */}
          <div className="mb-8 flex flex-col md:flex-row md:items-end justify-between gap-4">
            <div>
              <h2 className="text-3xl font-bold text-white mb-2">
                {deal.title || deal.client_name || "Детали рассрочки"}
              </h2>
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
                {deal.object_location && (
                  <div className="flex items-center gap-2 text-dashboard-text-muted">
                    <span className="text-purple-400">📍</span>
                    <span>{deal.object_location}</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* В мобильной версии показываем информацию о проекте сразу после местоположения */}
          <div className="block lg:hidden">
            <DealDetailsCard deal={deal} />
          </div>

          {/* Карточки с метриками */}
          <SummaryCards deal={deal} />

          {/* Блок с полями проекта убран: данные есть в хедере и в правой карточке */}

          {/* Основной контент - две колонки */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              {/* График платежей */}
              {hasPayments ? (
                <PaymentScheduleCard 
                  payments={deal.payments} 
                  onPay={(payment) => {
                    if (payment.status !== "paid") {
                      const remaining = (typeof payment.remaining_in_month === "number")
                        ? payment.remaining_in_month
                        : 0;
                      setPayAmount(remaining > 0 ? remaining : payment.amount);
                    }
                  }}
                />
              ) : (
                <div className="bg-dashboard-card border border-slate-700/50 rounded-xl p-12 text-center">
                  <div className="text-5xl mb-4">📅</div>
                  <h3 className="text-xl font-semibold text-white mb-2">График платежей не создан</h3>
                  <p className="text-dashboard-text-muted">Обратитесь к администратору для настройки графика</p>
                </div>
              )}
            </div>
            
            <div className="lg:col-span-1 hidden lg:block">
              <DealDetailsCard deal={deal} />
            </div>
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
              const nextPayment = deal.payments.find(p => p.status !== "paid");
              if (nextPayment) {
                const remaining = (typeof nextPayment.remaining_in_month === "number")
                  ? nextPayment.remaining_in_month
                  : 0;
                setPayAmount(remaining > 0 ? remaining : nextPayment.amount);
              }
            }}
            className="w-full py-4 bg-gradient-to-r from-purple-600 to-purple-700 hover:from-purple-700 hover:to-purple-800 text-white rounded-xl font-bold text-lg transition-all shadow-lg"
          >
            {(() => {
              const nextPayment = deal.payments.find(p => p.status !== "paid");
              if (!nextPayment) return "Оплатить";
              const remaining = (typeof nextPayment.remaining_in_month === "number") ? nextPayment.remaining_in_month : 0;
              const toPay = remaining > 0 ? remaining : nextPayment.amount;
              return `Оплатить ${toPay.toLocaleString('ru-RU')} ₽`;
            })()}
          </button>
        </div>
      )}

      {/* Payment Modal */}
      {payAmount && (
        <PaymentModal
          amount={payAmount}
          onClose={() => setPayAmount(null)}
        />
      )}
    </ErrorBoundary>
  );
}
