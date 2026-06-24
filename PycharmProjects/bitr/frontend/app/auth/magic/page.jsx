"use client";

export const dynamic = 'force-dynamic';

import { useEffect, Suspense, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { setToken } from "@/lib/auth";
import { apiClient } from "@/lib/apiClient";

function MagicLinkContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get("token");
  const [status, setStatus] = useState('loading'); // 'loading' | 'success' | 'error'
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    const authenticate = async () => {
      if (!token) {
        setStatus('error');
        setErrorMessage('Токен не найден в ссылке');
        setTimeout(() => {
          router.push('/auth/login');
        }, 2000);
        return;
      }

      try {
        // Сохраняем токен
        setToken(token);
        
        // Валидируем токен, делая тестовый запрос к API
        // Это также создаст сессию пользователя в БД если её нет
        try {
          await apiClient.get('/api/installment/my');
          // Если запрос успешен, токен валидный
          setStatus('success');
          // Небольшая задержка для плавного перехода
          setTimeout(() => {
            router.push('/installment');
          }, 300);
        } catch (error) {
          // Если токен невалидный или истек
          setStatus('error');
          const err = error || {};
          if (err.status === 401 || err.status === 403) {
            setErrorMessage('Ссылка для входа недействительна или истекла. Запросите новую ссылку.');
          } else if (err.status === 404) {
            setErrorMessage('Рассрочка не найдена. Обратитесь к администратору.');
          } else {
            setErrorMessage('Ошибка при проверке токена. Попробуйте еще раз.');
          }
          setTimeout(() => {
            router.push('/auth/login');
          }, 3000);
        }
      } catch (error) {
        setStatus('error');
        setErrorMessage('Произошла ошибка при авторизации');
        setTimeout(() => {
          router.push('/auth/login');
        }, 2000);
      }
    };

    authenticate();
  }, [token, router]);

  return (
    <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-purple-900 via-purple-800 to-indigo-900">
      <div className="bg-gray-800 rounded-lg shadow-2xl p-8 max-w-md w-full mx-4">
        {status === 'loading' && (
          <div className="text-center">
            <div className="inline-block animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-purple-500 mb-4"></div>
            <h1 className="text-2xl font-bold text-white mb-2">Авторизация...</h1>
            <p className="text-gray-400">Проверка токена доступа</p>
          </div>
        )}
        
        {status === 'success' && (
          <div className="text-center">
            <div className="inline-block mb-4">
              <svg className="w-12 h-12 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-white mb-2">Успешный вход!</h1>
            <p className="text-gray-400">Перенаправление...</p>
          </div>
        )}
        
        {status === 'error' && (
          <div className="text-center">
            <div className="inline-block mb-4">
              <svg className="w-12 h-12 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-white mb-2">Ошибка входа</h1>
            <p className="text-red-400 mb-4">{errorMessage}</p>
            <p className="text-gray-400 text-sm">Перенаправление на страницу входа...</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default function MagicLinkPage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-purple-900 via-purple-800 to-indigo-900">
        <div className="bg-gray-800 rounded-lg shadow-2xl p-8 max-w-md w-full mx-4 text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-purple-500 mb-4"></div>
          <h1 className="text-2xl font-bold text-white mb-2">Загрузка...</h1>
        </div>
      </div>
    }>
      <MagicLinkContent />
    </Suspense>
  );
}

