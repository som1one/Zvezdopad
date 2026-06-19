// Содержимое файла: static_webapp/js/games.js (Исправлено: возвращен вызов updateStatusDisplay)
import { tg } from './dom.js';
import { state } from './state.js';
import { DEFAULT_SPIN_COST, PREFERENCE_STORAGE_KEY } from './config.js';
import { setActiveCostButton, updateStatusDisplay } from './ui.js'; // Убедитесь, что оба импортированы
import { buildSectors, updateWheelSizeAndRedraw } from './wheelRenderer.js';
import { playLuckGameApi, attemptRobberyApi, playSlotsApi } from './api.js';
import { formatDateTime, formatTimeLeft } from './utils.js';
import {
    handleSpinClick,
    handleCostChange,
    handleModeToggle,
    handlePrizeActionChange
} from './handlers.js';
// import { log } from './logger.js'; // Убедитесь, что это закомментировано или удалено

const gameContentArea       = document.getElementById('game-content-area');
const backToGamesBtn        = document.getElementById('back-to-games-btn');
const wheelThumbnail        = document.getElementById('game-wheel');
const luckThumbnail         = document.getElementById('game-luck');
const robberyThumbnail      = document.getElementById('game-robbery');
const slotsThumbnail        = document.getElementById('game-slots');
const gamesTabElement       = document.getElementById('games-tab');
const gamesContainer        = document.querySelector('#games-tab .games-container');
const activeGameContainer   = document.getElementById('active-game-container');

const initialWheelHtml = `
    <div id="balancePlaque">
        <div class="balanceRow">
            <div id="balanceInfo">
                <span class="balanceLabel">Баланс:</span>
                <span id="balanceValue">0 ⭐</span>
            </div>
        </div>
        <div id="freeSpinInfoPlaque" class="freeSpinInfoPlaque">Проверка...</div>
    </div>
    <div id="outerRing">
        <div id="wheelContainer">
            <canvas id="wheel"></canvas>
            <div id="topPointer"></div>
            <div id="centerDisc"></div>
        </div>
    </div>
    <hr class="divider"/>
    <div id="controls">
        <div id="spinCostBlock">
            <p>Стоимость прокрутки</p>
            <div class="costBtns">
                <button id="cost25Btn" class="costBtn" data-cost="25">25 ⭐</button>
                <button id="cost50Btn" class="costBtn" data-cost="50">50 ⭐</button>
                <button id="cost100Btn" class="costBtn" data-cost="100">100 ⭐</button>
            </div>
            <p class="cost-description">
                С повышением стоимости растёт
                <a href="https://telegra.ph/SHansy-vypadeniya-prizov-v-Kolese-Fortuny-ot-Zvezdopad-04-05"
                   target="_blank" rel="noopener noreferrer">
                    шанс
                </a> на призы.
            </p>
        </div>
        <fieldset id="prizeActionBlock">
            <legend>Действие при выигрыше подарка:</legend>
            <div class="prizeActionOptions">
                <label>
                    <input type="radio" name="prizeAction" value="ask"/>
                    Всегда спрашивать
                </label>
                <label>
                    <input type="radio" name="prizeAction" value="receive"/>
                    Всегда получать
                </label>
                <label>
                    <input type="radio" name="prizeAction" value="sell"/>
                    Всегда продавать
                </label>
            </div>
        </fieldset>
        <div id="modeToggleBlock">
            <span id="modeLabel">Игра на звезды</span>
            <label class="switch">
                <input type="checkbox" id="modeToggle"/>
                <span class="slider"></span>
            </label>
        </div>
    </div>
    <button id="spinBtn" disabled>Загрузка...</button>
    <div id="spinInfo">
        <p>
            Используя колесо, вы принимаете
            <a href="https://telegra.ph/User-Agreement-ZvezdoPadTG-Bot-04-05"
               target="_blank" rel="noopener noreferrer">
                Соглашение
            </a>.
        </p>
        <div id="spinResult" class="result-display"></div>
        <div id="spinActionConfirm" class="action-confirm" style="display: none;"></div>
    </div>
`;

let activeGameId = null;
let luckGameBetButtons = [];
let robberyCooldownInterval = null;
let slotsGameBetButtons = [];

