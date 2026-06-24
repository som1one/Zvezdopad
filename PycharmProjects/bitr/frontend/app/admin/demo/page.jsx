"use client";

import { useState } from "react";
import Header from "@/components/layout/Header";
import Link from "next/link";

// Захардкоженные данные для демо-админки
const DEMO_DEALS = [
  {
    id: "DEAL_001",
    client_name: "Иванов Иван Иванович",
    email: "ivanov@example.com",
    total_amount: 300000,
    paid_amount: 100000,
    rest_amount: 200000,
    term_months: 6,
    status: "В процессе",
    progress: 33,
    created_at: "2025-01-15"
  },
  {
    id: "DEAL_002",
    client_name: "Петрова Мария Сергеевна",
    email: "petrova@example.com",
    total_amount: 500000,
    paid_amount: 250000,
    rest_amount: 250000,
    term_months: 10,
    status: "В процессе",
    progress: 50,
    created_at: "2025-02-01"
  },
  {
    id: "DEAL_003",
    client_name: "Сидоров Алексей Петрович",
    email: "sidorov@example.com",
    total_amount: 200000,
    paid_amount: 200000,
    rest_amount: 0,
    term_months: 4,
    status: "Завершена",
    progress: 100,
    created_at: "2024-12-10"
  },
  {
    id: "DEAL_004",
    client_name: "Козлова Елена Викторовна",
    email: "kozlova@example.com",
    total_amount: 450000,
    paid_amount: 150000,
    rest_amount: 300000,
    term_months: 12,
    status: "В процессе",
    progress: 33,
    created_at: "2025-01-20"
  },
  {
    id: "DEAL_005",
    client_name: "Морозов Дмитрий Александрович",
    email: "morozov@example.com",
    total_amount: 600000,
    paid_amount: 600000,
    rest_amount: 0,
    term_months: 8,
    status: "Завершена",
    progress: 100,
    created_at: "2024-11-05"
  }
];

