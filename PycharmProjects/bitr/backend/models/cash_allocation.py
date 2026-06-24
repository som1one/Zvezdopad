from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime

from models.payment_log import Base


class CashAllocation(Base):
    """
    Распределение платежа (наличных) по месяцам графика.
    month_index — индекс платежа в графике (0..term-1) на момент формирования графика.
    """
    __tablename__ = "cash_allocations"

    id = Column(Integer, primary_key=True, index=True)
    deal_id = Column(String, index=True)
    payment_id = Column(String, index=True)  # payment_logs.payment_id (cash_*)
    month_index = Column(Integer, index=True)
    amount = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)