// --- Функции createLuckGameUI, handleLuckGameBet, createRobberyGameUI, handleRobberyAttempt, startRobberyCooldownTimer, createSlotsGameUI, handleSlotsBet ---
// --- ОСТАЮТСЯ БЕЗ ИЗМЕНЕНИЙ ---
function createLuckGameUI() {
    if (!gameContentArea) return;
    gameContentArea.innerHTML = '';
    const container = document.createElement('div');
    container.className = 'luck-game-container';
    const title = document.createElement('h3');
    title.textContent = '🎲 Все или ничего';
    const rules = document.createElement('p');
    rules.className = 'luck-game-rules';
    rules.innerHTML = `
        Испытай удачу!
        Шанс выигрыша: <span>25%</span>.
        Возможный коэффициент: <span>x1.8 - x2.5</span>.
    `;
    const balanceDisplay = document.createElement('p');
    balanceDisplay.className = 'luck-game-balance';
    balanceDisplay.id = 'luck-game-current-balance';
    balanceDisplay.innerHTML = `
        Ваш баланс: <span>${state.userBalance.toFixed(2)} ⭐</span>
    `;
    const betsContainer = document.createElement('div');
    betsContainer.className = 'luck-game-bets';
    const betOptions = [1, 5, 10, 25, 50, 100, 250, 500, 1000];
    luckGameBetButtons = [];
    betOptions.forEach(bet => {
        const button = document.createElement('button');
        button.className = 'luck-bet-button';
        button.dataset.bet = bet;
        button.textContent = `${bet} ⭐`;
        button.disabled = state.userBalance < bet;
        betsContainer.appendChild(button);
        luckGameBetButtons.push(button);
    });
    const resultDisplay = document.createElement('div');
    resultDisplay.className = 'luck-game-result';
    resultDisplay.id = 'luck-game-result-display';
    resultDisplay.textContent = 'Выберите ставку';
    container.append(title, rules, balanceDisplay, betsContainer, resultDisplay);
    gameContentArea.appendChild(container);
    betsContainer.addEventListener('click', handleLuckGameBet);
}

async function handleLuckGameBet(event) {
    if (!event.target.matches('.luck-bet-button') || event.target.disabled) return;
    const betAmount = parseFloat(event.target.dataset.bet);
    if (isNaN(betAmount) || betAmount <= 0) return;

    const resultDisplay = document.getElementById('luck-game-result-display');
    const balanceDisplay = document.getElementById('luck-game-current-balance');

    if (!resultDisplay || !balanceDisplay) {
        console.error("Luck game UI elements not found!");
        return;
    }

    luckGameBetButtons.forEach(btn => (btn.disabled = true));
    resultDisplay.textContent = 'Думаем... 🤔';
    resultDisplay.className = 'luck-game-result info';
    tg?.HapticFeedback?.impactOccurred('light');

    const apiResult = await playLuckGameApi(betAmount);

    if(balanceDisplay) balanceDisplay.innerHTML = `Ваш баланс: <span>${state.userBalance.toFixed(2)} ⭐</span>`;

    const resultDelay = 1500;

    setTimeout(() => {
        if (!resultDisplay) return;

        if (apiResult?.ok) {
            if (apiResult.win) {
                resultDisplay.textContent = `🎉 Выигрыш +${apiResult.win_amount.toFixed(2)} ⭐ (x${apiResult.coefficient.toFixed(2)})!`;
                resultDisplay.className = 'luck-game-result win';
                tg?.HapticFeedback?.notificationOccurred('success');
            } else {
                resultDisplay.textContent = `😞 Проигрыш -${apiResult.bet.toFixed(0)} ⭐. Попробуйте еще!`;
                resultDisplay.className = 'luck-game-result loss';
                tg?.HapticFeedback?.notificationOccurred('warning');
            }
        } else {
            resultDisplay.textContent = `⚠️ ${apiResult?.error || 'Ошибка игры'}`;
            resultDisplay.className = 'luck-game-result loss';
            tg?.HapticFeedback?.notificationOccurred('error');
        }

        luckGameBetButtons.forEach(btn => {
            btn.disabled = state.userBalance < parseFloat(btn.dataset.bet);
        });

    }, resultDelay);
}


