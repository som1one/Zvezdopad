// js/api.js
import { tg } from './dom.js';
import {
    GET_STATE_ENDPOINT,
    START_SPIN_ENDPOINT,
    CONFIRM_ACTION_ENDPOINT,
    FREE_SPIN_COOLDOWN_SECONDS,
    PLAY_LUCK_GAME_ENDPOINT,
    ATTEMPT_ROBBERY_ENDPOINT,
    PLAY_SLOTS_ENDPOINT // <--- Импорт нового эндпоинта
} from './config.js';
import { state } from './state.js';

export function getInitDataString() {
    return tg && tg.initData ? tg.initData
        : tg && tg.initDataUnsafe && tg.initDataUnsafe.initData ? tg.initDataUnsafe.initData
        : (console.error("TG initData not found."), null);
}

function logServerResponse(endpoint, status, data) {
    const statusColor = status >= 200 && status < 300 ? 'green' : 'red';
    console.log(`%cResponse from ${endpoint} [${status}]:`, `color: ${statusColor}; font-weight: bold;`, data);
}

export async function fetchUserState() {
    console.log("%cFetching user state...", "color: purple;");
    const initDataStr = getInitDataString();
    if (!initDataStr) {
        console.error("TG initData not available for fetch user state.");
        return null;
    }
    try {
        const response = await fetch(GET_STATE_ENDPOINT, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ initData: initDataStr })
        });
        const data = await response.json();
        logServerResponse(GET_STATE_ENDPOINT, response.status, data);
        if (response.ok && data.ok) {
            return data;
        } else {
            console.error("Server error fetching state:", data?.error || `Status ${response.status}`);
            return null;
        }
    } catch (error) {
        console.error("Network error fetching state:", error);
        return null;
    }
}