export default function AdminDemoPage() {
  const [searchTerm, setSearchTerm] = useState("");

  const filteredDeals = DEMO_DEALS.filter(deal =>
    deal.client_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    deal.email.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <>
      <Header />
      <main className="p-4 sm:p-6 lg:p-8 bg-dashboard-bg min-h-screen">
        <div className="max-w-7xl mx-auto space-y-6">
          {/* Заголовок */}
          <div className="mb-8">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h1 className="text-3xl font-bold text-white mb-2">Панель администратора</h1>
                <p className="text-dashboard-text-muted">Управление рассрочками</p>
              </div>
              <div className="px-4 py-2 bg-purple-500/10 border border-purple-500/30 rounded-lg text-sm text-purple-300">
                🎨 Демо-режим
              </div>
            </div>

            {/* Поиск и фильтры */}
            <div className="flex flex-col sm:flex-row gap-4">
              <div className="flex-1">
                <input
                  type="text"
                  placeholder="Поиск по имени или email..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full px-4 py-2 bg-dashboard-card border border-slate-700/50 rounded-lg text-white placeholder-dashboard-text-muted focus:outline-none focus:ring-2 focus:ring-purple-500/50"
                />
              </div>
              <div className="flex gap-2">
                <button className="px-4 py-2 bg-dashboard-card border border-slate-700/50 rounded-lg text-white hover:bg-slate-700/50 transition-colors">
                  Фильтры
                </button>
                <button className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors">
                  Экспорт
                </button>
              </div>
            </div>
          </div>

          {/* Статистика */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-dashboard-card border border-slate-700/50 rounded-xl p-4 backdrop-blur-sm">
              <div className="text-sm text-dashboard-text-muted mb-1">Всего сделок</div>
              <div className="text-2xl font-bold text-white">{DEMO_DEALS.length}</div>
            </div>
            <div className="bg-dashboard-card border border-slate-700/50 rounded-xl p-4 backdrop-blur-sm">
              <div className="text-sm text-dashboard-text-muted mb-1">В процессе</div>
              <div className="text-2xl font-bold text-blue-400">
                {DEMO_DEALS.filter(d => d.status === "В процессе").length}
              </div>
            </div>
            <div className="bg-dashboard-card border border-slate-700/50 rounded-xl p-4 backdrop-blur-sm">
              <div className="text-sm text-dashboard-text-muted mb-1">Завершено</div>
              <div className="text-2xl font-bold text-green-400">
                {DEMO_DEALS.filter(d => d.status === "Завершена").length}
              </div>
            </div>
            <div className="bg-dashboard-card border border-slate-700/50 rounded-xl p-4 backdrop-blur-sm">
              <div className="text-sm text-dashboard-text-muted mb-1">Общая сумма</div>
              <div className="text-2xl font-bold text-white">
                {DEMO_DEALS.reduce((sum, d) => sum + d.total_amount, 0).toLocaleString('ru-RU')} ₽
              </div>
            </div>
          </div>

          {/* Таблица сделок */}
          <div className="bg-dashboard-card border border-slate-700/50 rounded-xl overflow-hidden backdrop-blur-sm">
            <div className="p-6 border-b border-slate-700/50">
              <h2 className="text-xl font-semibold text-white">Список рассрочек</h2>
              <p className="text-sm text-dashboard-text-muted mt-1">
                Найдено: {filteredDeals.length} из {DEMO_DEALS.length}
              </p>
            </div>

            {/* Мобильная версия - карточки */}
            <div className="block sm:hidden divide-y divide-slate-700/50">
              {filteredDeals.map((deal) => (
                <Link
                  key={deal.id}
                  href={`/admin/demo/${deal.id}`}
                  className="block p-4 hover:bg-slate-800/50 transition-colors"
                >
                  <div className="space-y-2">
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-white truncate">{deal.client_name}</div>
                        <div className="text-xs text-dashboard-text-muted truncate">{deal.email}</div>
                      </div>
                      <span className={`px-2 py-1 text-xs font-medium rounded-full whitespace-nowrap ml-2 ${
                        deal.status === 'Завершена' 
                          ? 'bg-green-500/20 text-green-400' 
                          : 'bg-blue-500/20 text-blue-400'
                      }`}>
                        {deal.status}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <div className="text-dashboard-text-muted text-xs">Сумма</div>
                        <div className="text-white font-medium">{deal.total_amount.toLocaleString('ru-RU')} ₽</div>
                      </div>
                      <div>
                        <div className="text-dashboard-text-muted text-xs">Оплачено</div>
                        <div className="text-green-400 font-medium">{deal.paid_amount.toLocaleString('ru-RU')} ₽</div>
                      </div>
                    </div>
                    <div className="pt-2">
                      <div className="h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-gradient-to-r from-purple-500 to-purple-600 transition-all"
                          style={{ width: `${deal.progress}%` }}
                        />
                      </div>
                      <div className="text-xs text-dashboard-text-muted mt-1">
                        Прогресс: {deal.progress}%
                      </div>
                    </div>
                  </div>
                </Link>
              ))}
            </div>

            {/* Десктопная версия - таблица */}
            <div className="hidden sm:block overflow-x-auto light-scrollbar">
              <table className="w-full">
                <thead className="bg-slate-800/50 border-b border-slate-700/50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-dashboard-text-muted uppercase">Клиент</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-dashboard-text-muted uppercase">Сумма</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-dashboard-text-muted uppercase">Оплачено</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-dashboard-text-muted uppercase">Остаток</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-dashboard-text-muted uppercase">Срок</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-dashboard-text-muted uppercase">Прогресс</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-dashboard-text-muted uppercase">Статус</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/50">
                  {filteredDeals.map((deal) => (
                    <tr key={deal.id} className="hover:bg-slate-800/30 transition-colors">
                      <td className="px-6 py-4">
                        <Link 
                          href={`/admin/demo/${deal.id}`}
                          className="block group"
                        >
                          <div className="font-medium text-white group-hover:text-purple-400 transition-colors">
                            {deal.client_name}
                          </div>
                          <div className="text-sm text-dashboard-text-muted">{deal.email}</div>
                        </Link>
                      </td>
                      <td className="px-6 py-4 text-white font-medium">
                        {deal.total_amount.toLocaleString('ru-RU')} ₽
                      </td>
                      <td className="px-6 py-4 text-green-400 font-medium">
                        {deal.paid_amount.toLocaleString('ru-RU')} ₽
                      </td>
                      <td className="px-6 py-4 text-dashboard-text-muted">
                        {deal.rest_amount.toLocaleString('ru-RU')} ₽
                      </td>
                      <td className="px-6 py-4 text-dashboard-text-muted">
                        {deal.term_months} мес.
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-2 bg-slate-700/50 rounded-full overflow-hidden min-w-[60px]">
                            <div 
                              className="h-full bg-gradient-to-r from-purple-500 to-purple-600 transition-all"
                              style={{ width: `${deal.progress}%` }}
                            />
                          </div>
                          <span className="text-xs text-dashboard-text-muted whitespace-nowrap">
                            {deal.progress}%
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                          deal.status === 'Завершена' 
                            ? 'bg-green-500/20 text-green-400' 
                            : 'bg-blue-500/20 text-blue-400'
                        }`}>
                          {deal.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}