function createRobberyGameUI() {
    if (!gameContentArea) return;
    gameContentArea.innerHTML = '';
    const container = document.createElement('div');
    container.className = 'robbery-game-container';
    const title = document.createElement('h3');
    title.textContent = '🏃 Я Вор!';
    const rules = document.createElement('p');
    rules.className = 'robbery-game-rules';
    rules.innerHTML = `
        Попробуй украсть <span>2%</span> звезд у случайного игрока!
        Кулдаун: <span>12 часов</span>.
        Для попытки нужно <span>5 ⭐</span> на балансе.
    `;
    const balanceDisplay = document.createElement('p');
    balanceDisplay.className = 'luck-game-balance';
    balanceDisplay.id = 'robbery-game-current-balance';
    balanceDisplay.innerHTML = `Ваш баланс: <span>${state.userBalance.toFixed(2)} ⭐</span>`;
    const attemptButton = document.createElement('button');
    attemptButton.id = 'robbery-attempt-btn';
    attemptButton.textContent = 'Ограбить!';
    const cooldownLeft = state.profileData?.robbery_cooldown_left ?? 0;
    attemptButton.disabled = state.userBalance < 5.0 || cooldownLeft > 0;
    const resultDisplay = document.createElement('div');
    resultDisplay.id = 'robbery-result-display';
    resultDisplay.className = 'robbery-game-result info';
    resultDisplay.textContent = 'Готов рискнуть?';
    const cooldownDisplay = document.createElement('p');
    cooldownDisplay.id = 'robbery-cooldown-timer';
    cooldownDisplay.className = 'robbery-cooldown-timer';
    container.append(title, rules, balanceDisplay, attemptButton, resultDisplay, cooldownDisplay);
    gameContentArea.appendChild(container);
    attemptButton.addEventListener('click', handleRobberyAttempt);
    if (cooldownLeft > 0) {
        startRobberyCooldownTimer(cooldownLeft);
    }
}

async function handleRobberyAttempt() {
    const attemptButton = document.getElementById('robbery-attempt-btn');
    const resultDisplay = document.getElementById('robbery-result-display');
    const balanceDisplay = document.getElementById('robbery-game-current-balance');
    if(attemptButton) attemptButton.disabled = true;
    if(resultDisplay) resultDisplay.textContent = 'Ищем жертву... 🕵️';
    if(resultDisplay) resultDisplay.className = 'robbery-game-result info';
    tg?.HapticFeedback?.impactOccurred('medium');
    const result = await attemptRobberyApi();
    if(balanceDisplay) balanceDisplay.innerHTML = `Ваш баланс: <span>${state.userBalance.toFixed(2)} ⭐</span>`;
    if (result?.ok) {
        if (result.success) {
           if(resultDisplay) resultDisplay.textContent = `✅ ${result.message}`;
           if(resultDisplay) resultDisplay.className = 'robbery-game-result win';
            tg?.HapticFeedback?.notificationOccurred('success');
        } else {
           if(resultDisplay) resultDisplay.textContent = `ℹ️ ${result.message}`;
           if(resultDisplay) resultDisplay.className = 'robbery-game-result info';
            tg?.HapticFeedback?.notificationOccurred('warning');
        }
        if (result.cooldown_applied > 0) {
            startRobberyCooldownTimer(result.cooldown_applied);
        } else {
            if (attemptButton) attemptButton.disabled = state.userBalance < 5.0;
        }
    } else {
       if(resultDisplay) resultDisplay.textContent = `⚠️ ${result?.error || 'Неизвестная ошибка'}`;
       if(resultDisplay) resultDisplay.className = 'robbery-game-result loss';
        tg?.HapticFeedback?.notificationOccurred('error');
        if (result?.reason === 'cooldown' && result.cooldown_left > 0) {
            startRobberyCooldownTimer(result.cooldown_left);
        } else {
             if (attemptButton) attemptButton.disabled = state.userBalance < 5.0;
        }
    }
}

function startRobberyCooldownTimer(totalSeconds) {
    const attemptButton   = document.getElementById('robbery-attempt-btn');
    const cooldownDisplay = document.getElementById('robbery-cooldown-timer');
    if (robberyCooldownInterval) {
        clearInterval(robberyCooldownInterval);
        robberyCooldownInterval = null;
    }
    if (totalSeconds <= 0) {
        if(cooldownDisplay) cooldownDisplay.textContent = '';
        if (attemptButton) attemptButton.disabled = state.userBalance < 5.0;
        if (attemptButton) attemptButton.dataset.cooldown = 'false';
        return;
    }
    if (attemptButton) attemptButton.disabled = true;
    if (attemptButton) attemptButton.dataset.cooldown = 'true';
    let remainingSeconds = Math.floor(totalSeconds);
    function updateTimer() {
        const currentAttemptButton = document.getElementById('robbery-attempt-btn');
        const currentCooldownDisplay = document.getElementById('robbery-cooldown-timer');
        if (remainingSeconds <= 0) {
            clearInterval(robberyCooldownInterval);
            robberyCooldownInterval = null;
            if (currentCooldownDisplay) currentCooldownDisplay.textContent = '';
            if (currentAttemptButton) currentAttemptButton.disabled = state.userBalance < 5.0;
            if (currentAttemptButton) currentAttemptButton.dataset.cooldown = 'false';
        } else {
            if (currentCooldownDisplay) currentCooldownDisplay.textContent = `Следующая попытка через: ${formatTimeLeft(remainingSeconds)}`;
            remainingSeconds--;
        }
    }
    updateTimer();
    robberyCooldownInterval = setInterval(updateTimer, 1000);
}

