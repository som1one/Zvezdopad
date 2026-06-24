#!/usr/bin/env python3
"""
Проверка реальных данных о сделках из Bitrix24
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bitrix.client import get_all_installment_deals, _get_full_deal
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_deals_data():
    """Проверяет реальные данные из Bitrix24"""
    deals = get_all_installment_deals()
    print(f"Всего сделок: {len(deals)}\n")
    
    print("=" * 80)
    print("Первые 10 сделок (краткие данные из crm.deal.list):")
    print("=" * 80)
    for deal in deals[:10]:
        deal_id = deal.get('ID')
        opportunity = deal.get('OPPORTUNITY', 'N/A')
        term_months = deal.get('UF_TERM_MONTHS', 'N/A')
        title = deal.get('TITLE', 'N/A')
        print(f"ID {deal_id}: {title}")
        print(f"  OPPORTUNITY: {opportunity}")
        print(f"  UF_TERM_MONTHS: {term_months}")
        print()
    
    print("\n" + "=" * 80)
    print("Полные данные для первых 5 сделок (через crm.deal.get):")
    print("=" * 80)
    for deal in deals[:5]:
        deal_id = deal.get('ID')
        try:
            full_deal = _get_full_deal(deal_id)
            if full_deal:
                opportunity = full_deal.get('OPPORTUNITY', 'N/A')
                term_months = full_deal.get('UF_TERM_MONTHS', 'N/A')
                title = full_deal.get('TITLE', 'N/A')
                contact_id = full_deal.get('CONTACT_ID', 'N/A')
                
                print(f"\nID {deal_id}: {title}")
                print(f"  OPPORTUNITY: {opportunity} (тип: {type(opportunity).__name__})")
                print(f"  UF_TERM_MONTHS: {term_months} (тип: {type(term_months).__name__})")
                print(f"  CONTACT_ID: {contact_id}")
                
                # Показываем все поля, содержащие "AMOUNT" или "TERM"
                amount_fields = {k: v for k, v in full_deal.items() if 'AMOUNT' in k.upper() or 'SUM' in k.upper()}
                term_fields = {k: v for k, v in full_deal.items() if 'TERM' in k.upper() or 'MONTH' in k.upper()}
                
                if amount_fields:
                    print(f"  Поля с суммой: {amount_fields}")
                if term_fields:
                    print(f"  Поля со сроком: {term_fields}")
        except Exception as e:
            print(f"\nID {deal_id}: Ошибка получения полных данных - {e}")

if __name__ == "__main__":
    check_deals_data()