export async function requestStartSpinFromServer(costValue, isFree) {
    console.log(`%cRequesting START SPIN: cost=${costValue}, free=${isFree}`, "color: blue; font-weight: bold;");
    const initDataStr = getInitDataString();
    if (!initDataStr) {
        console.error("TG initData not available for start spin.");
        tg?.showAlert("Ошибка: Нет данных пользователя.");
        return { ok: false, error: "Нет данных пользователя." };
    }
    const payload = {
        initData: initDataStr,
        cost: isFree ? 'free' : String(costValue)
    };
    try {
        const response = await fetch(START_SPIN_ENDPOINT, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const responseData = await response.json();
        logServerResponse(START_SPIN_ENDPOINT, response.status, responseData);

        if (!response.ok || !responseData.ok) {
            const errorMsg = responseData?.error || `Ошибка сервера (${response.status})`;
            return { ok: false, error: errorMsg, reason: responseData?.reason };
        }
        console.log("%cSTART SPIN OK:", "color: green;", responseData);
        if (typeof responseData.new_balance === 'number') {
            state.userBalance = responseData.new_balance;
             console.log(`Local balance updated to: ${state.userBalance} from start_spin response.`);
        }
        if (isFree) {
            console.log("Server confirmed FREE spin usage. Updating local state immediately.");
            state.isFreeSpinAvailable = false;
            state.freeSpinCooldownEnd = Math.floor(Date.now() / 1000) + FREE_SPIN_COOLDOWN_SECONDS;
            console.log("New cooldown end timestamp (local):", state.freeSpinCooldownEnd, new Date(state.freeSpinCooldownEnd * 1000));
        }

        return responseData;
    } catch (error) {
        console.error("Fetch error starting spin:", error);
        const errorMsg = `Ошибка сети: ${error.message || "?"}`;
        return { ok: false, error: errorMsg, reason: 'network_error' };
    }
}

export async function confirmSpinActionWithServer(spinId, actionChoice) {
    console.log(`%cConfirming ACTION '${actionChoice}' for spin ${spinId}...`, "color: blue;");
    const initDataStr = getInitDataString();
    if (!initDataStr) {
        console.error("TG initData not available for confirm action.");
        return { ok: false, error: "Нет данных пользователя." };
    }
    const payload = {
        initData: initDataStr,
        spin_id: spinId,
        action: actionChoice
    };
    try {
        const response = await fetch(CONFIRM_ACTION_ENDPOINT, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const responseData = await response.json();
        logServerResponse(CONFIRM_ACTION_ENDPOINT, response.status, responseData);

        if (responseData && typeof responseData.new_balance === 'number') {
            state.userBalance = responseData.new_balance;
            console.log(`Local balance updated to: ${state.userBalance} from confirm response (status ${response.status}).`);
        } else {
             console.warn("new_balance not found or invalid in confirm action response:", responseData);
        }

        if (!response.ok || !responseData.ok) {
            const errorMsg = responseData?.error || `Ошибка сервера (${response.status})`;
            console.error("Confirm spin action failed:", errorMsg);
            return { ok: false, error: errorMsg, was_free: responseData?.was_free ?? false };
        }

        console.log("%cCONFIRM ACTION OK:", "color: green;", responseData);
        return responseData;

    } catch (error) {
        console.error("Fetch error confirming action:", error);
        const errorMsg = `Ошибка сети: ${error.message || "?"}`;
        return { ok: false, error: errorMsg };
    }
}

export async function playLuckGameApi(betAmount) {
    console.log(`%cRequesting PLAY LUCK GAME: bet=${betAmount}`, "color: blue; font-weight: bold;");
    const initDataStr = getInitDataString();
    if (!initDataStr) {
        console.error("TG initData not available for luck game.");
        tg?.showAlert("Ошибка: Нет данных пользователя.");
        return null; // Changed from null to consistent error object
    }

    const payload = {
        initData: initDataStr,
        bet: String(betAmount)
    };

    try {
        const response = await fetch(PLAY_LUCK_GAME_ENDPOINT, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const responseData = await response.json();
        logServerResponse(PLAY_LUCK_GAME_ENDPOINT, response.status, responseData);

        // Update balance locally if available in response
        if (responseData && typeof responseData.new_balance === 'number') {
            state.userBalance = responseData.new_balance;
            console.log(`Local balance updated to: ${state.userBalance} from luck_game response (status ${response.status}).`);
        }

        return responseData;

    } catch (error) {
        console.error("Fetch error playing luck game:", error);
        tg?.showAlert(`Ошибка сети: ${error.message || "?"}`);
        return { ok: false, error: `Ошибка сети: ${error.message || "?"}`, reason: 'network_error' };
    }
}

export async function attemptRobberyApi() {
    console.log(`%cRequesting ATTEMPT ROBBERY`, "color: blue; font-weight: bold;");
    const initDataStr = getInitDataString();
    if (!initDataStr) {
        console.error("TG initData not available for robbery game.");
        tg?.showAlert("Ошибка: Нет данных пользователя.");
        return { ok: false, error: "Нет данных пользователя." }; // Consistent error object
    }

    const payload = {
        initData: initDataStr
    };

    try {
        const response = await fetch(ATTEMPT_ROBBERY_ENDPOINT, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const responseData = await response.json();
        logServerResponse(ATTEMPT_ROBBERY_ENDPOINT, response.status, responseData);

        // Update balance locally if available in response
         if (responseData && typeof responseData.new_balance === 'number') {
            state.userBalance = responseData.new_balance;
            console.log(`Local balance updated to: ${state.userBalance} from robbery response (status ${response.status}).`);
        }


        return responseData;

    } catch (error) {
        console.error("Fetch error attempting robbery:", error);
        tg?.showAlert(`Ошибка сети: ${error.message || "?"}`);
        return { ok: false, error: `Ошибка сети: ${error.message || "?"}`, reason: 'network_error' };
    }
}

// --- НОВАЯ ФУНКЦИЯ API для игры "Слоты" ---
/**
 * Отправляет запрос на игру в "Слоты" на сервер.
 * @param {number} betAmount Сумма ставки.
 * @returns {Promise<object|null>} Результат игры от сервера или null при ошибке сети.
 */
export async function playSlotsApi(betAmount) {
    console.log(`%cRequesting PLAY SLOTS: bet=${betAmount}`, "color: blue; font-weight: bold;");
    const initDataStr = getInitDataString(); // Используем существующую функцию getInitDataString
    if (!initDataStr) {
        console.error("TG initData not available for slots game.");
        tg?.showAlert("Ошибка: Нет данных пользователя.");
        // Return consistent error object instead of null
        return { ok: false, error: "Нет данных пользователя.", reason: 'init_data_missing' };
    }

    const payload = {
        initData: initDataStr,
        bet: String(betAmount)
    };

    try {
        const response = await fetch(PLAY_SLOTS_ENDPOINT, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const responseData = await response.json();
        logServerResponse(PLAY_SLOTS_ENDPOINT, response.status, responseData);

        // Update balance locally if available in response
         if (responseData && typeof responseData.new_balance === 'number') {
            state.userBalance = responseData.new_balance;
            console.log(`Local balance updated to: ${state.userBalance} from slots response (status ${response.status}).`);
        }

        return responseData; // {ok: bool, win: bool, bet: float, win_amount: float, coefficient: float, new_balance: float, dice_value: int, error?: str, reason?: str}

    } catch (error) {
        console.error("Fetch error playing slots:", error);
        tg?.showAlert(`Ошибка сети: ${error.message || "?"}`);
        return { ok: false, error: `Ошибка сети: ${error.message || "?"}`, reason: 'network_error' };
    }
}
