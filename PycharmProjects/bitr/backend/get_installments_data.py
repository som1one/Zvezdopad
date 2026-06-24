#!/usr/bin/env python3
"""
Скрипт для получения всех данных о рассрочках (срок и сумма)
"""
import sys
import os

# Добавляем корневую директорию проекта в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.deal import Deal
from models.payment_log import SessionLocal
from bitrix.client import get_all_installment_deals, _get_full_deal
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_all_installments_data():
    """Получает все данные о рассрочках"""
    db = SessionLocal()
    try:
        # Получаем все рассрочки из Bitrix24
        logger.info("Получение всех рассрочек из Bitrix24...")
        bitrix_deals = get_all_installment_deals()
        logger.info(f"Найдено {len(bitrix_deals)} рассрочек в Bitrix24")
        
        # Получаем все сделки из локальной БД
        db_deals = db.query(Deal).all()
        db_deals_dict = {deal.deal_id: deal for deal in db_deals}
        logger.info(f"Найдено {len(db_deals)} записей в локальной БД")
        
        # Объединяем данные
        result = []
        for bitrix_deal in bitrix_deals:
            deal_id = bitrix_deal.get("ID")
            
            # Получаем полные данные сделки из Bitrix24 (включая пользовательские поля)
            try:
                full_deal = _get_full_deal(deal_id)
                if full_deal:
                    bitrix_deal = full_deal
            except Exception as e:
                logger.warning(f"Не удалось получить полные данные для сделки {deal_id}: {e}")
            
            # Получаем сумму из Bitrix24
            opportunity = bitrix_deal.get("OPPORTUNITY", "0")
            if isinstance(opportunity, str):
                opportunity = opportunity.replace(" ", "").replace(",", "")
            try:
                total_amount = int(float(opportunity)) if opportunity and float(opportunity) > 0 else 0
            except (ValueError, TypeError):
                total_amount = 0
            
            # Используем данные из БД если они есть (источник истины)
            db_deal = db_deals_dict.get(deal_id)
            if db_deal and db_deal.total_amount > 0:
                total_amount = db_deal.total_amount
            # НЕ используем дефолт - если сумма не указана, оставляем 0
            # Это позволит видеть, какие сделки имеют реальные данные
            
            # Получаем срок рассрочки
            term_months = None  # Нет дефолта - показываем что не указано
            if db_deal:
                term_months = db_deal.term_months
            else:
                term_str = bitrix_deal.get("UF_TERM_MONTHS")
                if term_str and str(term_str).strip() and str(term_str) != "N/A":
                    try:
                        term_months = int(term_str)
                    except (ValueError, TypeError):
                        term_months = None
            
            # Получаем оплаченную сумму
            paid_amount = db_deal.paid_amount if db_deal else 0
            
            # Получаем email/телефон пользователя
            user_identifier = db_deal.email if db_deal else None
            if not user_identifier:
                # Пытаемся получить из контакта Bitrix24
                try:
                    contact_id = bitrix_deal.get("CONTACT_ID")
                    if contact_id:
                        from core.config import settings
                        import requests
                        contact_res = requests.get(
                            f"{settings.BITRIX_WEBHOOK_URL}/crm.contact.get",
                            params={"ID": contact_id},
                            timeout=10
                        )
                        if contact_res.status_code == 200:
                            contact = contact_res.json().get('result', {})
                            # Проверяем телефон
                            phone = contact.get('PHONE')
                            if phone:
                                if isinstance(phone, list) and len(phone) > 0:
                                    if isinstance(phone[0], dict):
                                        user_identifier = phone[0].get('VALUE', '')
                                    else:
                                        user_identifier = str(phone[0])
                                elif isinstance(phone, str):
                                    user_identifier = phone
                            # Если телефона нет, проверяем email
                            if not user_identifier:
                                email = contact.get('EMAIL')
                                if email:
                                    if isinstance(email, list) and len(email) > 0:
                                        if isinstance(email[0], dict):
                                            user_identifier = email[0].get('VALUE', '')
                                        else:
                                            user_identifier = str(email[0])
                                    elif isinstance(email, str):
                                        user_identifier = email
                            # Если и email нет, используем NAME
                            if not user_identifier:
                                name = contact.get('NAME', '')
                                if name:
                                    user_identifier = name
                except Exception as e:
                    logger.debug(f"Не удалось получить контакт для сделки {deal_id}: {e}")
            
            result.append({
                "deal_id": deal_id,
                "title": bitrix_deal.get("TITLE", ""),
                "user_identifier": user_identifier or "Не указан",
                "total_amount": total_amount,
                "paid_amount": paid_amount,
                "remaining_amount": max(0, total_amount - paid_amount) if total_amount else 0,
                "term_months": term_months or "Не указан",
                "has_real_data": (total_amount > 0) and (term_months is not None)
            })
        
        return result
    finally:
        db.close()

def save_to_file(data, filename="installments_data.txt"):
    """Сохраняет данные в текстовый файл"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write("Данные о рассрочках\n")
        f.write("=" * 80 + "\n\n")
        
        for item in sorted(data, key=lambda x: x["deal_id"]):
            f.write(f"ID сделки: {item['deal_id']}\n")
            f.write(f"Название: {item['title']}\n")
            f.write(f"Пользователь: {item['user_identifier']}\n")
            if item['total_amount'] > 0:
                f.write(f"Общая сумма: {item['total_amount']:,} ₽\n")
                f.write(f"Оплачено: {item['paid_amount']:,} ₽\n")
                f.write(f"Остаток: {item['remaining_amount']:,} ₽\n")
            else:
                f.write(f"Общая сумма: НЕ УКАЗАНА в Bitrix24\n")
                f.write(f"Оплачено: {item['paid_amount']:,} ₽\n")
                f.write(f"Остаток: НЕ РАСЧИТЫВАЕТСЯ (нет суммы)\n")
            
            if isinstance(item['term_months'], int):
                f.write(f"Срок рассрочки: {item['term_months']} месяцев\n")
            else:
                f.write(f"Срок рассрочки: НЕ УКАЗАН в Bitrix24\n")
            
            if not item.get('has_real_data'):
                f.write(f"⚠️  ВНИМАНИЕ: Данные не заполнены в Bitrix24!\n")
            f.write("-" * 80 + "\n\n")
        
        # Итого
        total_sum = sum(item["total_amount"] for item in data)
        total_paid = sum(item["paid_amount"] for item in data)
        total_remaining = sum(item["remaining_amount"] for item in data)
        
        f.write("\n" + "=" * 80 + "\n")
        f.write("ИТОГО:\n")
        f.write(f"Всего рассрочек: {len(data)}\n")
        f.write(f"Общая сумма всех рассрочек: {total_sum:,} ₽\n")
        f.write(f"Общая оплаченная сумма: {total_paid:,} ₽\n")
        f.write(f"Общий остаток: {total_remaining:,} ₽\n")

if __name__ == "__main__":
    try:
        data = get_all_installments_data()
        save_to_file(data)
        print(f"\n✅ Данные сохранены в файл installments_data.txt")
        print(f"📊 Обработано рассрочек: {len(data)}")
        
        # Выводим краткую статистику
        total_sum = sum(item["total_amount"] for item in data)
        total_paid = sum(item["paid_amount"] for item in data)
        print(f"💰 Общая сумма: {total_sum:,} ₽")
        print(f"💵 Оплачено: {total_paid:,} ₽")
        print(f"📈 Остаток: {total_sum - total_paid:,} ₽")
    except Exception as e:
        logger.error(f"Ошибка при получении данных: {e}", exc_info=True)
        sys.exit(1)

