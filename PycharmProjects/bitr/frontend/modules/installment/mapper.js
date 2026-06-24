export function mapDeal(dto) {
  // Валидация входных данных
  if (!dto) {
    throw new Error("Данные для маппинга отсутствуют");
  }

  if (!dto.deal) {
    throw new Error("Данные сделки отсутствуют");
  }

  const deal = dto.deal;
  
  // Безопасное получение значений с дефолтами
  const total = Number(deal.total_amount) || 0;
  const paid = Number(deal.paid_amount) || 0;
  const initial_payment = Number(deal.initial_payment) || 0;
  const installment_amount = Number(deal.installment_amount) || Math.max(0, total - initial_payment);
  // initial_payment не является "оплаченной суммой", это только параметр графика.
  // Поэтому оплачено по графику = paid_amount (с ограничением суммой рассрочки).
  const paid_installment = Math.min(installment_amount, Math.max(0, paid));
  const rest_installment = Math.max(0, installment_amount - paid_installment);
  const term = Number(deal.term_months) || 0;
  const rest = Math.max(0, total - paid); // Убеждаемся, что остаток не отрицательный

  // Валидация платежей
  let payments = [];
  if (Array.isArray(dto.payments)) {
    payments = dto.payments
      .filter(p => p != null) // Фильтруем null/undefined
      .map(p => ({
        index: Number(p.index ?? p.month_index) || 0,
        month: p.month || "Не указано",
        date: p.date || "",
        amount: Number(p.amount) || 0,
        status: (p.status === "paid" || p.status === "partial" || p.status === "pending") ? p.status : "pending",
        // Не подставляем 0, если значения реально отсутствуют — иначе графики будут считать "всё оплачено"
        paid_in_month: (p.paid_in_month ?? p.paid_amount_for_month) != null ? (Number(p.paid_in_month ?? p.paid_amount_for_month) || 0) : null,
        remaining_in_month: p.remaining_in_month != null ? (Number(p.remaining_in_month) || 0) : null,
      }))
      .filter(p => p.amount > 0); // Фильтруем платежи с нулевой суммой
  }

  return {
    total,
    paid,
    rest,
    initial_payment,
    installment_amount,
    paid_installment,
    rest_installment,
    term,
    payments,
    contract_number: deal.contract_number || deal.ID || "UNKNOWN",
    title: deal.title || "Рассрочка",
    client_name: deal.client_name || "",
    client_phone: deal.client_phone || deal.CONTACT_PHONE || deal.contact_phone || "",
    project_type: deal.project_type || "",
    project_start_date: deal.project_start_date || "",
    object_location: deal.object_location || "",
    is_admin: !!deal.is_admin,
    crm_deal_url: deal.crm_deal_url || "",
    // Сохраняем исходные поля для детальной карточки
    raw: deal
  };
}

