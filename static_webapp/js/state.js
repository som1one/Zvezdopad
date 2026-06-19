
// state.js
import { DEFAULT_SPIN_COST } from './config.js';

export const state = {
    // Wheel & Spin State
    currentSpinCost: DEFAULT_SPIN_COST, // Начальная стоимость
    sectors: [], // Массив секторов для отрисовки/демо
    currentRotation: 0, // Текущий угол поворота колеса (для сброса анимации)
    isSpinning: false, // Флаг, идет ли вращение в данный момент
    wheelSize: 300, // Размер колеса (будет обновляться)
    currentSpinId: null, // ID текущего спина от сервера
    currentWinningPrize: null, // Данные о выигрышном призе от сервера

    // User State
    userBalance: 0, // Баланс пользователя
    isFreeSpinAvailable: false, // Доступен ли бесплатный спин
    freeSpinCooldownEnd: null, // Timestamp (секунды) окончания кулдауна

    // App State
    dataLoaded: false, // Загружены ли начальные данные с сервера
    prizeActionPreference: 'ask', // Предпочтение пользователя ('ask', 'receive', 'sell')
};

// Функции для изменения состояния (опционально, но может быть полезно для сложной логики)
// Пока что будем изменять напрямую: state.isSpinning = true;

console.log("State module initialized with defaults.");