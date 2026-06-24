import { apiClient } from "@/lib/apiClient";

export async function getMyInstallment() {
  return apiClient.get("/api/installment/my");
}

export async function createPayment(amount) {
  return apiClient.post("/api/payments/create", { amount });
}

