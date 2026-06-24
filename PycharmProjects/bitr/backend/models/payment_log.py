from sqlalchemy import create_engine, Column, Integer, String, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os

Base = declarative_base()

# Поддержка PostgreSQL и SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./payment_logs.db")

if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class PaymentLog(Base):
    __tablename__ = "payment_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    deal_id = Column(String, index=True)
    payment_id = Column(String, unique=True, index=True)
    amount = Column(Integer)
    status = Column(String)  # "pending", "paid", "failed"
    source = Column(String)  # "yookassa", "admin"
    comment = Column(String, nullable=True)  # комментарий (например, для наличной оплаты)
    created_at = Column(DateTime, default=datetime.utcnow)
    payment_date = Column(DateTime, nullable=True)  # дата фактической оплаты (может отличаться от created_at)

def init_db():
    # Импортируем все модели для создания таблиц
    from models.deal import Deal  # noqa: F401
    from models.cash_allocation import CashAllocation  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Легкая миграция: добавляем колонку comment, если ее нет
    try:
        dialect = engine.dialect.name
        if "sqlite" in str(DATABASE_URL):
            with engine.connect() as conn:
                cols = conn.execute(text("PRAGMA table_info(payment_logs)")).fetchall()
                col_names = {row[1] for row in cols}  # row[1] = name
                if "comment" not in col_names:
                    conn.execute(text("ALTER TABLE payment_logs ADD COLUMN comment VARCHAR"))
                    conn.commit()
        else:
            # postgres / others
            with engine.connect() as conn:
                # Postgres supports IF NOT EXISTS
                conn.execute(text("ALTER TABLE payment_logs ADD COLUMN IF NOT EXISTS comment VARCHAR"))
                conn.commit()
    except Exception:
        # Не блокируем запуск приложения
        pass

    # Лёгкая миграция: добавляем колонку initial_payment в deals, если её нет
    try:
        if "sqlite" in str(DATABASE_URL):
            with engine.connect() as conn:
                cols = conn.execute(text("PRAGMA table_info(deals)")).fetchall()
                col_names = {row[1] for row in cols}
                if "initial_payment" not in col_names:
                    conn.execute(text("ALTER TABLE deals ADD COLUMN initial_payment INTEGER DEFAULT 0"))
                    conn.commit()
        else:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE deals ADD COLUMN IF NOT EXISTS initial_payment INTEGER DEFAULT 0"))
                conn.commit()
    except Exception:
        pass

    # Лёгкая миграция: фиксируем дату создания графика (schedule_start_date) и день платежа (schedule_day)
    try:
        if "sqlite" in str(DATABASE_URL):
            with engine.connect() as conn:
                cols = conn.execute(text("PRAGMA table_info(deals)")).fetchall()
                col_names = {row[1] for row in cols}
                if "schedule_start_date" not in col_names:
                    conn.execute(text("ALTER TABLE deals ADD COLUMN schedule_start_date DATETIME"))
                if "schedule_day" not in col_names:
                    conn.execute(text("ALTER TABLE deals ADD COLUMN schedule_day INTEGER DEFAULT 10"))
                conn.commit()
        else:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE deals ADD COLUMN IF NOT EXISTS schedule_start_date TIMESTAMP NULL"))
                conn.execute(text("ALTER TABLE deals ADD COLUMN IF NOT EXISTS schedule_day INTEGER DEFAULT 10"))
                conn.commit()
    except Exception:
        pass

    # Миграция данных: если раньше initial_payment писали в cash_allocations как month_index=0,
    # перенесём их в month_index=-1 (чтобы не влияли на месячные статусы графика).
    try:
        if "sqlite" in str(DATABASE_URL):
            with engine.connect() as conn:
                conn.execute(text("UPDATE cash_allocations SET month_index = -1 WHERE payment_id LIKE 'init_%'"))
                conn.commit()
        else:
            with engine.connect() as conn:
                conn.execute(text("UPDATE cash_allocations SET month_index = -1 WHERE payment_id LIKE 'init_%'"))
                conn.commit()
    except Exception:
        pass

    # Миграция: добавляем поле payment_date в payment_logs
    try:
        if "sqlite" in str(DATABASE_URL):
            with engine.connect() as conn:
                cols = conn.execute(text("PRAGMA table_info(payment_logs)")).fetchall()
                col_names = {row[1] for row in cols}
                if "payment_date" not in col_names:
                    conn.execute(text("ALTER TABLE payment_logs ADD COLUMN payment_date DATETIME"))
                conn.commit()
        else:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE payment_logs ADD COLUMN IF NOT EXISTS payment_date TIMESTAMP NULL"))
                conn.commit()
    except Exception:
        pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

