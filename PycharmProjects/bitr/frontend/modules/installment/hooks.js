import { useEffect, useState } from "react";
import { getMyInstallment, createPayment } from "./api";
import { mapDeal } from "./mapper";
import { logger } from "@/lib/logger";

export function useInstallment() {
  const [deal, setDeal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [paymentLoading, setPaymentLoading] = useState(false);

  useEffect(() => {
    loadDeal();
  }, []);

  const loadDeal = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMyInstallment();
      
      // Валидация данных перед маппингом
      if (!data) {
        throw new Error("Сервер вернул пустой ответ");
      }
      
      // Проверка структуры данных
      if (data.error) {
        throw new Error(data.error || "Рассрочка не найдена");
      }
      
      if (!data.deal && !data.payments) {
        throw new Error("Неверный формат данных от сервера");
      }
      
      const mappedDeal = mapDeal(data);
      
      // Дополнительная валидация после маппинга
      if (!mappedDeal) {
        throw new Error("Ошибка обработки данных");
      }
      
      setDeal(mappedDeal);
      logger.info("installment_loaded", { dealId: data.deal?.contract_number });
    } catch (err) {
      console.error("Ошибка загрузки рассрочки:", err);
      
      // Более детальное сообщение об ошибке
      let errorMsg = "Ошибка загрузки данных";
      
      if (err.message) {
        errorMsg = err.message;
      } else if (err.response?.status === 404) {
        errorMsg = "Рассрочка не найдена. Обратитесь к администратору.";
      } else if (err.response?.status === 500) {
        errorMsg = "Ошибка сервера. Попробуйте позже.";
      } else if (err.name === "TypeError" && err.message.includes("fetch")) {
        errorMsg = "Не удалось подключиться к серверу. Проверьте подключение к интернету.";
      }
      
      setError(errorMsg);
      logger.error("installment_load_error", { 
        error: errorMsg,
        originalError: err.message,
        stack: err.stack 
      });
    } finally {
      setLoading(false);
    }
  };

  const pay = async (amount) => {
    if (paymentLoading) {
      logger.warn("payment_duplicate_attempt", { amount });
      return; // Идемпотентность на фронте
    }
    
    setPaymentLoading(true);
    try {
      logger.info("payment_attempt", { amount });
      const { url } = await createPayment(amount);
      logger.info("payment_redirect", { url, amount });
      window.location.href = url;
    } catch (err) {
      const errorMsg = err.message || "Ошибка создания платежа";
      logger.error("payment_error", { error: errorMsg, amount });
      setError(errorMsg);
      setPaymentLoading(false);
    }
  };

  return { deal, loading, error, pay, paymentLoading, refetch: loadDeal };
}
