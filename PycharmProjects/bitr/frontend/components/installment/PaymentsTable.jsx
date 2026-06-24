"use client";

import { useState } from "react";
import PaymentModal from "@/components/payments/PaymentModal";

export default function PaymentsTable({ payments, onPay, loading = false }) {
  const showPayButton = !!onPay;
  const nextPaymentIndex = payments.findIndex(p => p.status === "pending");
  const [payAmount, setPayAmount] = useState(null);

  const handlePayClick = (payment) => {
    if (payment.status === "paid" || loading) return;
    setPayAmount(payment.amount);
  };

  const nextPayment = payments.find(p => p.status === "pending");

  return (
    <>
      {/* Desktop Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden hidden sm:block">
        <div className="overflow-x-auto light-scrollbar">
          <table className="w-full text-sm md:text-base">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 md:px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Месяц</th>
                <th className="px-4 md:px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Дата</th>
                <th className="px-4 md:px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Сумма</th>
                <th className="px-4 md:px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Статус</th>
                {showPayButton && (
                  <th className="px-4 md:px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Действие</th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {payments.map((p, index) => (
                <tr 
                  key={index} 
                  className={p.status === "paid" ? "bg-gray-50 opacity-60" : ""}
                >
                  <td className="px-4 md:px-6 py-4 whitespace-nowrap">
                    <span className={p.status === "paid" ? "line-through" : ""}>
                      {p.month}
                    </span>
                    {index === nextPaymentIndex && (
                      <span className="ml-2 px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded">
                        Следующий
                      </span>
                    )}
                  </td>
                  <td className="px-4 md:px-6 py-4 whitespace-nowrap">
                    <span className={p.status === "paid" ? "line-through" : ""}>
                      {p.date}
                    </span>
                  </td>
                  <td className="px-4 md:px-6 py-4 whitespace-nowrap">
                    <span className={p.status === "paid" ? "line-through" : ""}>
                      {p.amount.toLocaleString('ru-RU')} ₽
                    </span>
                  </td>
                  <td className="px-4 md:px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 py-1 text-xs rounded-full ${
                      p.status === "paid" 
                        ? "bg-green-100 text-green-800" 
                        : "bg-yellow-100 text-yellow-800"
                    }`}>
                      {p.status === "paid" ? "Оплачено" : "К оплате"}
                    </span>
                  </td>
                  {showPayButton && (
                    <td className="px-4 md:px-6 py-4 whitespace-nowrap">
                      <button
                        disabled={p.status === "paid" || loading}
                        onClick={() => handlePayClick(p)}
                        className={`px-4 py-2 rounded text-sm ${
                          p.status === "paid" || loading
                            ? "bg-gray-300 text-gray-500 cursor-not-allowed"
                            : "bg-blue-600 text-white hover:bg-blue-700"
                        }`}
                      >
                        {loading ? "Оплата..." : "Оплатить"}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Mobile Cards */}
      <div className="space-y-3 sm:hidden">
        {payments.map((p, index) => (
          <div
            key={index}
            className={`bg-white rounded-lg p-4 shadow ${
              p.status === "paid" ? "opacity-60" : ""
            }`}
          >
            <div className="flex justify-between items-start mb-2">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className={p.status === "paid" ? "line-through text-gray-500" : "font-medium"}>
                    {p.month}
                  </span>
                  {index === nextPaymentIndex && (
                    <span className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded">
                      Следующий
                    </span>
                  )}
                </div>
                <div className="text-sm text-gray-500 mt-1">
                  {p.date}
                </div>
              </div>
              <div className="text-right">
                <div className={p.status === "paid" ? "line-through text-gray-500" : "font-semibold text-lg"}>
                  {p.amount.toLocaleString('ru-RU')} ₽
                </div>
                <span className={`mt-1 inline-block px-2 py-1 text-xs rounded-full ${
                  p.status === "paid" 
                    ? "bg-green-100 text-green-800" 
                    : "bg-yellow-100 text-yellow-800"
                }`}>
                  {p.status === "paid" ? "Оплачено" : "К оплате"}
                </span>
              </div>
            </div>
            {showPayButton && p.status !== "paid" && (
              <button
                disabled={loading}
                onClick={() => handlePayClick(p)}
                className={`w-full mt-3 px-4 py-2 rounded text-sm ${
                  loading
                    ? "bg-gray-300 text-gray-500 cursor-not-allowed"
                    : "bg-blue-600 text-white hover:bg-blue-700"
                }`}
              >
                {loading ? "Оплата..." : "Оплатить"}
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Sticky CTA для мобильных */}
      {nextPayment && showPayButton && (
        <div className="fixed bottom-0 left-0 right-0 p-4 bg-white border-t shadow-lg sm:hidden z-50">
          <button
            onClick={() => handlePayClick(nextPayment)}
            disabled={loading}
            className="w-full bg-black text-white py-3 rounded-lg font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Оплатить {nextPayment.amount.toLocaleString('ru-RU')} ₽
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
    </>
  );
}
