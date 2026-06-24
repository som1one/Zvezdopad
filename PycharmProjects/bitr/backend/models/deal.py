from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from models.payment_log import Base
from datetime import datetime

class Deal(Base):
    __tablename__ = "deals"
    
    id = Column(Integer, primary_key=True, index=True)
    deal_id = Column(String, unique=True, index=True)  # ID из Bitrix24
    title = Column(String)
    email = Column(String, index=True)  # Email пользователя
    total_amount = Column(Integer)  # Общая сумма рассрочки
    paid_amount = Column(Integer, default=0)  # Оплаченная сумма
    initial_payment = Column(Integer, default=0)  # Первоначальный взнос (учитывается в paid_amount)
    term_months = Column(Integer)  # Срок в месяцах

    # График платежей:
    # - schedule_start_date фиксируется в момент создания/настройки графика (чтобы даты не "плясали" от DATE_CREATE в Bitrix)
    # - schedule_day — день месяца для платежа (по умолчанию 10)
    schedule_start_date = Column(DateTime, nullable=True)
    schedule_day = Column(Integer, default=10)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

