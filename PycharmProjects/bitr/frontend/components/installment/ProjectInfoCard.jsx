"use client";

export default function ProjectInfoCard({ deal }) {
  if (!deal) return null;

  const projectType = deal.project_type || "—";
  const projectStart = deal.project_start_date || "—";
  const location = deal.object_location || "—";

  const total = Number(deal.total) || 0;
  const paid = Number(deal.paid) || 0;
  const rest = Math.max(0, total - paid);
  const percent = total > 0 ? Math.round((paid / total) * 100) : 0;

  const showCrmButton = !!deal.is_admin && !!deal.crm_deal_url;

  return (
    <div className="bg-dashboard-card rounded-xl border border-slate-700/50 p-6 backdrop-blur-sm">
      <div className="flex flex-col lg:flex-row gap-6 items-stretch">
        {/* Left: project fields + button */}
        <div className="flex-1">
          <div className="space-y-4">
            <Field label="Тип проекта" value={projectType} />
            <Field label="Начало проекта" value={projectStart} />
            <Field label="Где находится объект" value={location} />
          </div>

          {showCrmButton && (
            <div className="mt-6">
              <a
                href={deal.crm_deal_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center justify-center px-6 py-3 rounded-xl font-semibold text-white bg-gradient-to-r from-emerald-600 to-emerald-700 hover:from-emerald-700 hover:to-emerald-800 transition-colors shadow-lg"
              >
                Открыть сделку в ЦРМ
              </a>
            </div>
          )}
        </div>

        {/* Right: donut card */}
        <div className="w-full lg:w-[320px] bg-slate-900/30 border border-slate-700/50 rounded-xl p-5 flex items-center justify-between gap-4">
          <Donut percent={percent} />
          <div className="flex-1">
            <Row label="Оплачено" value={`${paid.toLocaleString("ru-RU")} ₽`} />
            <Row label="Осталось оплатить" value={`${rest.toLocaleString("ru-RU")} ₽`} />
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-baseline gap-2">
      <div className="text-xl sm:text-2xl font-semibold text-white">{label}:</div>
      <div className="text-xl sm:text-2xl text-dashboard-text-muted">{value}</div>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="mb-3 last:mb-0">
      <div className="text-sm text-dashboard-text-muted">{label}:</div>
      <div className="text-lg font-semibold text-white">{value}</div>
    </div>
  );
}

function Donut({ percent }) {
  const safe = Math.max(0, Math.min(100, Number(percent) || 0));
  const style = {
    background: `conic-gradient(#8b5cf6 ${safe}%, rgba(148,163,184,0.25) 0)`,
  };
  return (
    <div className="relative w-24 h-24 shrink-0">
      <div className="w-24 h-24 rounded-full" style={style} />
      <div className="absolute inset-3 rounded-full bg-slate-900/60 border border-slate-700/40 flex items-center justify-center">
        <div className="text-lg font-bold text-white">{safe}%</div>
      </div>
    </div>
  );
}


