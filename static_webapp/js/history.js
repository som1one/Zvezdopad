import { tg } from './dom.js';
import { state } from './state.js';
import { GET_GAME_HISTORY_ENDPOINT } from './config.js';
import { getInitDataString } from './api.js';
import { formatDateTime } from './utils.js';

const historyListEl = document.getElementById('game-history-list');
const noHistoryEl = document.getElementById('no-game-history');
const historyContentEl = document.querySelector('#history-tab .history-content');

let isLoading = false;

function renderGameHistory(historyItems) {
    if (!historyListEl || !noHistoryEl || !historyContentEl) {
        console.error("History list, no-history element, or history content not found in renderGameHistory");
        return;
    }

    const gameTypeEmojis = {
        'wheel': '🎡',
        'luck': '🎲',
        'robbery': '🏃',
        'slots': '🎰',
        'clicker': '🖱️',
        'gift': '🎁',
        'promocode': '🎫',
        'referral': '👥',
        'admin': '⚙️',
        'spin_result': '🎁',
        'spin_result_sell': '💰',
        'unknown': '❓'
    };

    historyListEl.innerHTML = '';

    if (!historyItems || historyItems.length === 0) {
        noHistoryEl.style.display = 'block';
        historyListEl.style.display = 'none';
    } else {
        noHistoryEl.style.display = 'none';
        historyListEl.style.display = 'block';
        historyItems.forEach(item => {
            const li = document.createElement('li');
            li.classList.add('game-history-item');

            const amount = item.amount || 0;
            let amountClass = 'neutral';
            let amountSign = '';
            if (amount > 0) {
                amountClass = 'win';
                amountSign = '+';
                li.classList.add('win');
            } else if (amount < 0) {
                amountClass = 'loss';
                li.classList.add('loss');
            } else {
                li.classList.add('neutral');
            }

            const gameType = item.game_type || 'unknown';
            const description = item.description || `Действие (${gameType})`;

            const gameEmoji = gameTypeEmojis[gameType] || gameTypeEmojis['unknown'];
            const gameTypeLabel = gameType.charAt(0).toUpperCase() + gameType.slice(1);

            const amountDisplay = amount.toFixed(amount % 1 === 0 ? 0 : 2);

            li.innerHTML = `
                <div class="history-details">
                    <span class="history-description">
                        ${gameEmoji} <span class="game-type-label" style="display: none;">${gameTypeLabel}</span> ${description}
                    </span>
                    <span class="history-timestamp">${formatDateTime(item.timestamp)}</span>
                </div>
                <span class="history-amount ${amountClass}">${amountSign}${amountDisplay} ⭐</span>
            `;

            historyListEl.appendChild(li);
        });
    }

    setTimeout(() => {
        historyContentEl.classList.add('loaded');
    }, 50);
}


function renderError(message) {
    if (!historyListEl || !noHistoryEl || !historyContentEl) {
        console.error("History elements not found in renderError");
        return;
    }
    historyListEl.innerHTML = `<li class="error-placeholder">${message}</li>`;
    noHistoryEl.style.display = 'none';
    historyListEl.style.display = 'block';
    setTimeout(() => {
        historyContentEl.classList.add('loaded');
    }, 50);
}

export async function loadGameHistory() {
    if (isLoading) {
        console.log("History loading is already in progress.");
        return;
    }
    if (!historyListEl || !noHistoryEl || !historyContentEl) {
        console.error("Required history elements not found.");
        return;
    }

    isLoading = true;
    console.log("Fetching game history...");

    historyContentEl.classList.remove('loaded');

    historyListEl.innerHTML = '<li class="loading-placeholder">Загрузка истории...</li>';
    noHistoryEl.style.display = 'none';
    historyListEl.style.display = 'block';

    const initDataStr = getInitDataString();
    if (!initDataStr) {
        renderError("Ошибка: Нет данных пользователя.");
        isLoading = false;
        return;
    }

    try {
        const response = await fetch(GET_GAME_HISTORY_ENDPOINT, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ initData: initDataStr, limit: 30 })
        });

        if (!response.ok) {
            let errorText = `Ошибка HTTP: ${response.status}`;
            try {
                const errorData = await response.json();
                errorText = errorData?.error || errorText;
            } catch (e) {
                console.warn("Could not parse error response JSON:", e);
            }
            throw new Error(errorText);
        }

        const data = await response.json();

        if (data && data.ok && Array.isArray(data.history)) {
            console.log("Game history received:", data.history);
            renderGameHistory(data.history);
        } else {
            console.error("Failed to fetch game history or invalid data format:", data);
            renderError(data?.error || "Не удалось загрузить историю (неверный формат ответа).");
        }

    } catch (error) {
        console.error("Error fetching game history:", error);
        renderError(`Ошибка сети или сервера: ${error.message}`);
    } finally {
        isLoading = false;
    }
}

export function initHistoryTab() {
    console.log("History tab initialized (data will load on activation).");
}