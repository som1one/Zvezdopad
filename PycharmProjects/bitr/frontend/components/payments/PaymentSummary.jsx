"use client";

export default function PaymentSummary({ amount, commission = 0 }) {
  const total = amount + commission;

  return (
    <div className="bg-gray-50 rounded-lg p-4 space-y-2">
      <div className="flex justify-between text-sm">
        <span className="text-gray-600">Сумма платежа:</span>
        <span className="font-medium">{amount.toLocaleString('ru-RU')} ₽</span>
      </div>
      {commission > 0 && (
        <div className="flex justify-between text-sm">
          <span className="text-gray-600">Комиссия:</span>
          <span className="font-medium">{commission.toLocaleString('ru-RU')} ₽</span>
        </div>
      )}
      <div className="flex justify-between text-base pt-2 border-t border-gray-300">
        <span className="font-semibold">Итого к оплате:</span>
        <span className="font-bold text-lg">{total.toLocaleString('ru-RU')} ₽</span>
      </div>
    </div>
  );
}

