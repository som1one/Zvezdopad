import { getToken } from './auth';
import { logger } from './logger';

// Используем относительный путь для работы через nginx в Docker
// В браузере это будет /api, что nginx проксирует на backend
const API_URL = process.env.NEXT_PUBLIC_API_URL || '';

class ApiClient {
  async request(url, options = {}) {
    const token = getToken();
    
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    try {
      const response = await fetch(`${API_URL}${url}`, {
        ...options,
        headers,
      });

      if (!response.ok) {
        let errorMessage = `Ошибка ${response.status}: ${response.statusText}`;
        
        try {
          const errorText = await response.text();
          if (errorText) {
            try {
              const errorJson = JSON.parse(errorText);
              errorMessage = errorJson.detail || errorJson.message || errorMessage;
            } catch {
              errorMessage = errorText || errorMessage;
            }
          }
        } catch (parseError) {
          // Если не удалось распарсить ошибку, используем стандартное сообщение
          console.warn("Не удалось распарсить ошибку от сервера:", parseError);
        }
        
        logger.error("api_request_failed", {
          url,
          status: response.status,
          statusText: response.statusText,
          error: errorMessage,
        });
        
        // Перенаправляем на страницу входа при 401/403
        if (response.status === 401 || response.status === 403) {
          // Очищаем токен
          if (typeof window !== 'undefined') {
            localStorage.removeItem('token');
            // Перенаправляем на страницу входа только если мы не на странице логина
            if (!window.location.pathname.startsWith('/auth/')) {
              // Для админки отправляем на отдельный логин
              if (window.location.pathname.startsWith('/admin')) {
                window.location.href = '/auth/admin/login';
              } else {
                window.location.href = '/auth/login';
              }
            }
          }
        }
        
        const error = new Error(errorMessage);
        error.status = response.status;
        error.response = response;
        throw error;
      }

      // Проверка на пустой ответ
      const contentType = response.headers.get("content-type");
      if (!contentType || !contentType.includes("application/json")) {
        const text = await response.text();
        if (!text) {
          throw new Error("Сервер вернул пустой ответ");
        }
        // Пытаемся распарсить как JSON даже если content-type не указан
        try {
          return JSON.parse(text);
        } catch {
          throw new Error("Сервер вернул неверный формат данных");
        }
      }

      const data = await response.json();
      logger.info("api_request_success", { url, method: options.method || 'GET' });
      return data;
    } catch (err) {
      // Улучшенная обработка сетевых ошибок
      if (err.name === "TypeError" && err.message.includes("fetch")) {
        const networkError = new Error("Не удалось подключиться к серверу. Проверьте подключение к интернету.");
        networkError.isNetworkError = true;
        logger.error("api_network_error", { url, error: err.message });
        throw networkError;
      }
      
      logger.error("api_request_error", { 
        url, 
        error: err.message,
        status: err.status,
        stack: err.stack 
      });
      throw err;
    }
  }

  get(url) {
    return this.request(url, { method: 'GET' });
  }

  post(url, data) {
    return this.request(url, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  put(url, data) {
    return this.request(url, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  delete(url) {
    return this.request(url, { method: 'DELETE' });
  }
}

export const apiClient = new ApiClient();

