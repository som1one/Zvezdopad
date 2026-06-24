"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { hasToken, removeToken } from "@/lib/auth";

export default function Header() {
  const router = useRouter();
  const pathname = usePathname();
  const [isAuthed, setIsAuthed] = useState(false);

  useEffect(() => {
    setIsAuthed(hasToken());
  }, []);

  const handleLogout = () => {
    removeToken();
    try {
      localStorage.removeItem("user");
    } catch {}
    setIsAuthed(false);

    // Если пользователь был в админке — ведём на админ-логин, иначе на обычный логин
    if ((pathname || "").startsWith("/admin")) {
      router.replace("/auth/admin/login");
    } else {
      router.replace("/auth/login");
    }
  };

  return (
    <header className="bg-dashboard-card border-b border-slate-700/50 backdrop-blur-sm sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-slate-900/40 border border-slate-700/60 flex items-center justify-center overflow-hidden">
              <Image
                src="/logo.png"
                alt="Логотип Мари Каркас"
                width={32}
                height={32}
                priority
              />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-white">Рассрочка</h1>
              <p className="text-xs text-dashboard-text-muted">Управление платежами</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="hidden md:flex items-center gap-2 px-4 py-2 bg-slate-800/50 rounded-lg border border-slate-700/50">
              <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
              <span className="text-sm text-dashboard-text-muted">Система активна</span>
            </div>
            {isAuthed && (
              <button
                onClick={handleLogout}
                className="px-4 py-2 bg-slate-800/60 hover:bg-slate-700 text-white text-sm font-semibold rounded-lg transition-colors border border-slate-700/60"
              >
                Выйти
              </button>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

