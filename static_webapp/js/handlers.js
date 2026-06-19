// Содержимое файла: static_webapp/js/handlers.js (Исправлено: убран logger.js)

import {
    tg, appContainer, errorMessageEl
} from './dom.js';
import { state } from './state.js';
import {
    items as configItems, PREFERENCE_STORAGE_KEY, SPIN_DURATION_MS,
    WINDUP_DURATION_S, WINDUP_ANGLE, SPIN_SOUND_DELAY_MS, RESET_DELAY_MS,
    FREE_SPIN_COOLDOWN_SECONDS // Убедитесь, что импортирована
} from './config.js';
import { fetchUserState, requestStartSpinFromServer, confirmSpinActionWithServer } from './api.js';
import { buildSectors, updateWheelSizeAndRedraw, drawWheelHighlight, drawWheel } from './wheelRenderer.js';
import {
    updateStatusDisplay, setActiveCostButton, playSpinSound, playWinSound,
    highlightWinningSector, launchConfetti, launchCelebration, displayModal,
    resetWheelVisuals,
    isReadyToSpin
} from './ui.js';
import { weightedRandom, randomInRange } from './utils.js';
import { forceResetState } from './main.js';


async function showWinMessageOrAction(winningPrizeData, spinId = null, isDemo = false) {
    // ... (код этой функции остается без изменений) ...
    if (!winningPrizeData) {
        forceResetState();
        return;
    }

    const isGift = winningPrizeData.canSell !== false && winningPrizeData.costNumber > 0;
    const currentPreference = isGift ? state.prizeActionPreference : 'receive';

    const performServerAction = async (actionChoice) => {
        if (isDemo) {
             setTimeout(forceResetState, RESET_DELAY_MS * 2);
            return;
        }

        if (!spinId) {
            tg?.showAlert("Критическая ошибка: ID спина отсутствует!");
            forceResetState();
            return;
        }

        if (appContainer) appContainer.classList.add("loading");
        const confirmationResult = await confirmSpinActionWithServer(spinId, actionChoice);
        if (appContainer) appContainer.classList.remove("loading");

        if (confirmationResult && confirmationResult.ok) {
             updateStatusDisplay();
        } else {
            if (tg && confirmationResult?.error) {
                 tg.showAlert(confirmationResult.error);
            } else if (tg) {
                 tg.showAlert("Не удалось подтвердить действие.");
            }
             updateStatusDisplay();
        }

        setTimeout(forceResetState, RESET_DELAY_MS);
    };

    if (currentPreference === "receive") {
        await performServerAction("spin_result");
    } else if (currentPreference === "sell" && isGift) {
        await performServerAction("spin_result_sell");
    } else {
        if (isDemo) {
             displayModal(winningPrizeData, null, true, spinId, forceResetState);
        } else {
            displayModal(winningPrizeData, performServerAction, false, spinId, forceResetState);
        }
    }
}


