"use client";

import { useDeals } from "@/modules/admin/deals/hooks";
import DealsTable from "@/components/admin/DealsTable";
import { Loader, ErrorState, EmptyState } from "@/components/ui/State";
import { ClipboardList, DollarSign, Wallet, Banknote, Search, Download, TestTube, Trash2, Filter } from "lucide-react";
import { useMemo, useState } from "react";
import { testWebhook } from "@/modules/admin/payments/api";
import { clearDatabase } from "@/modules/admin/deals/api";

export default function AdminDealsPage() {
  const { deals, loading, error, refetch } = useDeals();
  const [searchQuery, setSearchQuery] = useState("");
  const [filterType, setFilterType] = useState("all"); // "all", "installment", "configured", "not_configured"
  const [testingWebhook, setTestingWebhook] = useState(false);
  const [webhookTestResult, setWebhookTestResult] = useState(null);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [clearing, setClearing] = useState(false);

  const installmentDeals = useMemo(() => {
    if (!deals) return [];
    
    // ОТЛАДКА: логируем все сделки для диагностики
    console.log("🔍 Все сделки из API:", deals);
    console.log("🔍 Количество сделок:", deals.length);
    
    // Применяем фильтр по типу
    const filtered = deals.filter((d) => {
      const totalAmount = Number(d.total_amount) || 0;
      const initialPayment = Number(d.initial_payment) || 0;
      const termMonths = Number(d.term_months) || 0;
      const installmentAmount = Math.max(0, totalAmount - initialPayment);
      const isConfigured = installmentAmount > 0 && termMonths > 0;
      
      switch (filterType) {
        case "installment":
          // Только рассрочки (есть сумма рассрочки)
          return installmentAmount > 0;
        case "configured":
          // Только настроенные (есть сумма и срок)
          return isConfigured;
        case "not_configured":
          // Только не настроенные (нет суммы или срока)
          return !isConfigured;
        case "all":
        default:
          // Все сделки
          return true;
      }
    });
    
    console.log("🔍 После фильтрации:", filtered.length, `(фильтр: ${filterType})`);
    if (filtered.length === 0 && deals.length > 0) {
      console.warn("⚠️ Все сделки отфильтрованы! Примеры:", deals.slice(0, 3));
    }
    
    return filtered;
  }, [deals, filterType]);

  const filteredDeals = useMemo(() => {
    if (!installmentDeals) return [];
    if (!searchQuery.trim()) return installmentDeals;
    
    const query = searchQuery.toLowerCase();
    return installmentDeals.filter(d => {
      const title = (d.title || "").toLowerCase();
      const email = (d.email || "").toLowerCase();
      const dealId = (d.deal_id || "").toLowerCase();
      return title.includes(query) || email.includes(query) || dealId.includes(query);
    });
  }, [installmentDeals, searchQuery]);

  const stats = useMemo(() => {
    if (!deals || deals.length === 0) {
      return {
        installmentsCount: 0,
        installmentTotal: 0,
        installmentPaid: 0,
        installmentRemaining: 0,
      };
    }

    // Метрики считаем по сумме РАССРОЧКИ (total_amount - initial_payment), а не по общей сумме сделки
    const normalized = deals.map((d) => {
      const totalAmount = Number(d.total_amount) || 0;
      const paidAmount = Number(d.paid_amount) || 0;
      const initialPayment = Number(d.initial_payment) || 0;
      const termMonths = Number(d.term_months) || 0;

      const installmentAmount = Math.max(0, totalAmount - initialPayment);
      // initial_payment не является фактом оплаты => оплачено по графику = paid_amount (с ограничением суммой рассрочки)
      const paidInstallment = Math.min(installmentAmount, Math.max(0, paidAmount));
      const remainingInstallment = Math.max(0, installmentAmount - paidInstallment);

      // "Рассрочка" для KPI = реально настроенная рассрочка (есть срок и сумма > 0).
      // Сделки с term_months=0 показываем в таблице, но в KPI не считаем.
      const isInstallment = installmentAmount > 0 && termMonths > 0;

      return {
        isInstallment,
        installmentAmount,
        paidInstallment,
        remainingInstallment,
      };
    });

    const installmentsCount = normalized.filter((x) => x.isInstallment).length;
    const installmentTotal = normalized.reduce((sum, x) => sum + (x.isInstallment ? x.installmentAmount : 0), 0);
    const installmentPaid = normalized.reduce((sum, x) => sum + (x.isInstallment ? x.paidInstallment : 0), 0);
    const installmentRemaining = normalized.reduce((sum, x) => sum + (x.isInstallment ? x.remainingInstallment : 0), 0);

    return {
      installmentsCount,
      installmentTotal,
      installmentPaid,
      installmentRemaining,
    };
  }, [deals]);

  const handleTestWebhook = async () => {
    setTestingWebhook(true);
    setWebhookTestResult(null);
    try {
      const result = await testWebhook();
      setWebhookTestResult({ success: true, message: result.message || "Webhook работает корректно" });
    } catch (error) {
      setWebhookTestResult({ 
        success: false, 
        message: error.message || "Ошибка при тестировании webhook" 
      });
    } finally {
      setTestingWebhook(false);
    }
  };

  const handleExport = () => {
    // Простой экспорт в CSV
    const csv = [
      ["ID", "Клиент", "Email", "Сумма", "Оплачено", "Остаток", "Срок", "Статус"].join(","),
      ...filteredDeals.map(d => [
        // Экспортируем по сумме рассрочки (total - initial)
        d.deal_id,
        `"${d.title || ""}"`,
        d.email || "",
        Math.max(0, (Number(d.total_amount) || 0) - (Number(d.initial_payment) || 0)),
        Math.max(0, (Number(d.paid_amount) || 0) - (Number(d.initial_payment) || 0)),
        Math.max(0, Math.max(0, (Number(d.total_amount) || 0) - (Number(d.initial_payment) || 0)) - Math.max(0, (Number(d.paid_amount) || 0) - (Number(d.initial_payment) || 0))),
        d.term_months || 0,
        d.status || "active"
      ].join(","))
    ].join("\n");

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `deals_${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
  };

  const handleClearDatabase = async () => {
    setClearing(true);
    try {
      await clearDatabase();
      alert("База данных успешно очищена!");
      setShowClearConfirm(false);
      refetch();
    } catch (error) {
      alert(`Ошибка при очистке базы данных: ${error.message || "Неизвестная ошибка"}`);
    } finally {
      setClearing(false);
    }
  };

  if (loading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900/20 to-slate-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <Loader text="Загрузка сделок..." />
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900/20 to-slate-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <ErrorState message={error} onRetry={refetch} />
        </div>
      </main>
    );
  }

  if (!deals || deals.length === 0) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900/20 to-slate-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <EmptyState text="Сделки не найдены" icon="📋" />
        </div>
      </main>
    );
  }

  // По умолчанию показываем только рассрочки: если их нет — выводим пустое состояние
  if (installmentDeals.length === 0) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900/20 to-slate-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <EmptyState text="Рассрочки не найдены" icon="📋" />
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900/20 to-slate-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Заголовок */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">Панель администратора</h1>
          <p className="text-slate-400 text-lg">Управление рассрочками</p>
        </div>

        {/* Результат теста webhook */}
        {webhookTestResult && (
          <div className={`mb-4 p-4 rounded-lg ${
            webhookTestResult.success 
              ? "bg-green-500/20 border border-green-500/50 text-green-400" 
              : "bg-red-500/20 border border-red-500/50 text-red-400"
          }`}>
            <p className="font-medium">{webhookTestResult.message}</p>
          </div>
        )}

        {/* Поиск и фильтры */}
        <div className="mb-6 space-y-4">
          <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Поиск по имени или email..."
                className="w-full pl-10 pr-4 py-3 bg-slate-800/50 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              />
            </div>
            <div className="flex gap-3">
              <button 
                onClick={handleTestWebhook}
                disabled={testingWebhook}
                className="px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <TestTube className="w-4 h-4" />
                {testingWebhook ? "Проверка..." : "Тест webhook"}
              </button>
              <button 
                onClick={handleExport}
                className="px-4 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors flex items-center gap-2 font-medium"
              >
                <Download className="w-4 h-4" />
                Экспорт
              </button>
              <button 
                onClick={() => setShowClearConfirm(true)}
                className="px-4 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors flex items-center gap-2 font-medium"
              >
                <Trash2 className="w-4 h-4" />
                Очистить БД
              </button>
            </div>
          </div>
          
          {/* Фильтр по типу рассрочки */}
          <div className="flex items-center gap-2 flex-wrap">
            <Filter className="w-5 h-5 text-slate-400" />
            <span className="text-sm text-slate-400 font-medium">Фильтр:</span>
            <button
              onClick={() => setFilterType("all")}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                filterType === "all"
                  ? "bg-purple-600 text-white"
                  : "bg-slate-800/50 text-slate-300 hover:bg-slate-700 border border-slate-700"
              }`}
            >
              Все сделки
            </button>
            <button
              onClick={() => setFilterType("installment")}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                filterType === "installment"
                  ? "bg-purple-600 text-white"
                  : "bg-slate-800/50 text-slate-300 hover:bg-slate-700 border border-slate-700"
              }`}
            >
              С рассрочкой
            </button>
            <button
              onClick={() => setFilterType("configured")}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                filterType === "configured"
                  ? "bg-purple-600 text-white"
                  : "bg-slate-800/50 text-slate-300 hover:bg-slate-700 border border-slate-700"
              }`}
            >
              Настроенные
            </button>
            <button
              onClick={() => setFilterType("not_configured")}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                filterType === "not_configured"
                  ? "bg-purple-600 text-white"
                  : "bg-slate-800/50 text-slate-300 hover:bg-slate-700 border border-slate-700"
              }`}
            >
              Не настроенные
            </button>
          </div>
        </div>

        {/* Статистика */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700 rounded-xl p-6 hover:bg-slate-800/70 transition-all hover:border-purple-500/50">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-400 mb-1">Рассрочек</p>
                <p className="text-3xl font-bold text-white">{stats.installmentsCount}</p>
              </div>
              <div className="p-3 bg-purple-500/20 rounded-lg">
                <ClipboardList className="w-6 h-6 text-purple-400" />
              </div>
            </div>
          </div>

          <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700 rounded-xl p-6 hover:bg-slate-800/70 transition-all hover:border-purple-500/50">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-400 mb-1">Оплачено</p>
                <p className="text-3xl font-bold text-emerald-400">
                  {stats.installmentPaid.toLocaleString('ru-RU')} ₽
                </p>
              </div>
              <div className="p-3 bg-emerald-500/20 rounded-lg">
                <Wallet className="w-6 h-6 text-emerald-400" />
              </div>
            </div>
          </div>

          <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700 rounded-xl p-6 hover:bg-slate-800/70 transition-all hover:border-purple-500/50">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-400 mb-1">Осталось оплатить</p>
                <p className="text-3xl font-bold text-blue-400">
                  {stats.installmentRemaining.toLocaleString('ru-RU')} ₽
                </p>
              </div>
              <div className="p-3 bg-blue-500/20 rounded-lg">
                <Banknote className="w-6 h-6 text-blue-400" />
              </div>
            </div>
          </div>

          <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700 rounded-xl p-6 hover:bg-slate-800/70 transition-all hover:border-purple-500/50">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-400 mb-1">Общая сумма рассрочки</p>
                <p className="text-3xl font-bold text-white">
                  {stats.installmentTotal.toLocaleString('ru-RU')} ₽
                </p>
              </div>
              <div className="p-3 bg-purple-500/20 rounded-lg">
                <DollarSign className="w-6 h-6 text-purple-400" />
              </div>
            </div>
          </div>
        </div>

        {/* Таблица */}
        <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700 rounded-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-700">
            <h2 className="text-lg font-semibold text-white">Список рассрочек</h2>
            <p className="text-sm text-slate-400 mt-1">
              Найдено: {filteredDeals.length} из {installmentDeals.length}
            </p>
          </div>
          <DealsTable deals={filteredDeals} onRefresh={refetch} />
        </div>
      </div>

      {/* Модальное окно подтверждения очистки БД */}
      {showClearConfirm && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-slate-800 border border-red-500/50 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-red-500/20 rounded-lg">
                <Trash2 className="w-6 h-6 text-red-400" />
              </div>
              <h2 className="text-xl font-semibold text-white">Очистка базы данных</h2>
            </div>
            
            <div className="mb-6">
              <p className="text-slate-300 mb-2">
                Вы уверены, что хотите очистить всю базу данных?
              </p>
              <p className="text-sm text-red-400 font-medium">
                ⚠️ Это действие удалит:
              </p>
              <ul className="text-sm text-slate-400 mt-2 ml-4 list-disc space-y-1">
                <li>Все сделки (deals)</li>
                <li>Все логи платежей (payment_logs)</li>
                <li>Все распределения платежей (cash_allocations)</li>
              </ul>
              <p className="text-sm text-red-400 font-medium mt-4">
                Это действие нельзя отменить!
              </p>
            </div>

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowClearConfirm(false)}
                disabled={clearing}
                className="px-4 py-2 border border-slate-600 text-slate-300 rounded-lg hover:bg-slate-700 disabled:opacity-50 transition-colors"
              >
                Отмена
              </button>
              <button
                onClick={handleClearDatabase}
                disabled={clearing}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 flex items-center gap-2 transition-colors"
              >
                {clearing ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    Очистка...
                  </>
                ) : (
                  <>
                    <Trash2 className="w-4 h-4" />
                    Очистить БД
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