function createSlotsGameUI() {
    if (!gameContentArea) return;
    gameContentArea.innerHTML = '';
    const container = document.createElement('div');
    container.className = 'slots-game-container';
    const title = document.createElement('h3');
    title.textContent = '🎰 Слоты';
    const balanceDisplay = document.createElement('p');
    balanceDisplay.className = 'slots-game-balance';
    balanceDisplay.id = 'slots-game-current-balance';
    balanceDisplay.innerHTML = `Ваш баланс: <span>${state.userBalance.toFixed(2)} ⭐</span>`;
    const slotsDisplay = document.createElement('div');
    slotsDisplay.className = 'slots-display';
    slotsDisplay.id = 'slots-visual-display';
    slotsDisplay.innerHTML = `
        <span class="slot-item">❓</span>
        <span class="slot-item">❓</span>
        <span class="slot-item">❓</span>
    `;
    const betsContainer = document.createElement('div');
    betsContainer.className = 'slots-game-bets';
    const betOptions = [1, 5, 10, 25, 50, 100];
    slotsGameBetButtons = [];
    betOptions.forEach(bet => {
        const button = document.createElement('button');
        button.className = 'luck-bet-button slots-bet-button';
        button.dataset.bet = bet;
        button.textContent = `${bet} ⭐`;
        button.disabled = state.userBalance < bet;
        betsContainer.appendChild(button);
        slotsGameBetButtons.push(button);
    });
    const resultDisplay = document.createElement('div');
    resultDisplay.className = 'slots-game-result';
    resultDisplay.id = 'slots-game-result-display';
    resultDisplay.textContent = 'Выберите ставку';
    container.append(title, balanceDisplay, slotsDisplay, betsContainer, resultDisplay);
    gameContentArea.appendChild(container);
    betsContainer.addEventListener('click', handleSlotsBet);
}