export async function handleSpinClick() {
    const currentSpinBtn = document.getElementById('spinBtn');
    const currentCanvas = document.getElementById('wheel');
    const currentCenterDisc = document.getElementById('centerDisc');
    const currentOuterRing = document.getElementById('outerRing');
    const currentModeToggle = document.getElementById('modeToggle');
    const currentCostButtons = document.querySelectorAll('#spinCostBlock .costBtn');
    const currentAppContainer = document.getElementById('appContainer');

    if (!window.gsap) {
         tg?.showAlert("Ошибка анимации. Попробуйте перезагрузить.");
         return;
    }

     if (!currentSpinBtn || !currentCanvas || !currentCenterDisc || !currentOuterRing || !currentModeToggle || !currentAppContainer) {
        console.error("handleSpinClick: Missing required elements.");
        return;
    }

    if (state.isSpinning || gsap.isTweening(currentCanvas) || !state.dataLoaded) {
        if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred("warning");
        return;
    }

    const isDemoMode = !currentModeToggle.checked;

    state.isSpinning = true;
    updateStatusDisplay();
    currentCenterDisc.classList.add("clicked");
    currentOuterRing.classList.remove("vibrate");

    setTimeout(playSpinSound, SPIN_SOUND_DELAY_MS);

    let winningIndex = -1;
    let winningPrizeData = null;
    let spinId = null;
    let initialSpinAnimation = null;

    try {
        currentCanvas.classList.add("spinning");
        initialSpinAnimation = gsap.to(currentCanvas, {
            rotation: "+=3600",
            duration: 10,
            ease: "none",
            repeat: -1,
            overwrite: true
        });

        if (isDemoMode) {
             // ... (логика для демо режима без изменений) ...
            if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred("light");

            state.sectors = buildSectors(state.currentSpinCost);
            if (state.sectors.length === 0) throw new Error("Demo sectors failed to build.");

            const totalWeight = state.sectors.reduce((sum, segment) => sum + (segment.weight || 0), 0);
            if (totalWeight <= 0) throw new Error(`Demo: No valid weights for cost ${state.currentSpinCost}`);

            winningIndex = weightedRandom(state.sectors, totalWeight);
            if (winningIndex < 0) throw new Error("Demo: weightedRandom failed.");

            winningPrizeData = state.sectors[winningIndex];
            if (!winningPrizeData) throw new Error(`Demo: Invalid sector data for index ${winningIndex}`);


        } else {
            // ... (логика для реального режима без изменений) ...
             if (!isReadyToSpin()) {
                const msg = state.isFreeSpinAvailable ? "Бесплатный спин сейчас недоступен." : `Недостаточно средств! Нужно ${state.currentSpinCost}⭐`;
                throw new Error(msg);
            }

            if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred("medium");

            currentAppContainer.classList.add("loading");
            const startResult = await requestStartSpinFromServer(state.currentSpinCost, state.isFreeSpinAvailable);
            currentAppContainer.classList.remove("loading");

            if (!startResult || !startResult.ok) {
                throw new Error(startResult?.error || "Server rejected start spin request.");
            }

            spinId = startResult.spin_id;
            state.currentSpinId = spinId;
            winningPrizeData = startResult.winning_prize;
            state.currentWinningPrize = winningPrizeData;

            if (typeof startResult.new_balance === 'number') {
                state.userBalance = startResult.new_balance;
                console.log(`Balance updated to: ${state.userBalance} from START_SPIN response.`);
            }
            if (state.isFreeSpinAvailable && startResult.ok) { // Проверяем, что это был именно УСПЕШНЫЙ бесплатный спин
                state.isFreeSpinAvailable = false;
                state.freeSpinCooldownEnd = Math.floor(Date.now() / 1000) + FREE_SPIN_COOLDOWN_SECONDS;
                console.log("Free spin used. Cooldown updated.");
            }
            updateStatusDisplay(); // Обновляем UI *после* получения ответа и обновления состояния

            winningIndex = winningPrizeData?.index;

            if (typeof winningIndex !== 'number' || winningIndex < 0 || winningIndex >= state.sectors.length) {
                throw new Error(`REAL: Invalid winning index received: ${winningIndex}`);
            }
        }

        if (winningIndex === -1 || !winningPrizeData) {
            throw new Error("Winning data is missing before final animation.");
        }

        if (initialSpinAnimation) {
            initialSpinAnimation.kill();
            console.debug("Initial spin animation killed.");
            // --------------------------
        }

        // ... (расчет углов и finalAngle без изменений) ...
        const angles = buildSectors(state.currentSpinCost).map((_, i, arr) => {
            const angleStep = 360 / arr.length;
            const angleOffset = 270 - angleStep / 2;
            const startAngle = angleOffset + i * angleStep;
            const midAngle = startAngle + angleStep / 2;
            const normalize = (a) => ((a % 360) + 360) % 360;
            return { mid: normalize(midAngle) };
        });
        if (angles.length === 0 || !angles[winningIndex]) {
            throw new Error("Failed to compute angles for animation.");
        }
        const angleToCenterPointer = 270;
        const winAngle = angles[winningIndex].mid;
        const currentActualRotation = gsap.getProperty(currentCanvas, "rotation") % 360;
        const targetRestingRotation = (angleToCenterPointer - winAngle + 360) % 360;
        const randomSpins = 5 + Math.random() * 3;
        const minSpinAngle = 360 * randomSpins;
        let targetAngle = (currentActualRotation < 0 ? currentActualRotation + 360 : currentActualRotation) + minSpinAngle;
        let currentModulo = targetAngle % 360;
        let adjustment = (targetRestingRotation - currentModulo + 360) % 360;
        targetAngle += adjustment;
        if (targetAngle < (currentActualRotation < 0 ? currentActualRotation + 360 : currentActualRotation) + minSpinAngle - 1) {
            targetAngle += 360;
        }
        const finalAngle = targetAngle;
        console.debug(`Final target angle calculated: ${finalAngle} (to land on index ${winningIndex})`);
        // --------------------------


        const stopTl = gsap.timeline({
            onComplete: () => {
                 console.debug("Final spin animation completed.");
                 // --------------------------
                state.currentRotation = ((finalAngle % 360) + 360) % 360;

                if(currentCanvas) currentCanvas.classList.remove("spinning");
                if(currentCenterDisc) currentCenterDisc.classList.remove("clicked");
                if(currentOuterRing) {
                    currentOuterRing.classList.add("stopping");
                    setTimeout(() => currentOuterRing?.classList.remove("stopping"), 400);
                }

                setTimeout(() => {
                    try {
                        // ... (код вибрации и highlightWinningSector без изменений) ...
                        if(currentOuterRing) {
                            currentOuterRing.classList.add("vibrate");
                            setTimeout(() => currentOuterRing?.classList.remove("vibrate"), 500);
                        }

                        const hapticType = isDemoMode ? "warning" : "success";
                        if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred(hapticType);

                        highlightWinningSector(winningIndex, () => {
                            try {
                                playWinSound();
                                launchConfetti();
                                if (winningPrizeData?.costNumber >= 100) {
                                    launchCelebration();
                                }
                                setTimeout(() => {
                                    showWinMessageOrAction(winningPrizeData, spinId, isDemoMode);
                                }, 400);
                            } catch (highlightCallbackError) {
                                console.error("Error in highlight callback:", highlightCallbackError);
                                forceResetState();
                            }
                        });
                    } catch (postSpinError) {
                         console.error("Error in post-spin actions:", postSpinError);
                         forceResetState();
                    }
                }, 150);
            },
             onInterrupt: () => {
                 console.warning("Spin animation interrupted! Forcing state reset.");
                 forceResetState();
             }
        });

        stopTl.to(currentCanvas, { rotation: `+=${WINDUP_ANGLE}`, duration: WINDUP_DURATION_S, ease: "power1.inOut" });
        stopTl.to(currentCanvas, { rotation: finalAngle, duration: SPIN_DURATION_MS / 1000, ease: "power3.out", overwrite: "auto" }, ">");


    } catch (error) {
        console.error("Error during handleSpinClick:", error);
        if (initialSpinAnimation) {
            initialSpinAnimation.kill();
             // ---> ЗАМЕНА log.debug <---
             console.debug("Initial animation killed due to error.");
             // --------------------------
        }
        gsap.killTweensOf(currentCanvas);
        if (currentCanvas) currentCanvas.classList.remove("spinning");

        if (tg) tg.showAlert(`Ошибка: ${error.message || "Неизвестная ошибка спина"}`);
        forceResetState();
        if (currentAppContainer) currentAppContainer.classList.remove("loading");
          // Кнопки стоимости должны стать снова доступными после вызова updateStatusDisplay внутри forceResetState
    }
}


