"use client";

import { useState } from 'react';

export default function SimpleProgressChart({ payments }) {
  const [hoveredIndex, setHoveredIndex] = useState(null);

  // Подготовка данных для графика - накопленная сумма оплаченных платежей
  const chartData = payments.map((payment, index) => {
    let cumulativePaid = 0;
    for (let i = 0; i <= index; i++) {
      if (payments[i].status === "paid") {
        cumulativePaid += payments[i].amount;
      }
    }
    
    return {
      month: payment.month,
      date: payment.date,
      amount: payment.amount,
      cumulative: cumulativePaid,
      status: payment.status,
    };
  });

  const totalAmount = payments.reduce((sum, p) => sum + p.amount, 0);
  const paidAmount = payments
    .filter(p => p.status === "paid")
    .reduce((sum, p) => sum + p.amount, 0);

  const maxCumulative = Math.max(...chartData.map(d => d.cumulative), totalAmount);
  const progressPercent = totalAmount > 0 ? Math.round((paidAmount / totalAmount) * 100) : 0;

  return (
    <div className="bg-dashboard-card rounded-xl border border-slate-700/50 p-6 backdrop-blur-sm">
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <div>
            <h3 className="text-xl font-semibold text-white mb-1">Прогресс оплаты</h3>
            <p className="text-sm text-dashboard-text-muted">Динамика погашения рассрочки</p>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold text-purple-400">{progressPercent}%</div>
            <div className="text-xs text-dashboard-text-muted">Выполнено</div>
          </div>
        </div>
        
        {/* Общий прогресс бар */}
        <div className="mt-4">
          <div className="h-2 bg-slate-700/50 rounded-full overflow-hidden">
            <div 
              className="h-full bg-gradient-to-r from-purple-500 via-purple-600 to-purple-500 transition-all duration-500 relative overflow-hidden"
              style={{ width: `${progressPercent}%` }}
            >
              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer"></div>
            </div>
          </div>
        </div>
      </div>

      {/* Улучшенная визуализация прогресса */}
      <div className="mb-6">
        <div className="relative h-[280px] flex items-end justify-between gap-1 sm:gap-2 px-2">
          {chartData.map((data, index) => {
            const height = (data.cumulative / maxCumulative) * 100;
            const isPaid = data.status === "paid";
            const isHovered = hoveredIndex === index;
            const monthShort = data.month.split(' ')[0].substring(0, 3);
            
            return (
              <div 
                key={index} 
                className="flex-1 flex flex-col items-center group cursor-pointer"
                onMouseEnter={() => setHoveredIndex(index)}
                onMouseLeave={() => setHoveredIndex(null)}
              >
                {/* Tooltip при наведении */}
                {isHovered && (
                  <div className="absolute bottom-full mb-2 px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg shadow-xl z-10 min-w-[140px]">
                    <div className="text-xs text-dashboard-text-muted mb-1">{data.month}</div>
                    <div className="text-sm font-semibold text-white">
                      {data.cumulative.toLocaleString('ru-RU')} ₽
                    </div>
                    <div className="text-xs text-dashboard-text-muted mt-1">
                      {isPaid ? '✅ Оплачено' : '⏳ Ожидает'}
                    </div>
                    <div className="absolute bottom-0 left-1/2 transform -translate-x-1/2 translate-y-1/2 w-2 h-2 bg-slate-800 border-r border-b border-slate-600 rotate-45"></div>
                  </div>
                )}
                
                {/* Столбец графика */}
                <div className="relative w-full flex items-end justify-center" style={{ height: '220px' }}>
                  <div
                    className={`w-full rounded-t-lg transition-all duration-300 relative overflow-hidden ${
                      isPaid 
                        ? 'bg-gradient-to-t from-purple-600 via-purple-500 to-purple-400 shadow-lg shadow-purple-500/30' 
                        : 'bg-gradient-to-t from-slate-700 via-slate-600 to-slate-500'
                    } ${isHovered ? 'scale-105 brightness-110' : ''}`}
                    style={{ height: `${Math.max(height, 5)}%` }}
                  >
                    {/* Эффект свечения для оплаченных */}
                    {isPaid && (
                      <div className="absolute inset-0 bg-gradient-to-t from-transparent via-white/10 to-transparent"></div>
                    )}
                    {/* Точка на вершине */}
                    {height > 0 && (
                      <div className={`absolute -top-1 left-1/2 transform -translate-x-1/2 w-2 h-2 rounded-full ${
                        isPaid ? 'bg-purple-300 shadow-lg shadow-purple-400/50' : 'bg-slate-400'
                      }`}></div>
                    )}
                  </div>
                </div>
                
                {/* Подпись месяца */}
                <div className="mt-3 text-[10px] sm:text-xs text-dashboard-text-muted text-center font-medium">
                  {monthShort}
                </div>
              </div>
            );
          })}
        </div>
        
        {/* Легенда */}
        <div className="mt-6 flex items-center justify-center gap-6 text-xs">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded bg-gradient-to-br from-purple-500 to-purple-600 shadow-sm"></div>
            <span className="text-dashboard-text-muted">Оплачено</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded bg-gradient-to-br from-slate-600 to-slate-700"></div>
            <span className="text-dashboard-text-muted">Ожидает оплаты</span>
          </div>
        </div>
      </div>

      {/* Статистика */}
      <div className="grid grid-cols-2 gap-4 mt-6">
        <div className="bg-gradient-to-br from-slate-800/60 to-slate-800/40 rounded-lg p-4 border border-slate-700/50 backdrop-blur-sm">
          <p className="text-sm text-dashboard-text-muted mb-1">Всего к оплате</p>
          <p className="text-2xl font-bold text-white">{totalAmount.toLocaleString('ru-RU')} ₽</p>
        </div>
        <div className="bg-gradient-to-br from-green-900/30 to-green-800/20 rounded-lg p-4 border border-green-700/30 backdrop-blur-sm">
          <p className="text-sm text-dashboard-text-muted mb-1">Уже оплачено</p>
          <p className="text-2xl font-bold text-green-400">{paidAmount.toLocaleString('ru-RU')} ₽</p>
        </div>
      </div>
    </div>
  );
}

