import {
    tg, appContainer, errorMessageEl
} from './dom.js';
import { state } from './state.js';
import { PREFERENCE_STORAGE_KEY, DEFAULT_SPIN_COST } from './config.js';
import { fetchUserState } from './api.js';
import {
    createAudioElements, updateStatusDisplay,
    startCooldownTimer, stopCooldownTimer
} from './ui.js';
import {
    handleResize, handleGlobalError, handleUnhandledRejection
} from './handlers.js';
import { setupTabs } from './tabs.js';
import { initProfileTab, loadProfileData } from './profile.js';
import { initHistoryTab, loadGameHistory } from './history.js';
import { initGamesTab } from './games.js';
import { initTheme } from './theme.js';
import { initTargetTab } from './target.js';


export function forceResetState() {
    console.warn("%c--- Force Resetting Application Spin State ---", "background:#ffdddd; color: #a60000; font-weight: bold;");
    try {
        const wheelElement = document.getElementById('wheel');
        if (window.gsap && wheelElement) {
            gsap.killTweensOf(wheelElement);
        }
        state.isSpinning = false;
        state.currentSpinId = null;
        state.currentWinningPrize = null;
        if (wheelElement && typeof resetWheelVisuals !== 'undefined') { // Проверка на существование функции
            resetWheelVisuals();
        }
        updateStatusDisplay();
    } catch (error) {
        console.error("Error during forceResetState:", error);
        const spinButton = document.getElementById('spinBtn');
        if (spinButton) spinButton.disabled = false;
        if (appContainer) appContainer.classList.remove("loading");
    } finally {
        if (appContainer) appContainer.classList.remove("loading");
        console.warn("%c--- Reset Complete ---", "background:#ddffdd; color: #006300; font-weight: bold;");
    }
}

function showCaptchaOverlay() {
    return new Promise((resolve) => {
        const overlay = document.getElementById('captcha-overlay');
        const questionEl = document.getElementById('captcha-question');
        const buttonsEl = document.getElementById('captcha-buttons');
        const errorEl = document.getElementById('captcha-error');

        if (!overlay || !questionEl || !buttonsEl) { resolve(true); return; }

        const ops = [
            ['+', (a, b) => a + b],
            ['-', (a, b) => a - b],
            ['×', (a, b) => a * b]
        ];
        const [sym, fn] = ops[Math.floor(Math.random() * ops.length)];
        let a, b;
        if (sym === '×') { a = 2 + Math.floor(Math.random() * 8); b = 2 + Math.floor(Math.random() * 8); }
        else if (sym === '-') { a = 5 + Math.floor(Math.random() * 16); b = 1 + Math.floor(Math.random() * a); }
        else { a = 1 + Math.floor(Math.random() * 20); b = 1 + Math.floor(Math.random() * 20); }
        const correct = fn(a, b);

        questionEl.textContent = `${a} ${sym} ${b} = ?`;

        const wrongs = new Set();
        while (wrongs.size < 3) {
            const w = correct + Math.floor(Math.random() * 11) - 5;
            if (w !== correct) wrongs.add(w);
        }
        const answers = [correct, ...wrongs].sort(() => Math.random() - 0.5);

        buttonsEl.innerHTML = '';
        answers.forEach(ans => {
            const btn = document.createElement('button');
            btn.textContent = ans;
            btn.style.cssText = 'padding:12px; font-size:18px; border-radius:8px; border:none; background:#3a3a5e; color:#fff; cursor:pointer; font-weight:bold;';
            btn.onclick = () => {
                if (ans === correct) {
                    overlay.style.display = 'none';
                    resolve(true);
                } else {
                    errorEl.style.display = 'block';
                    setTimeout(() => { errorEl.style.display = 'none'; }, 1500);
                }
            };
            buttonsEl.appendChild(btn);
        });

        overlay.style.display = 'flex';
    });
}

