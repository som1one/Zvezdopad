"use client";

import { useState } from "react";

export default function DemoPaymentModal({ amount, onClose }) {
  const [loading, setLoading] = useState(false);

  const handlePay = async () => {
    if (loading) return;
    
    setLoading(true);
    // Имитация задержки для демо
    setTimeout(() => {
      alert(`Демо-режим: Оплата на сумму ${amount.toLocaleString('ru-RU')} ₽\n\nВ реальном режиме здесь будет перенаправление на платёжную систему.`);
      setLoading(false);
      onClose();
    }, 1000);
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-dashboard-card border border-slate-700/50 rounded-xl w-full max-w-md p-6 space-y-4 shadow-2xl">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xl font-semibold text-white">
            Оплата по рассрочке
          </h2>
          <button
            onClick={onClose}
            disabled={loading}
            className="text-dashboard-text-muted hover:text-white transition-colors disabled:opacity-50"
          >
            ✕
          </button>
        </div>

        <div className="px-3 py-2 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-sm text-yellow-300 mb-2">
          🎨 Демо-режим: платеж не будет выполнен
        </div>

        <div className="space-y-3 py-4 border-y border-slate-700/50">
          <Row label="Сумма" value={`${amount.toLocaleString('ru-RU')} ₽`} />
          <Row label="Комиссия" value="0 ₽" />
          <Row label="Итого" value={`${amount.toLocaleString('ru-RU')} ₽`} bold />
        </div>

        <button
          onClick={handlePay}
          disabled={loading}
          className="w-full bg-gradient-to-r from-purple-600 to-purple-700 hover:from-purple-700 hover:to-purple-800 text-white py-3 rounded-lg font-semibold transition-all shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? "Перенаправление..." : "Подтвердить оплату (Демо)"}
        </button>

        <button
          onClick={onClose}
          disabled={loading}
          className="w-full text-sm text-dashboard-text-muted hover:text-white disabled:opacity-50 transition-colors"
        >
          Отмена
        </button>

        <div className="text-xs text-dashboard-text-muted text-center flex items-center justify-center gap-1 pt-2">
          <span>🔒</span>
          <span>Платёж защищён ЮKassa</span>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, bold }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-dashboard-text-muted">{label}:</span>
      <span className={bold ? "font-semibold text-lg text-white" : "text-white"}>{value}</span>
    </div>
  );
}