async function handleSlotsBet(event) {
    if (!event.target.matches('.slots-bet-button') || event.target.disabled) return;
    const betAmount = parseFloat(event.target.dataset.bet);
    if (isNaN(betAmount) || betAmount <= 0) return;

    const resultDisplay = document.getElementById('slots-game-result-display');
    const balanceDisplay = document.getElementById('slots-game-current-balance');
    const slotsVisualDisplay = document.getElementById('slots-visual-display');

    if (!resultDisplay || !balanceDisplay || !slotsVisualDisplay) {
        console.error("Slots game UI elements not found!");
        return;
    }

    slotsGameBetButtons.forEach(btn => (btn.disabled = true));
    resultDisplay.textContent = 'Крутим барабаны... 🎰';
    resultDisplay.className = 'slots-game-result info';

    let spinInterval = null;
    let apiResult = null;
    let isApiFinished = false;
    const minSpinDuration = 2500;
    const spinStartTime = Date.now();

    const emojis = ['🎰', '🍒', '💰', '💎', '🍋', '🎁', '⭐', '💔', '🍀'];
    const slotItems = slotsVisualDisplay.querySelectorAll('.slot-item');
    spinInterval = setInterval(() => {
        slotItems.forEach(slot => {
            slot.textContent = emojis[Math.floor(Math.random() * emojis.length)];
        });
    }, 100);

    tg?.HapticFeedback?.impactOccurred('medium');

    playSlotsApi(betAmount).then(res => {
        apiResult = res;
        isApiFinished = true;
        if (res && typeof res.new_balance === 'number') {
            state.userBalance = res.new_balance;
            console.log(`Slots: Balance updated in state to ${state.userBalance} after API response.`);
        }
        console.debug("Slots API finished."); // Используем console
    }).catch(err => {
        console.error("Slots API error:", err); // Используем console
        apiResult = { ok: false, error: `Ошибка сети: ${err.message || "?"}`, reason: 'network_error' };
        isApiFinished = true;
    });

    const finalizeSpin = () => {
        clearInterval(spinInterval);
        console.debug("Slots: Finalizing spin."); // Используем console

        if(balanceDisplay) balanceDisplay.innerHTML = `Ваш баланс: <span>${state.userBalance.toFixed(2)} ⭐</span>`;

        if (apiResult?.ok) {
            if (Array.isArray(apiResult.result_emojis) && apiResult.result_emojis.length === 3) {
                slotItems.forEach((slot, i) => {
                    slot.textContent = apiResult.result_emojis[i] || '❓';
                });
            } else {
                slotItems.forEach(s => (s.textContent = '❓'));
            }

            if (apiResult.win) {
                if(resultDisplay) resultDisplay.textContent = `🎉 Выигрыш +${apiResult.win_amount.toFixed(2)} ⭐ (x${(apiResult.coefficient ?? '?').toFixed(2)})!`;
                if(resultDisplay) resultDisplay.className = 'slots-game-result win';
                tg?.HapticFeedback?.notificationOccurred('success');
            } else {
                if(resultDisplay) resultDisplay.textContent = `😞 Увы, не повезло. Баланс: ${state.userBalance.toFixed(2)} ⭐`;
                if(resultDisplay) resultDisplay.className = 'slots-game-result loss';
                tg?.HapticFeedback?.notificationOccurred('warning');
            }
        } else {
            slotItems.forEach(s => (s.textContent = '💥'));
            if(resultDisplay) resultDisplay.textContent = `⚠️ ${apiResult?.error || 'Ошибка игры'}`;
            if(resultDisplay) resultDisplay.className   = 'slots-game-result loss';
            tg?.HapticFeedback?.notificationOccurred('error');
        }
        slotsGameBetButtons.forEach(btn => {
            btn.disabled = state.userBalance < parseFloat(btn.dataset.bet);
        });
    };

    const checkCompletion = () => {
        const elapsedTime = Date.now() - spinStartTime;
        if (isApiFinished && elapsedTime >= minSpinDuration) {
            finalizeSpin();
        } else {
            setTimeout(checkCompletion, 100);
        }
    };

    checkCompletion();
}
// --- КОНЕЦ: Функции для других игр ---


function createWheelGameUI() {
    if (!gameContentArea) return;
    gameContentArea.innerHTML = initialWheelHtml;
    const spinBtn = document.getElementById('spinBtn');
    const costBtnsContainer = gameContentArea.querySelector(".costBtns");
    const prizeActionContainer = document.getElementById("prizeActionBlock");
    const modeToggle = document.getElementById("modeToggle");
    const canvas = document.getElementById('wheel');

    if (!spinBtn || !costBtnsContainer || !prizeActionContainer || !modeToggle || !canvas) {
        gameContentArea.innerHTML = '<p class="error-placeholder">Ошибка загрузки интерфейса Колеса Фортуны.</p>';
        return;
    }

    // Attach event listeners
    spinBtn.addEventListener("click", handleSpinClick);
    costBtnsContainer.addEventListener('click', handleCostChange);
    prizeActionContainer.addEventListener('change', handlePrizeActionChange);
    modeToggle.addEventListener("change", handleModeToggle);

    // Initialize state/UI elements
    state.sectors = buildSectors(state.currentSpinCost);
    modeToggle.checked = true;

    // Set default prize preference radio button
    const savedPref = localStorage.getItem(PREFERENCE_STORAGE_KEY);
    state.prizeActionPreference = (savedPref && ["ask", "receive", "sell"].includes(savedPref)) ? savedPref : 'ask';
    const currentPrefRadio = prizeActionContainer.querySelector(`input[name="prizeAction"][value="${state.prizeActionPreference}"]`);
    if (currentPrefRadio) {
        currentPrefRadio.checked = true;
    } else {
        const askRadio = prizeActionContainer.querySelector(`input[name="prizeAction"][value="ask"]`);
        if (askRadio) {
            askRadio.checked = true;
            state.prizeActionPreference = 'ask';
            localStorage.setItem(PREFERENCE_STORAGE_KEY, state.prizeActionPreference);
        }
    }

    // Set initial active cost button
    const defaultCostButton = costBtnsContainer.querySelector(`.costBtn[data-cost="${state.currentSpinCost}"]`);
    if (defaultCostButton) {
        setActiveCostButton(defaultCostButton);
        console.log(`Default cost button ${state.currentSpinCost} set as active.`);
    } else {
        const fallbackButton = costBtnsContainer.querySelector('.costBtn');
        if (fallbackButton) {
             setActiveCostButton(fallbackButton);
             console.warn(`Default cost button for ${state.currentSpinCost} not found, activating first button.`);
        } else {
             console.error("No cost buttons found to activate.");
        }
    }

    // Update wheel graphics and FULL status display (including balance)
    if (activeGameId === 'game-wheel' && document.getElementById('wheel')) {
         updateWheelSizeAndRedraw();
         updateStatusDisplay(); // <--- ВОЗВРАЩАЕМ ЭТОТ ВЫЗОВ
    }
}


