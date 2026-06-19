// static_webapp/js/target.js

function updateTargetProgress(current, target) {
    const progressBarEl = document.getElementById('target-progress-value');
    const progressLabelEl = document.getElementById('target-progress-label');

    if (!progressBarEl || !progressLabelEl) {
        console.warn("Target progress elements not found for update.");
        return;
    }

    const percentage = Math.min(100, Math.max(0, (current / target) * 100));

    progressBarEl.style.width = `${percentage}%`;
    progressLabelEl.textContent = `${current}/${target}`;
}

function updateTicketStatus(hasTickets) {
    const ticketStatusEl = document.getElementById('target-ticket-status');
    if (!ticketStatusEl) {
        console.warn("Target ticket status element not found.");
        return;
    }

    if (hasTickets) {
        ticketStatusEl.innerHTML = "У вас есть билеты! Ожидайте розыгрыша.";
    } else {
        ticketStatusEl.innerHTML = 'У вас пока нет билетов...<br/>Хотите поучаствовать - <a href="https://t.me/payZvezdopadtg_bot" target="_blank" class="target-topup-link">пополните баланс!</a>';
    }
}

export function initTargetTab() {
    console.log("Target tab activated/refreshed.");

    // --- ЗАГЛУШКИ ---
    const currentAmount = 1234; // Это значение потом будет приходить с сервера
    const targetAmount = 10000;  // Это значение тоже может быть динамическим
    const userHasRaffleTickets = false; // Это значение тоже будет с сервера
    // --- КОНЕЦ ЗАГЛУШЕК ---

    updateTargetProgress(currentAmount, targetAmount);
    updateTicketStatus(userHasRaffleTickets);

    // Дополнительная логика для вкладки "Цель", если нужна:
    // - Загрузка актуальных данных о прогрессе пользователя с сервера
    // - Отображение правил предстоящих розыгрышей и т.д.
    // - Анимации или интерактивные элементы
}

// Вызов initTargetTab при первоначальной загрузке, если вкладка "Цель" активна
// Это будет обработано в tabs.js через switchTab