# Импортируем функции для удобства
from .client import (
    get_installment_deal,
    get_installment_deal_by_phone,
    get_all_installment_deals,
    update_paid_amount,
    _get_full_deal
)

# Функция для проверки существования контакта (используем get_installment_deal)
def verify_contact_exists(email: str) -> bool:
    """
    Проверяет, существует ли контакт в Bitrix24 по email.
    Использует get_installment_deal, который ищет контакт.
    """
    deal = get_installment_deal(email)
    return deal is not None

__all__ = [
    'get_installment_deal',
    'get_installment_deal_by_phone',
    'get_all_installment_deals',
    'update_paid_amount',
    '_get_full_deal',
    'verify_contact_exists'
]

