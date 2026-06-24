"use client";

export default function DashboardCard({ title, value, subtitle, icon, color = "purple", trend }) {
  const colorClasses = {
    purple: "bg-gradient-to-br from-purple-500/20 to-purple-600/20 border-purple-500/30",
    blue: "bg-gradient-to-br from-blue-500/20 to-blue-600/20 border-blue-500/30",
    green: "bg-gradient-to-br from-green-500/20 to-green-600/20 border-green-500/30",
    orange: "bg-gradient-to-br from-orange-500/20 to-orange-600/20 border-orange-500/30",
  };

  const iconColors = {
    purple: "text-purple-400",
    blue: "text-blue-400",
    green: "text-green-400",
    orange: "text-orange-400",
  };

  return (
    <div className={`rounded-xl border p-6 ${colorClasses[color]} backdrop-blur-sm transition-all hover:scale-105 hover:shadow-lg`}>
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          {icon && (
            <div className={`p-3 rounded-lg bg-white/5 ${iconColors[color]}`}>
              {icon}
            </div>
          )}
          <div>
            <p className="text-sm text-dashboard-text-muted font-medium">{title}</p>
            {subtitle && (
              <p className="text-xs text-dashboard-text-muted/70 mt-1">{subtitle}</p>
            )}
          </div>
        </div>
        {trend && (
          <div className={`text-xs font-semibold px-2 py-1 rounded ${
            trend > 0 ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
          }`}>
            {trend > 0 ? '↑' : '↓'} {Math.abs(trend)}%
          </div>
        )}
      </div>
      <div className="mt-4">
        <p className="text-3xl font-bold text-white">{value}</p>
      </div>
    </div>
  );
}

