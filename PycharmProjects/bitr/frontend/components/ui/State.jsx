"use client";

export function Loader({ text = "Загрузка..." }) {
  return (
    <div className="flex items-center justify-center p-8">
      <div className="text-center">
        <div className="w-12 h-12 border-4 border-purple-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
        <div className="animate-pulse text-dashboard-text-muted">{text}</div>
      </div>
    </div>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="p-6 bg-red-500/10 border border-red-500/30 text-red-400 rounded-xl">
      <div className="flex items-center justify-between">
        <div>
          <p className="font-semibold text-white mb-1">Ошибка</p>
          <p className="text-sm text-red-400/80">{message}</p>
        </div>
        {onRetry && (
          <button
            onClick={onRetry}
            className="ml-4 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-semibold transition-colors"
          >
            Повторить
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ text, icon }) {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-dashboard-text-muted">
      {icon && <div className="text-5xl mb-4">{icon}</div>}
      <p className="text-center text-lg">{text}</p>
    </div>
  );
}

