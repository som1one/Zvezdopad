from aiogram.fsm.state import State, StatesGroup


class PaymentStates(StatesGroup):
    waiting_for_topup_amount = State()
    choosing_boost = State()

