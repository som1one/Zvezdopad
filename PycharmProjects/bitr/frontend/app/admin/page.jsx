"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default function AdminIndexPage() {
  const router = useRouter();

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/auth/admin/login");
      return;
    }
    router.replace("/admin/deals");
  }, [router]);

  return null;
}


