import { apiClient } from "@/lib/apiClient";

export async function getPaymentLogs(dealId = null) {
  const url = dealId ? `/api/payments/logs?deal_id=${dealId}` : "/api/payments/logs";
  return apiClient.get(url);
}

export async function testWebhook() {
  return apiClient.post("/api/payments/webhook/test");
}