async function initializeApp() {
    // --- Капча перед загрузкой приложения ---
    const captchaPassed = await showCaptchaOverlay();
    if (!captchaPassed) return;
    // -----------------------------------------

    initTheme();

    if (!appContainer || !errorMessageEl) {
        document.body.innerHTML = '<p style="color:red; padding: 20px; text-align: center;">Критическая ошибка: Не найдены основные элементы интерфейса. Перезагрузите приложение.</p>';
        return;
    }

    try {
        appContainer.classList.remove("loading", "error");
        errorMessageEl.style.display = "none";
        errorMessageEl.textContent = '';

        if (tg?.expand) {
             tg.expand();
        }
        createAudioElements();

        appContainer.classList.add("loading");
        const serverState = await fetchUserState();
        appContainer.classList.remove("loading");

        if (serverState && serverState.ok) {
            state.userBalance = serverState.balance ?? 0;
            state.isFreeSpinAvailable = serverState.freeSpin ?? false;
            state.freeSpinCooldownEnd = serverState.cooldown ?? null;
            state.profileData = {
                username: serverState.username,
                user_id: serverState.user_id,
                photo_url: serverState.photo_url,
                total_referrals: serverState.total_referrals,
                weekly_referrals: serverState.weekly_referrals,
                withdrawal_requirement: serverState.withdrawal_requirement,
                withdrawal_history: serverState.withdrawal_history,
                robbery_cooldown_left: serverState.robbery_cooldown_left ?? 0
            };
        } else {
            const errorMsg = serverState?.error || "Ошибка загрузки данных с сервера.";
            tg?.showAlert(errorMsg);
            errorMessageEl.textContent = errorMsg;
            errorMessageEl.style.display = "block";
            appContainer.classList.add("error");
            state.profileData = null;
        }
        state.dataLoaded = true;

        const savedPref = localStorage.getItem(PREFERENCE_STORAGE_KEY);
        state.prizeActionPreference = (savedPref && ["ask", "receive", "sell"].includes(savedPref)) ? savedPref : 'ask';
        localStorage.setItem(PREFERENCE_STORAGE_KEY, state.prizeActionPreference);
        state.currentSpinCost = DEFAULT_SPIN_COST;

        updateStatusDisplay();
        startCooldownTimer();

        initProfileTab();
        initHistoryTab();
        initGamesTab();

        const activeTabButton = document.querySelector('#tab-bar .tab-button.active');
        if (activeTabButton) {
            const activeTabId = activeTabButton.dataset.tab;
            if (activeTabId === 'profile-tab') {
                loadProfileData();
            } else if (activeTabId === 'history-tab') {
                loadGameHistory();
            } else if (activeTabId === 'target-tab') {
                initTargetTab();
            }
        }


        window.addEventListener("resize", handleResize);
        window.onerror = handleGlobalError;
        window.addEventListener("unhandledrejection", handleUnhandledRejection);

    } catch (initError) {
        console.error("!!! APPLICATION INITIALIZATION ERROR !!!", initError);
        appContainer.classList.remove("loading");
        appContainer.classList.add("error");
        const errorDisplayMessage = `Критическая ошибка инициализации: ${initError.message || initError}`;
        errorMessageEl.textContent = errorDisplayMessage;
        errorMessageEl.style.display = "block";
        stopCooldownTimer();
        try {
            const errorData = {
                action: "js_init_error",
                error: { message: initError?.message, stack: initError?.stack, name: initError?.name },
                timestamp: new Date().toISOString()
            };
            tg?.sendData && tg.sendData(JSON.stringify(errorData));
        } catch (reportError) {
            console.error("Failed to report initialization error:", reportError);
        }
    }
}

document.addEventListener("DOMContentLoaded", () => {
    console.log(`%cDOM ready. Initializing ${document.title || 'Application'}...`, "font-weight: bold; color: #0d47a1;");
    setupTabs();
    if (window.Telegram?.WebApp || window.location.hostname === 'localhost') {
        if (window.Telegram?.WebApp) {
            window.Telegram.WebApp.ready();
        } else {
            console.warn("Running locally without Telegram WebApp API.");
        }
        initializeApp();
    } else {
        console.error("Telegram WebApp API (window.Telegram.WebApp) not found! Cannot initialize.");
        document.body.innerHTML = '<p style="color: red; padding: 20px; text-align: center;">Ошибка: Пожалуйста, запустите это приложение через Telegram.</p>';
    }
});