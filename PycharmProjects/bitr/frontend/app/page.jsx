"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/auth";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    const token = getToken();
    
    if (!token) {
      // Если нет токена, редирект на страницу авторизации
      router.push("/auth/login");
    } else {
      // Если есть токен, редирект на страницу рассрочки
      router.push("/installment");
    }
  }, [router]);

  return (
    <div className="flex items-center justify-center min-h-screen bg-dashboard-bg">
      <div className="text-center">
        <div className="w-16 h-16 border-4 border-purple-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
        <p className="text-dashboard-text-muted">Перенаправление...</p>
      </div>
    </div>
  );
}

