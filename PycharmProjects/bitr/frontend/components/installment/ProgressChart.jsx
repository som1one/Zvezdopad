"use client";

import { useEffect, useState } from 'react';

class ChartErrorBoundary extends (require("react").Component) {
  constructor(props) {
    super(props);
    this.state = { hasError: false, message: "" };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, message: error?.message || "Ошибка отображения графика" };
  }
  componentDidCatch(error, info) {
    // Логи в консоль — полезно для диагностики в проде (не ломает UI)
    // eslint-disable-next-line no-console
    console.error("ProgressChart render error:", error, info);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="bg-dashboard-card rounded-xl border border-slate-700/50 p-6 backdrop-blur-sm">
          <div className="mb-6">
            <h3 className="text-xl font-semibold text-white mb-1">Прогресс оплаты</h3>
            <p className="text-sm text-dashboard-text-muted">Динамика погашения рассрочки</p>
          </div>
          <div className="text-center text-dashboard-text-muted py-8">
            Ошибка отображения графика. Используется упрощенный вид.
            <div className="text-xs text-slate-500 mt-2">{this.state.message}</div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function ProgressChartInner({ payments }) {
  const [isClient, setIsClient] = useState(false);
  const [ChartLib, setChartLib] = useState(null);

  useEffect(() => {
    setIsClient(true);
    // Импортируем recharts динамически только на клиенте
    import('recharts').then((lib) => {
      // recharts может экспортироваться по-разному, обрабатываем оба случая
      setChartLib(lib.default || lib);
    }).catch((err) => {
      console.error("Ошибка загрузки recharts:", err);
      setChartLib(null);
    });
  }, []);

  if (!payments || payments.length === 0) {
    return (
      <div className="bg-dashboard-card rounded-xl border border-slate-700/50 p-6 backdrop-blur-sm">
        <div className="mb-6">
          <h3 className="text-xl font-semibold text-white mb-1">Прогресс оплаты</h3>
          <p className="text-sm text-dashboard-text-muted">Динамика погашения рассрочки</p>
        </div>
        <div className="h-[250px] flex items-center justify-center">
          <div className="text-dashboard-text-muted">Нет данных для отображения</div>
        </div>
      </div>
    );
  }

  // Подготовка данных для графика и расчеты
  const safePayments = Array.isArray(payments) ? payments.filter(Boolean) : [];
  const chartData = safePayments.map((payment, index) => {
    // Накопленная сумма по графику
    let cumulativeScheduled = 0;
    for (let i = 0; i <= index; i++) {
      cumulativeScheduled += Number(safePayments[i]?.amount) || 0;
    }
    
    // Накопленная сумма фактически оплаченных платежей (учитываем partial)
    let cumulativePaid = 0;
    for (let i = 0; i <= index; i++) {
      const amt = Number(safePayments[i]?.amount) || 0;
      const paidInMonth = Number(safePayments[i]?.paid_in_month) || 0;
      const remaining = Number(safePayments[i]?.remaining_in_month);
      if (Number.isFinite(remaining)) {
        cumulativePaid += Math.max(0, amt - remaining);
      } else if (paidInMonth > 0) {
        cumulativePaid += Math.min(amt, paidInMonth);
      } else if (safePayments[i]?.status === "paid") {
        cumulativePaid += amt;
      }
    }
    
    return {
      month: payment.month || "",
      cumulative: Number.isFinite(cumulativeScheduled) ? cumulativeScheduled : 0,
      cumulativePaid: Number.isFinite(cumulativePaid) ? cumulativePaid : 0,
    };
  });

  // ВАЖНО: график строится по сумме РАССРОЧКИ (total - initial_payment),
  // поэтому totalAmount здесь = сумма платежей графика.
  const totalAmount = safePayments.reduce((sum, p) => sum + (Number(p.amount) || 0), 0);
  const paidAmount = safePayments.reduce((sum, p) => {
    const amt = Number(p?.amount) || 0;
    const paidInMonth = Number(p?.paid_in_month) || 0;
    const remaining = Number(p?.remaining_in_month);
    if (Number.isFinite(remaining)) return sum + Math.max(0, amt - remaining);
    if (paidInMonth > 0) return sum + Math.min(amt, paidInMonth);
    if (p?.status === "paid") return sum + amt;
    return sum;
  }, 0);
  const percent = totalAmount > 0 ? Math.round((paidAmount / totalAmount) * 100) : 0;

  // Если библиотека не загрузилась или еще не загружена, показываем fallback
  if (!isClient || !ChartLib) {
    return (
      <div className="bg-dashboard-card rounded-xl border border-slate-700/50 p-6 backdrop-blur-sm">
        <div className="mb-6">
          <h3 className="text-xl font-semibold text-white mb-1">Прогресс оплаты</h3>
          <p className="text-sm text-dashboard-text-muted">Динамика погашения рассрочки</p>
        </div>
        <div className="space-y-4">
          <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm text-dashboard-text-muted">Прогресс</span>
              <span className="text-lg font-bold text-purple-400">{percent}%</span>
            </div>
            <div className="w-full bg-slate-700 rounded-full h-4 overflow-hidden">
              <div
                className="bg-purple-500 h-full rounded-full transition-all duration-500"
                style={{ width: `${percent}%` }}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50">
              <p className="text-sm text-dashboard-text-muted mb-1">Сумма рассрочки</p>
              <p className="text-2xl font-bold text-white">{totalAmount.toLocaleString('ru-RU')} ₽</p>
            </div>
            <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50">
              <p className="text-sm text-dashboard-text-muted mb-1">Оплачено по графику</p>
              <p className="text-2xl font-bold text-green-400">{paidAmount.toLocaleString('ru-RU')} ₽</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Используем библиотеку для отображения графика
  // Безопасно извлекаем компоненты из ChartLib
  const { 
    AreaChart, Area, XAxis, YAxis, CartesianGrid, 
    Tooltip, ResponsiveContainer, Legend 
  } = ChartLib;

  // Если основные компоненты отсутствуют, возвращаем fallback
  if (!AreaChart || !Area) {
    return <div>Ошибка загрузки компонентов графика</div>;
  }

  return (
    <div className="bg-dashboard-card rounded-xl border border-slate-700/50 p-6 backdrop-blur-sm">
      <div className="mb-6">
        <h3 className="text-xl font-semibold text-white mb-1">Прогресс оплаты</h3>
        <p className="text-sm text-dashboard-text-muted">Динамика погашения рассрочки</p>
      </div>

      <div className="mb-6">
        <ResponsiveContainer width="100%" height={250}>
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="colorScheduled" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.4}/>
                <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0.1}/>
              </linearGradient>
              <linearGradient id="colorPaid" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis 
              dataKey="month" 
              stroke="#94a3b8"
              style={{ fontSize: '12px' }}
            />
            <YAxis 
              stroke="#94a3b8"
              style={{ fontSize: '12px' }}
              tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '8px',
                color: '#f1f5f9'
              }}
              formatter={(value, name) => {
                if (name === 'cumulativePaid') {
                  return [`${value.toLocaleString('ru-RU')} ₽`, 'Оплачено'];
                }
                return [`${value.toLocaleString('ru-RU')} ₽`, 'Запланировано'];
              }}
              labelFormatter={(label) => `Месяц ${label}`}
            />
            <Area
              type="monotone"
              dataKey="cumulative"
              stroke="#8b5cf6"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#colorScheduled)"
              name="Запланировано"
            />
            <Area
              type="monotone"
              dataKey="cumulativePaid"
              stroke="#10b981"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#colorPaid)"
              name="Оплачено"
            />
            {Legend && <Legend wrapperStyle={{ color: '#94a3b8', fontSize: '12px', paddingTop: '20px' }} />}
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-2 gap-4 mt-6">
        <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50">
          <p className="text-sm text-dashboard-text-muted mb-1">Сумма рассрочки</p>
          <p className="text-2xl font-bold text-white">{totalAmount.toLocaleString('ru-RU')} ₽</p>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50">
          <p className="text-sm text-dashboard-text-muted mb-1">Оплачено по графику</p>
          <p className="text-2xl font-bold text-green-400">{paidAmount.toLocaleString('ru-RU')} ₽</p>
        </div>
      </div>
    </div>
  );
}

export default function ProgressChart(props) {
  return (
    <ChartErrorBoundary>
      <ProgressChartInner {...props} />
    </ChartErrorBoundary>
  );
}
