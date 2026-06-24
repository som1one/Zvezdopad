"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default function OfferPage() {
  const [text, setText] = useState("");
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/offer.txt", { cache: "no-store" });
        if (!res.ok) throw new Error(`Не удалось загрузить документ (HTTP ${res.status})`);
        const body = await res.text();
        if (!cancelled) setText(body || "");
      } catch (e) {
        if (!cancelled) setError(e?.message || "Ошибка загрузки документа");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900/20 to-slate-900">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="mb-6">
          <Link
            href="/auth/login"
            className="inline-flex items-center gap-2 text-slate-400 hover:text-white transition-colors"
          >
            ← Назад
          </Link>
        </div>

        <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700 rounded-xl p-6">
          <h1 className="text-2xl sm:text-3xl font-bold text-white mb-4">Оферта / Политика</h1>

          {error ? (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
              <p className="text-red-300">{error}</p>
            </div>
          ) : (
            <pre className="whitespace-pre-wrap text-slate-200 leading-relaxed text-sm sm:text-base">
              {text || "Загрузка..."}
            </pre>
          )}
        </div>
      </div>
    </main>
  );
}


