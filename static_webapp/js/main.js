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

async function initializeApp() {
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