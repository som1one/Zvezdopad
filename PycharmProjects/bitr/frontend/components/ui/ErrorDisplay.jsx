"use client";

export default function ErrorDisplay({ error, onRetry, title = "Ошибка" }) {
  if (!error) return null;

  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
      <div className="flex items-start">
        <svg
          className="h-5 w-5 text-red-500 mt-0.5 mr-3 flex-shrink-0"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-red-800 mb-1">
            {title}
          </h3>
          <p className="text-sm text-red-700">
            {typeof error === "string" ? error : error?.message || "Произошла неизвестная ошибка"}
          </p>
          
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-3 text-sm text-red-800 underline hover:text-red-900"
            >
              Попробовать снова
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

