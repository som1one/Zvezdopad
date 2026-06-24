import { apiClient } from "@/lib/apiClient";

export function getDeals() {
  return apiClient.get("/api/admin/deals");
}

export function getDeal(id) {
  return apiClient.get(`/api/admin/deals/${id}`);
}

export function recordCashPayment(dealId, allocations, comment, paymentDate = null) {
  const idempotencyKey = (typeof crypto !== "undefined" && crypto.randomUUID)
    ? crypto.randomUUID()
    : `${Date.now()}_${Math.random().toString(16).slice(2)}`;

  const safeAllocs = Array.isArray(allocations) ? allocations : [];
  const totalAmount = safeAllocs.reduce((sum, a) => sum + (Number(a.amount) || 0), 0);
  return apiClient.post(`/api/admin/deals/${dealId}/cash-payment`, {
    deal_id: dealId,
    comment: comment || null,
    idempotency_key: idempotencyKey,
    amount: totalAmount,
    allocations: safeAllocs,
    payment_date: paymentDate || null
  });
}

export function updateDealSettings(dealId, settings) {
  return apiClient.put(`/api/admin/deals/${dealId}/settings`, settings);
}

export function clearDatabase() {
  return apiClient.post("/api/admin/database/clear");
}