// ... (остальные функции: handleCostChange, handleModeToggle и т.д. без изменений) ...
export function handleCostChange(event) {
    const currentModeToggle = document.getElementById('modeToggle');

    if (state.isSpinning || !event.target.classList.contains('costBtn')) return;

    const btn = event.target;
    const cost = parseInt(btn.dataset.cost);

    if (!isNaN(cost)) {
         setActiveCostButton(btn);
         if (currentModeToggle && !currentModeToggle.checked) {
             state.sectors = buildSectors(state.currentSpinCost);
             drawWheel();
         }
    }
}


export function handleModeToggle() {
    const currentModeToggle = document.getElementById('modeToggle');
    if (!currentModeToggle) return;

    updateStatusDisplay();
    if (tg?.HapticFeedback) tg.HapticFeedback.selectionChanged();

     if (!currentModeToggle.checked) {
         state.sectors = buildSectors(state.currentSpinCost);
         drawWheel();
     } else {
         state.sectors = buildSectors(state.currentSpinCost);
         drawWheel();
     }
}

export function handlePrizeActionChange(event) {
    if (event.target.checked) {
        state.prizeActionPreference = event.target.value;
        localStorage.setItem(PREFERENCE_STORAGE_KEY, state.prizeActionPreference);
        if (tg?.HapticFeedback) tg.HapticFeedback.selectionChanged();
    }
}

export function handleResize() {
    const wheelCanvas = document.getElementById('wheel');
    if (wheelCanvas && document.body.contains(wheelCanvas)) {
        updateWheelSizeAndRedraw();
    }
}

export function handleGlobalError(message, source, lineno, colno, error) {
    try {
        const data = {
            action: "js_error",
            error: { message, source, lineno, colno, stack: error?.stack ?? "N/A" }
        };
        tg?.sendData && tg.sendData(JSON.stringify(data));
    } catch (e) { /* ignore */ }
    tg?.showAlert(`Критическая ошибка:\n${message}`);
    if (state.isSpinning) {
        forceResetState();
    }
    return false;
}

export function handleUnhandledRejection(event) {
    try {
        const data = {
            action: "js_promise_rejection",
            error: { reason: String(event.reason), stack: event.reason instanceof Error ? event.reason.stack : "N/A" }
        };
        tg?.sendData && tg.sendData(JSON.stringify(data));
    } catch (e) { /* ignore */ }
    tg?.showAlert(`Внутренняя ошибка:\n${event.reason}`);
    if (state.isSpinning) {
        forceResetState();
    }
}