function showGame(gameId, gameTitle = 'Игра') {
    if (!activeGameContainer || !gamesContainer || !gameContentArea) {
        console.error("Required containers not found for showGame");
        return;
    }

    activeGameId = gameId;

    if (robberyCooldownInterval) {
        clearInterval(robberyCooldownInterval);
        robberyCooldownInterval = null;
    }

    gameContentArea.innerHTML = `<div class="game-loader">Загрузка "${gameTitle}"...</div>`;
    gamesContainer.style.display = 'none';
    activeGameContainer.style.display = 'block';
    gsap.set(activeGameContainer, { opacity: 0 });

    requestAnimationFrame(() => {
        if (activeGameId !== gameId) return; // Проверка, что игра не сменилась пока ждали frame

        switch (gameId) {
            case 'game-wheel':
                createWheelGameUI(); // Вызываем функцию создания UI для колеса
                break;
            case 'game-luck':
                createLuckGameUI();
                break;
            case 'game-robbery':
                createRobberyGameUI();
                break;
            case 'game-slots':
                createSlotsGameUI();
                break;
            default:
                gameContentArea.innerHTML = `<p class="error-placeholder">Игра "${gameTitle}" не найдена.</p>`;
        }

        // Анимация появления контейнера игры
        gsap.to(activeGameContainer, { opacity: 1, duration: 0.3, ease: "power1.inOut" });
    });

    tg?.HapticFeedback?.impactOccurred('light');
}

function hideActiveGame() {
    if (!activeGameContainer || !gamesContainer || !gameContentArea) {
        console.error("Required containers not found for hideActiveGame");
        return;
    }
    activeGameId = null;

    if (robberyCooldownInterval) {
        clearInterval(robberyCooldownInterval);
        robberyCooldownInterval = null;
    }

    // Анимация исчезновения контейнера игры
    gsap.to(activeGameContainer, {
        opacity: 0,
        duration: 0.3,
        ease: "power1.inOut",
        onComplete: () => {
            activeGameContainer.style.display = 'none'; // Скрываем контейнер игры
            gameContentArea.innerHTML = ''; // Очищаем его содержимое
            gamesContainer.style.display = 'block'; // Показываем контейнер со списком игр
            gsap.set(gamesContainer, { opacity: 1 }); // Устанавливаем его видимость
        }
    });

    tg?.HapticFeedback?.selectionChanged();
}

export function initGamesTab() {
    if (!wheelThumbnail || !backToGamesBtn || !luckThumbnail || !robberyThumbnail || !slotsThumbnail || !gamesContainer || !activeGameContainer) {
        const gamesTab = document.getElementById('games-tab') || document.body;
        if (gamesTab) gamesTab.innerHTML = '<p class="error-placeholder">Ошибка инициализации вкладки Игр (не найдены элементы).</p>';
        console.error("Failed to initialize Games Tab - missing elements");
        return;
    }

    // Установка обработчиков кликов на миниатюры игр
    wheelThumbnail.addEventListener('click', () => showGame('game-wheel', 'Колесо Фортуны'));
    luckThumbnail.addEventListener('click', () => showGame('game-luck', 'Все или Ничего'));
    robberyThumbnail.addEventListener('click', () => showGame('game-robbery', 'Я Вор!'));
    slotsThumbnail.addEventListener('click', () => showGame('game-slots', 'Слоты'));

    // Установка обработчика на кнопку "Назад"
    backToGamesBtn.addEventListener('click', hideActiveGame);

    // Начальное состояние: показываем список игр, скрываем контейнер активной игры
    activeGameContainer.style.display = 'none';
    gamesContainer.style.display = 'block';
    gsap.set(activeGameContainer, { opacity: 0 });
    gsap.set(gamesContainer, { opacity: 1 });

    console.log("Games tab initialized.");
}