"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";

export default function LoginPage() {
  const [phone, setPhone] = useState("");
  const [acceptedOffer, setAcceptedOffer] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);
  const router = useRouter();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setMessage(null);

    try {
      // Нормализуем телефон (убираем пробелы для отправки)
      const normalizedPhone = phone.replace(/\s/g, "");
      
      // Отправляем телефон
      let response;
      try {
        response = await fetch(`/api/auth/magic-link?phone=${encodeURIComponent(normalizedPhone)}`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
        });
      } catch (e) {
        // Если query параметр не работает, пробуем body
        response = await fetch("/api/auth/magic-link", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ phone: normalizedPhone }),
        });
      }

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || data.message || "Ошибка запроса");
      }

      // Если в development режиме, показываем ссылку
      if (data.link) {
        setMessage(`Ссылка для входа: ${data.link}`);
        // Автоматически переходим по ссылке
        setTimeout(() => {
          window.location.href = data.link;
        }, 2000);
      } else {
        setMessage("Ссылка для входа отправлена");
      }
    } catch (err) {
      setError(err.message || "Ошибка при запросе ссылки для входа");
    } finally {
      setLoading(false);
    }
  };

  // Форматирование телефона при вводе
  const handlePhoneChange = (e) => {
    let value = e.target.value.replace(/\D/g, ""); // Только цифры
    if (value.startsWith("8")) {
      value = "7" + value.slice(1);
    }
    if (value.length > 11) {
      value = value.slice(0, 11);
    }
    
    // Форматируем: +7 (XXX) XXX-XX-XX
    let formatted = "";
    if (value.length > 0) {
      formatted = "+7";
      if (value.length > 1) {
        formatted += " (" + value.slice(1, 4);
        if (value.length > 4) {
          formatted += ") " + value.slice(4, 7);
          if (value.length > 7) {
            formatted += "-" + value.slice(7, 9);
            if (value.length > 9) {
              formatted += "-" + value.slice(9, 11);
            }
          }
        } else {
          formatted += ")";
        }
      }
    }
    setPhone(formatted);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="bg-dashboard-card rounded-2xl border border-slate-700/50 p-8 backdrop-blur-sm shadow-2xl">
          <div className="text-center mb-8">
            <div className="w-16 h-16 bg-slate-900/40 border border-slate-700/60 rounded-full flex items-center justify-center mx-auto mb-4 overflow-hidden">
              <Image
                src="/logo.png"
                alt="Логотип"
                width={40}
                height={40}
                priority
              />
            </div>
            <h1 className="text-3xl font-bold text-white mb-2">Вход в систему</h1>
            <p className="text-dashboard-text-muted">
              Введите ваш номер телефона для получения ссылки для входа
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="phone" className="block text-sm font-medium text-white mb-2">
                Номер телефона
              </label>
              <input
                id="phone"
                type="tel"
                value={phone}
                onChange={handlePhoneChange}
                required
                className="w-full px-4 py-3 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                placeholder="+7 (XXX) XXX-XX-XX"
                disabled={loading}
                maxLength={18}
              />
            </div>

            <div className="flex items-start gap-3">
              <input
                id="accept-offer"
                type="checkbox"
                checked={acceptedOffer}
                onChange={(e) => setAcceptedOffer(e.target.checked)}
                className="mt-1 h-4 w-4 rounded border-slate-600 bg-slate-800 text-purple-600 focus:ring-purple-500"
              />
              <label htmlFor="accept-offer" className="text-sm text-slate-300">
                Я принимаю условия{" "}
                <a
                  href="/offer"
                  target="_blank"
                  rel="noreferrer"
                  className="text-purple-400 hover:text-purple-300 underline"
                >
                  оферты/политики
                </a>
              </label>
            </div>

            {error && (
              <div className="bg-red-500/10 border border-red-500/50 rounded-lg p-4">
                <p className="text-red-400 text-sm">{error}</p>
              </div>
            )}

            {message && (
              <div className="bg-green-500/10 border border-green-500/50 rounded-lg p-4">
                <p className="text-green-400 text-sm">{message}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !phone || phone.length < 10 || !acceptedOffer}
              className="w-full bg-purple-600 hover:bg-purple-700 disabled:bg-slate-700 disabled:cursor-not-allowed text-white font-semibold py-3 px-4 rounded-lg transition-colors"
            >
              {loading ? "Отправка..." : "Получить ссылку для входа"}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-dashboard-text-muted">
            <p>
              Если у вас нет рассрочки или возникли проблемы,{" "}
              <span className="text-purple-400">обратитесь к администратору</span>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

