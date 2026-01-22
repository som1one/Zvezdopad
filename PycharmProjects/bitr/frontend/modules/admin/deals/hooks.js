import { useEffect, useState } from "react";
import { getDeals, getDeal } from "./api";

export function useDeals() {
  const [deals, setDeals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadDeals();
  }, []);

  const loadDeals = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getDeals();
      console.log("📥 Данные от API /api/admin/deals:", data);
      console.log("📥 Тип данных:", Array.isArray(data) ? "массив" : typeof data);
      console.log("📥 Количество:", Array.isArray(data) ? data.length : "не массив");
      
      if (!Array.isArray(data)) {
        console.error("❌ API вернул не массив:", data);
        setError("Сервер вернул неверный формат данных");
        setDeals([]);
        return;
      }
      
      setDeals(data);
      console.log("✅ Сделки загружены:", data.length);
    } catch (err) {
      setError(err.message || "Ошибка загрузки сделок");
      console.error("❌ deals_load_error", { 
        error: err.message,
        stack: err.stack,
        response: err.response
      });
      setDeals([]);
    } finally {
      setLoading(false);
    }
  };

  return { deals, loading, error, refetch: loadDeals };
}

export function useDeal(id) {
  const [deal, setDeal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (id) loadDeal(id);
  }, [id]);

  const loadDeal = async (dealId) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getDeal(dealId);
      setDeal(data);
    } catch (err) {
      setError(err.message || "Ошибка загрузки сделки");
      console.error("deal_load_error", { error: err.message, dealId });
    } finally {
      setLoading(false);
    }
  };

  return { deal, loading, error, refetch: () => loadDeal(id) };
}
