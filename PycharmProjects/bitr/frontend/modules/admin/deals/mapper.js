export function mapDeal(dto) {
  return {
    id: dto.deal.contract_number,
    contract: dto.deal.contract_number,
    client_name: dto.deal.client_name || 'Не указан',
    total_amount: dto.deal.total_amount,
    paid_amount: dto.deal.paid_amount,
    term_months: dto.deal.term_months,
    status: dto.deal.paid_amount >= dto.deal.total_amount ? 'Завершена' : 'Активна',
    payments: dto.payments.map(p => ({
      month: p.month,
      date: p.date,
      amount: p.amount,
      status: p.status,
    }))
  };
}

export function mapDealsList(deals) {
  return deals.map(mapDeal);
}

