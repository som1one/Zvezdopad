// Содержимое файла: js/ui.js
// --------------------------
import {
    tg, appContainer, errorMessageEl
} from './dom.js';
import { state } from './state.js';
import {
    FREE_SPIN_COOLDOWN_SECONDS, SPIN_SOUND_SRC, WIN_SOUND_SRC,
    PREFERENCE_STORAGE_KEY, DEFAULT_SPIN_COST
} from './config.js';
import { confirmSpinActionWithServer } from './api.js';
import { drawWheel, drawWheelHighlight } from './wheelRenderer.js';
// Если gsap используется как модуль, а не глобально:
// import { gsap } from "gsap";

// --- Аудио ---
let spinSoundInstance, winSoundInstance;

export function createAudioElements() {
    function createAudio(src, volume = 0.6) {
        try {
            const audio = new Audio(src);
            audio.preload = "auto";
            audio.volume = volume;
            return audio;
        } catch (e) {
            console.warn(`Sound ${src} load error`, e);
            return { // Fallback object
                play: () => Promise.resolve(),
                pause: () => {},
                load: () => {},
                currentTime: 0,
                volume: 0
            };
        }
    }
    // Проверяем путь к звуковым файлам
    console.log("Spin Sound Path:", SPIN_SOUND_SRC);
    console.log("Win Sound Path:", WIN_SOUND_SRC);
    spinSoundInstance = createAudio(SPIN_SOUND_SRC, 0.6);
    winSoundInstance = createAudio(WIN_SOUND_SRC, 0.7);
    console.log("Audio elements created.");
}

export function playSpinSound() {
    if(spinSoundInstance) {
        spinSoundInstance.currentTime = 0;
        spinSoundInstance.play().catch((e) => console.warn("Spin sound play error:", e));
    }
}

export function playWinSound() {
     if(winSoundInstance) {
        winSoundInstance.currentTime = 0;
        winSoundInstance.play().catch((e) => console.warn("Win sound play error:", e));
    }
}

// --- ИЗМЕНЕНИЕ: Добавлено 'export' ---
/**
 * Анимирует изменение числового значения в текстовом элементе.
 * @param {Element} element - DOM-элемент для обновления (span, div, etc.).
 * @param {number} targetValue - Конечное числовое значение.
 * @param {string} [suffix=''] - Суффикс для добавления к числу (напр., ' ⭐').
 * @param {number} [duration=0.5] - Длительность анимации в секундах.
 * @param {number} [decimals=0] - Количество знаков после запятой.
 */
export function animateCounter(element, targetValue, suffix = '', duration = 0.5, decimals = 0) {
    if (!element || typeof targetValue !== 'number' || !window.gsap) {
        if (element) element.textContent = targetValue.toFixed(decimals) + suffix; // Установка значения без анимации
        console.warn("animateCounter: Element, targetValue, or gsap not valid. Setting text directly.", {element, targetValue, gsap: !!window.gsap});
        return;
    }

    // Получаем текущее числовое значение из элемента (убирая суффикс и парся)
    const currentText = element.textContent || '0';
    // Улучшенное получение текущего значения, чтобы справиться с ' ⭐' и возможными пробелами
    const currentValue = parseFloat(currentText.replace(/[^0-9.,-]+/g, '').replace(',', '.')) || 0;

    // Если значение не изменилось, все равно установим его с нужным форматированием
    if (Math.abs(currentValue - targetValue) < (0.1 ** decimals) / 2 ) { // Сравнение с учетом точности
         element.textContent = targetValue.toFixed(decimals) + suffix;
        // console.log(`animateCounter: Target ${targetValue} is same as current ${currentValue}. Skipping animation.`);
        return;
    }

    // Используем proxy объект для анимации значения
    let proxy = { value: currentValue };

    gsap.to(proxy, {
        value: targetValue,
        duration: duration,
        ease: "power2.out",
        onUpdate: () => {
            // Проверка на NaN перед установкой
            if (!isNaN(proxy.value)) {
                element.textContent = proxy.value.toFixed(decimals) + suffix;
            }
        },
        // По завершении устанавливаем точное значение с форматированием
        onComplete: () => {
             if (!isNaN(targetValue)) {
                element.textContent = targetValue.toFixed(decimals) + suffix;
             }
        },
        overwrite: 'auto' // Позволяет перезаписать анимацию для того же элемента
    });
}
// --- КОНЕЦ ИЗМЕНЕНИЯ ---


// --- Визуальные Эффекты ---

export function highlightWinningSector(winningIndex, callback) {
    console.log("Highlight animation start for index:", winningIndex);
    const duration = 700; // ms
    const framesPerSecond = 60;
    const totalFrames = Math.ceil(duration / (1000 / framesPerSecond));
    let currentFrame = 0;
    let intervalId = null;
    let callbackCalled = false;

    const wheelCanvas = document.getElementById('wheel');

    if (!wheelCanvas || !window.gsap) {
       console.error("Highlight failed: canvas or gsap not available.");
       if(callback) callback();
       return;
    }

    gsap.set(wheelCanvas, { rotation: state.currentRotation });

    const executeCallback = () => {
        if (!callbackCalled && callback) {
            console.log("Executing highlight callback.");
            callbackCalled = true;
            try {
                callback();
            } catch (e) {
                console.error("Error in highlight callback:", e);
            }
        } else if (!callback) {
            console.warn("No highlight callback was provided.");
        }
    };

    const loop = () => {
        try {
            currentFrame++;
            let progress = currentFrame / totalFrames;
            if (progress > 1) progress = 1;

            const saturation = 1 + 0.8 * Math.sin(progress * Math.PI);
            drawWheelHighlight(winningIndex, saturation);

            if (progress >= 1) {
                console.log("Highlight animation finished.");
                if (intervalId) clearInterval(intervalId);
                intervalId = null;
                drawWheelHighlight(winningIndex, 1.6);
                executeCallback();
            }
        } catch (e) {
            console.error("Error during highlight animation loop:", e);
            if (intervalId) clearInterval(intervalId);
            intervalId = null;
            executeCallback();
        }
    };

    intervalId = setInterval(loop, 1000 / framesPerSecond);

    setTimeout(() => {
        if (intervalId) {
            console.warn("Highlight animation fallback timeout triggered.");
            clearInterval(intervalId);
            intervalId = null;
            drawWheelHighlight(winningIndex, 1.6);
            executeCallback();
        }
    }, duration + 500);
}


export function launchConfetti() {
    try {
        const currentAppContainer = document.getElementById("appContainer");
        const currentOuterRing = document.getElementById("outerRing");

        if (!currentAppContainer || !currentOuterRing) {
             console.warn("Cannot launch confetti: appContainer or outerRing not found.");
             return;
        }

        const numConfetti = 80;
        const colors = ["#ffce00", "#ff6f61", "#a29bfe", "#fd79a8", "#ffeaa7", "#55efc4", "#74b9ff", "#f0932b", "#eb4d4b"];
        const containerRect = currentAppContainer.getBoundingClientRect();
        const wheelRect = currentOuterRing.getBoundingClientRect();

        const startX = (wheelRect.left - containerRect.left) + wheelRect.width / 2;
        const startY = (wheelRect.top - containerRect.top) - 10;

        for (let i = 0; i < numConfetti; i++) {
            setTimeout(() => {
                if (!document.body.contains(currentAppContainer)) return;

                const confetti = document.createElement("div");
                confetti.classList.add("confetti");
                const color = colors[Math.floor(Math.random() * colors.length)];
                confetti.style.setProperty("--c", color);

                const x = startX + (Math.random() - 0.5) * 80;
                const y = startY + (Math.random() - 0.5) * 30;
                confetti.style.left = x + "px";
                confetti.style.top = y + "px";

                const angle = Math.random() * Math.PI * 2;
                const distance = 120 + Math.random() * 180;
                const finalX = Math.cos(angle) * distance;
                const finalY = (Math.sin(angle) * distance) + (distance * 0.5);
                const rotateZ = (Math.random() - 0.5) * 720;
                const rotateY = (Math.random() - 0.5) * 720;

                confetti.style.setProperty("--dx", finalX + "px");
                confetti.style.setProperty("--dy", finalY + "px");
                confetti.style.setProperty("--rz", rotateZ + "deg");
                confetti.style.setProperty("--ry", rotateY + "deg");

                currentAppContainer.appendChild(confetti);

                setTimeout(() => {
                    if (confetti.parentNode === currentAppContainer) {
                        currentAppContainer.removeChild(confetti);
                    }
                }, 1900);
            }, i * 8);
        }
    } catch (e) {
        console.error("Confetti launch error:", e);
    }
}


export function launchCelebration() {
    let fireworkCanvas = document.getElementById("fireworkCanvas");
    if (fireworkCanvas) return;

    fireworkCanvas = document.createElement("canvas");
    fireworkCanvas.id = "fireworkCanvas";
    fireworkCanvas.style.cssText = "position:fixed;top:0;left:0;pointer-events:none;z-index:10001;width:100%;height:100%;";
    document.body.appendChild(fireworkCanvas);

    const resizeCanvas = () => {
         if (fireworkCanvas) {
             fireworkCanvas.width = window.innerWidth;
             fireworkCanvas.height = window.innerHeight;
         }
    };
    resizeCanvas();

    const ctxF = fireworkCanvas.getContext("2d");
    if (!ctxF) {
        console.error("Failed to get 2D context for fireworks canvas.");
        if (document.body.contains(fireworkCanvas)) document.body.removeChild(fireworkCanvas);
        return;
    }

    const particles = [];
    const fireworks = [];
    const gravity = 0.05;
    let animationFrameId;
    let fireworkIntervalId;
    let cleanupTimeoutId;

     function createParticles(x, y, color) {
        const particleCount = 80 + Math.random() * 40;
        const baseSpeed = Math.random() * 4 + 3;
        for (let i = 0; i < particleCount; i++) {
            const angle = Math.random() * Math.PI * 2;
            const speed = Math.random() * baseSpeed;
            particles.push({
                x: x, y: y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed - Math.random() * 1.5,
                alpha: 1,
                color: color || `hsl(${Math.random() * 360}, 100%, 70%)`,
                size: Math.random() * 2.5 + 1,
                fade: 0.015 + Math.random() * 0.01
            });
        }
    }

    function createFirework() {
        const startX = window.innerWidth / 2;
        const startY = window.innerHeight;
        const endX = Math.random() * window.innerWidth * 0.6 + window.innerWidth * 0.2;
        const endY = Math.random() * window.innerHeight * 0.4 + window.innerHeight * 0.1;
        fireworks.push({
            x: startX, y: startY,
            tx: endX, ty: endY,
            speed: Math.random() * 2 + 4.5,
            color: `hsl(${Math.random() * 360}, 100%, 70%)`
        });
    }

    const cleanup = () => {
         console.log("Cleaning up fireworks...");
         window.removeEventListener("resize", resizeCanvas);
         if (animationFrameId) cancelAnimationFrame(animationFrameId);
         if (fireworkIntervalId) clearInterval(fireworkIntervalId);
         if (cleanupTimeoutId) clearTimeout(cleanupTimeoutId);
         let canvasToRemove = document.getElementById("fireworkCanvas");
         if (canvasToRemove && document.body.contains(canvasToRemove)) {
              document.body.removeChild(canvasToRemove);
         }
         fireworkCanvas = null;
         animationFrameId = null;
         fireworkIntervalId = null;
         cleanupTimeoutId = null;
    };

    function animateFireworks() {
         if (!fireworkCanvas || !ctxF) {
            console.warn("Fireworks animation stopped: canvas or context lost.");
            cleanup();
            return;
         }
        ctxF.fillStyle = "rgba(0, 0, 0, 0.1)";
        ctxF.fillRect(0, 0, fireworkCanvas.width, fireworkCanvas.height);

         for (let i = fireworks.length - 1; i >= 0; i--) {
            const fw = fireworks[i];
            const dx = fw.tx - fw.x, dy = fw.ty - fw.y;
            const distance = Math.sqrt(dx * dx + dy * dy);
            if (distance === 0) {
                 fireworks.splice(i, 1);
                 continue;
            }
            const angle = Math.atan2(dy, dx);
            fw.x += Math.cos(angle) * fw.speed;
            fw.y += Math.sin(angle) * fw.speed;

            ctxF.fillStyle = fw.color;
            ctxF.beginPath();
            ctxF.arc(fw.x, fw.y, 2.5, 0, Math.PI * 2);
            ctxF.fill();

            if (distance < fw.speed * 1.5) {
                createParticles(fw.x, fw.y, fw.color);
                fireworks.splice(i, 1);
            }
        }

         for (let i = particles.length - 1; i >= 0; i--) {
            const p = particles[i];
            p.vy += gravity;
            p.x += p.vx;
            p.y += p.vy;
            p.alpha -= p.fade;

            if (p.alpha <= 0) {
                particles.splice(i, 1);
            } else {
                ctxF.save();
                ctxF.globalAlpha = p.alpha;
                ctxF.fillStyle = p.color;
                ctxF.beginPath();
                ctxF.arc(p.x, p.y, p.size, 0, Math.PI * 2);
                ctxF.fill();
                ctxF.restore();
            }
        }

        if (particles.length === 0 && fireworks.length === 0 && !fireworkIntervalId) {
            console.log("Fireworks finished.");
            if (!cleanupTimeoutId) {
                 cleanupTimeoutId = setTimeout(cleanup, 1000);
            }
            return;
        }
        animationFrameId = requestAnimationFrame(animateFireworks);
    }

    fireworkIntervalId = setInterval(createFirework, 400);
    createFirework();
    animateFireworks();

    setTimeout(() => {
        if (fireworkIntervalId) {
            clearInterval(fireworkIntervalId);
            fireworkIntervalId = null;
            console.log("Stopped launching new fireworks.");
        }
    }, 2500);

    window.addEventListener("resize", resizeCanvas);
}


export function displayModal(prizeData, actionCallback, isDemo, spinId, resetCallback) {
    try {
        const existingOverlay = document.getElementById("winOverlay");
        if (existingOverlay) existingOverlay.remove();

        const overlay = document.createElement("div");
        overlay.id = "winOverlay";

        let modalHTML = `
            <div id="winModal">
                <h2>${isDemo ? "Демо Выигрыш!" : "Поздравляем!"}</h2>
                <div class="win-emoji">${prizeData.emoji || "❓"}</div>
                <p class="win-text">Вы выиграли <b>${prizeData.name || "Приз"}</b> (${prizeData.costNumber || 0} ⭐)!</p>
                <div class="win-actions">`;

        if (!isDemo && actionCallback && prizeData.canSell !== false && prizeData.costNumber > 0) {
             modalHTML += `<button id="receivePrizeBtn" data-action="spin_result">🎁 Получить</button>`;
             modalHTML += `<button id="sellPrizeBtn" class="sell-btn" data-action="spin_result_sell">💰 Продать (+${prizeData.costNumber || 0}⭐)</button>`;
        } else if (!isDemo && actionCallback) {
             modalHTML += `<button id="receivePrizeBtn" data-action="spin_result">🎁 Получить</button>`;
             modalHTML += `<button id="closeWinModal">Отлично!</button>`;
        } else {
            modalHTML += `<button id="closeWinModal">Отлично!</button>`;
        }


        modalHTML += `</div></div>`;
        overlay.innerHTML = modalHTML;
        document.body.appendChild(overlay);

        const winModal = overlay.querySelector("#winModal");

        const closeModal = (shouldReset = true) => {
            if (!winModal || !overlay.parentNode) return;
            winModal.style.animation = "fadeOutScale 0.3s ease-in forwards";
            overlay.style.animation = "fadeOutOverlay 0.3s 0.1s ease-in forwards";
            overlay.style.pointerEvents = "none";

            setTimeout(() => {
                if (document.body.contains(overlay)) {
                    document.body.removeChild(overlay);
                }
                if (shouldReset && resetCallback) {
                    console.log("Modal closed via 'Close' or Demo -> triggering reset callback.");
                    resetCallback();
                } else {
                    console.log("Modal closed via action button -> reset handled by action callback.");
                }
            }, 600);
        };

        const closeButton = overlay.querySelector("#closeWinModal");
        if (closeButton) {
            closeButton.addEventListener("click", () => closeModal(true));
        }

        const actionButtons = overlay.querySelectorAll("#receivePrizeBtn, #sellPrizeBtn");
        if (!isDemo && actionCallback) {
            actionButtons.forEach(button => {
                button.addEventListener("click", () => {
                    actionButtons.forEach(btn => btn.disabled = true);
                    const actionChoice = button.dataset.action;
                    actionCallback(actionChoice);
                    closeModal(false);
                });
            });
        }

        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                overlay.classList.add("visible");
            });
        });

    } catch (e) {
        console.error("Display modal error:", e);
        const overlay = document.getElementById("winOverlay");
        if (overlay) overlay.remove();
        if (resetCallback) resetCallback();
    }
}


// --- Обновление UI ---

export function resetWheelVisuals() {
    console.log("%cVisual reset", "color:gray;");
    const wheelCanvas = document.getElementById('wheel');
    const currentCenterDisc = document.getElementById('centerDisc');
    const currentOuterRing = document.getElementById('outerRing');

    if (!wheelCanvas || !currentCenterDisc || !currentOuterRing || !window.gsap) {
        console.warn("Cannot reset visuals: wheel elements or GSAP not found.");
        return;
    }
    gsap.killTweensOf(wheelCanvas);
    gsap.set(wheelCanvas, { rotation: state.currentRotation, overwrite: true });
    wheelCanvas.classList.remove("spinning");
    currentCenterDisc.classList.remove("clicked");
    currentOuterRing.classList.remove("stopping", "vibrate");
    drawWheel();
}

export function isReadyToSpin() {
     const currentModeToggle = document.getElementById('modeToggle');
     const wheelIsActive = !!document.getElementById('wheel');

     if (!wheelIsActive) {
         // console.log("Spin readiness check: Wheel is not active.");
         return false;
     }
     if (!state.dataLoaded) {
        console.warn("Spin readiness check: Data not loaded.");
        return false;
     }
     const isDemo = currentModeToggle ? !currentModeToggle.checked : true;
     return isDemo || (state.isFreeSpinAvailable || state.userBalance >= state.currentSpinCost);
}

function updateSpinButtonText() {
    const currentSpinBtn = document.getElementById('spinBtn');
    const currentModeToggle = document.getElementById('modeToggle');
    if (currentSpinBtn) {
        const isDemo = currentModeToggle ? !currentModeToggle.checked : false;
        currentSpinBtn.textContent = state.isSpinning
            ? "Вращаем..."
            : !state.dataLoaded
                ? "Загрузка..."
                : isDemo
                    ? "Крутить (Демо)"
                    : (state.isFreeSpinAvailable ? "Крутить (Беспл.)" : "Крутить");
    }
}

function updateSpinButtonState() {
    const currentSpinBtn = document.getElementById('spinBtn');
    if (currentSpinBtn) {
        currentSpinBtn.disabled = state.isSpinning || !isReadyToSpin();
        updateSpinButtonText();
    }
}

export function setActiveCostButton(btn) {
    const currentCostButtons = document.querySelectorAll("#spinCostBlock .costBtn");
    const currentCenterDisc = document.getElementById('centerDisc');
    const currentModeToggle = document.getElementById('modeToggle');

    if (!btn || typeof btn.dataset === 'undefined' || typeof btn.dataset.cost === 'undefined' || !currentCostButtons || !currentCenterDisc) {
        console.error("setActiveCostButton: Invalid button element or missing required elements/data.", {
             buttonElement: btn,
             isElement: btn instanceof Element,
             hasDataset: btn ? typeof btn.dataset !== 'undefined' : 'N/A',
             hasDatasetCost: btn && typeof btn.dataset !== 'undefined' ? typeof btn.dataset.cost !== 'undefined' : 'N/A',
             costButtonsFound: !!currentCostButtons,
             centerDiscFound: !!currentCenterDisc
        });
        return;
    }

    const newCost = parseInt(btn.dataset.cost);
    if (isNaN(newCost)) {
         console.error("setActiveCostButton: Invalid cost value in dataset:", btn.dataset.cost);
         return;
    }

    if (newCost !== state.currentSpinCost) {
         state.currentSpinCost = newCost;
         console.log(`State cost updated to: ${state.currentSpinCost}`);
         if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred("light");
    }

    currentCostButtons.forEach(b => b.classList.remove("active"));
    btn.classList.add("active");

    const isDemo = currentModeToggle ? !currentModeToggle.checked : false;
    if (isDemo || !state.isFreeSpinAvailable) {
        currentCenterDisc.innerHTML = `<span class="cost-value">${state.currentSpinCost}</span><span class="cost-star">⭐</span>`;
        currentCenterDisc.classList.remove("free-spin-active");
    } else {
        if (!currentCenterDisc.classList.contains("free-spin-active")) {
            currentCenterDisc.innerHTML = '<span class="cost-label">FREE</span><span class="cost-sublabel">🎁</span>';
            currentCenterDisc.classList.add("free-spin-active");
        }
    }
    updateSpinButtonState();
}

export function updateStatusDisplay() {
     const currentBalanceValueEl = document.getElementById("balanceValue");
     const currentFreeSpinInfoEl = document.getElementById("freeSpinInfoPlaque");

     // console.log(`%cUpdate UI State: Balance=${state.userBalance}, Free=${state.isFreeSpinAvailable}, CooldownEnd=${state.freeSpinCooldownEnd ? new Date(1000 * state.freeSpinCooldownEnd).toISOString() : "N/A"}`, "color:orange;");

     if (currentBalanceValueEl) {
        animateCounter(currentBalanceValueEl, Math.floor(state.userBalance), ' ⭐', 0.5, 0);
     }

     const profileBalanceEl = document.getElementById('profile-balance');
     if (profileBalanceEl && !profileBalanceEl.querySelector('.profile-placeholder')) {
         profileBalanceEl.textContent = state.userBalance.toFixed(2);
     }

      if (currentFreeSpinInfoEl) {
        if (state.isFreeSpinAvailable) {
            currentFreeSpinInfoEl.textContent = "🎁 Бесплатная прокрутка доступна!";
            currentFreeSpinInfoEl.className = "freeSpinInfoPlaque available";
        } else if (state.freeSpinCooldownEnd && typeof state.freeSpinCooldownEnd === 'number') {
            const nowTimestamp = Math.floor(Date.now() / 1000);
            const remainingSeconds = state.freeSpinCooldownEnd - nowTimestamp;
            if (remainingSeconds > 0) {
                const hoursLeft = Math.floor(remainingSeconds / 3600);
                const minutesLeft = Math.floor((remainingSeconds % 3600) / 60);
                const newText = `⏳ Беспл. спин через: ${hoursLeft}ч ${minutesLeft}м`;
                if (currentFreeSpinInfoEl.textContent !== newText || !currentFreeSpinInfoEl.classList.contains('cooldown')) {
                     currentFreeSpinInfoEl.textContent = newText;
                     currentFreeSpinInfoEl.className = "freeSpinInfoPlaque cooldown";
                }
            } else {
                if (!state.isFreeSpinAvailable) {
                    console.log("Cooldown expired locally. Setting free spin available.");
                    state.isFreeSpinAvailable = true;
                    state.freeSpinCooldownEnd = null;
                    currentFreeSpinInfoEl.textContent = "🎁 Бесплатная прокрутка доступна!";
                    currentFreeSpinInfoEl.className = "freeSpinInfoPlaque available";
                    updateSpinButtonState();
                }
            }
        } else {
            if (currentFreeSpinInfoEl.textContent !== "Бесплатных прокруток нет" || !currentFreeSpinInfoEl.className.includes("freeSpinInfoPlaque")) {
                currentFreeSpinInfoEl.textContent = "Бесплатных прокруток нет";
                 currentFreeSpinInfoEl.className = "freeSpinInfoPlaque";
            }
        }
     }


     const currentModeToggle = document.getElementById('modeToggle');
     const currentModeLabel = document.getElementById('modeLabel');
     const currentSpinCostBlock = document.getElementById('spinCostBlock');
     const currentCostButtons = document.querySelectorAll("#spinCostBlock .costBtn");
     const currentCenterDisc = document.getElementById('centerDisc');
     const currentPrizeRadios = document.querySelectorAll('#prizeActionBlock input[name="prizeAction"]');

     if (currentModeToggle) {
         const isDemo = !currentModeToggle.checked;
         currentModeToggle.disabled = !state.dataLoaded || state.isSpinning;
         if (currentModeLabel) {
             currentModeLabel.textContent = isDemo ? "Демо режим" : "Игра на звезды";
         }

         if (currentSpinCostBlock && currentCostButtons.length > 0) {
             if (isDemo || !state.isFreeSpinAvailable) {
                 currentCostButtons.forEach(b => { b.disabled = state.isSpinning });
                 const activeBtn = document.querySelector(`#spinCostBlock .costBtn[data-cost="${state.currentSpinCost}"]`) || document.getElementById("cost25Btn");
                 if (activeBtn && !activeBtn.classList.contains('active')) { // Проверяем, что кнопка не активна уже
                      // setActiveCostButton(activeBtn); // Не вызываем здесь, чтобы избежать рекурсии/лишних вызовов
                      console.log("Need to set active cost button, but skipping in updateStatusDisplay to avoid loop.");
                 } else if (!activeBtn){
                      console.warn(`Could not find button for current cost ${state.currentSpinCost} or default during UI update.`);
                      const defaultBtn = document.getElementById("cost25Btn");
                      if(defaultBtn) setActiveCostButton(defaultBtn);
                 }
                 currentSpinCostBlock.style.opacity = "1";
                 currentSpinCostBlock.style.pointerEvents = "auto";
             } else {
                 currentCostButtons.forEach(b => { b.disabled = true });
                 currentSpinCostBlock.style.opacity = ".6";
                 currentSpinCostBlock.style.pointerEvents = "none";
             }
         }

          if (currentCenterDisc) {
             if (isDemo || !state.isFreeSpinAvailable) {
                  currentCenterDisc.innerHTML = `<span class="cost-value">${state.currentSpinCost}</span><span class="cost-star">⭐</span>`;
                  currentCenterDisc.classList.remove("free-spin-active");
             } else {
                 if (!currentCenterDisc.classList.contains("free-spin-active")) {
                     currentCenterDisc.innerHTML = '<span class="cost-label">FREE</span><span class="cost-sublabel">🎁</span>';
                     currentCenterDisc.classList.add("free-spin-active");
                 }
             }
          }

         if (currentPrizeRadios.length > 0) {
            let prefFound = false;
            currentPrizeRadios.forEach(radio => {
                radio.checked = (radio.value === state.prizeActionPreference);
                if(radio.checked) prefFound = true;
            });
            if (!prefFound) {
                const defaultRadio = document.querySelector('#prizeActionBlock input[name="prizeAction"][value="ask"]');
                if (defaultRadio) defaultRadio.checked = true;
                state.prizeActionPreference = 'ask';
                localStorage.setItem(PREFERENCE_STORAGE_KEY, state.prizeActionPreference);
            }
         }
        updateSpinButtonState();
     }


     const luckBetButtons = document.querySelectorAll('.luck-bet-button');
     luckBetButtons.forEach(btn => {
         const bet = parseFloat(btn.dataset.bet);
         btn.disabled = state.userBalance < bet || state.isSpinning;
     });
     const slotsBetButtons = document.querySelectorAll('.slots-bet-button');
     slotsBetButtons.forEach(btn => {
         const bet = parseFloat(btn.dataset.bet);
         btn.disabled = state.userBalance < bet || state.isSpinning;
     });
     const robberyButton = document.getElementById('robbery-attempt-btn');
     if (robberyButton) {
         robberyButton.disabled = state.userBalance < 5.0 || robberyButton.dataset.cooldown === 'true';
     }


      const luckBalanceDisplay = document.getElementById('luck-game-current-balance');
      if(luckBalanceDisplay) luckBalanceDisplay.innerHTML = `Ваш баланс: <span>${state.userBalance.toFixed(2)} ⭐</span>`;
      const slotsBalanceDisplay = document.getElementById('slots-game-current-balance');
      if(slotsBalanceDisplay) slotsBalanceDisplay.innerHTML = `Ваш баланс: <span>${state.userBalance.toFixed(2)} ⭐</span>`;
      const robberyBalanceDisplay = document.getElementById('robbery-game-current-balance');
       if(robberyBalanceDisplay) robberyBalanceDisplay.innerHTML = `Ваш баланс: <span>${state.userBalance.toFixed(2)} ⭐</span>`;

}


// Таймер для обновления текста кулдауна
let cooldownIntervalId = null;
export function startCooldownTimer() {
    if (cooldownIntervalId) clearInterval(cooldownIntervalId);

    cooldownIntervalId = setInterval(() => {
        // Обновляем только если есть активный кулдаун
        if (!state.isFreeSpinAvailable && state.freeSpinCooldownEnd && state.freeSpinCooldownEnd > Math.floor(Date.now()/1000)) {
            // Вызываем updateStatusDisplay, он сам проверит, нужно ли обновлять текст
            updateStatusDisplay();
        } else if (!state.isFreeSpinAvailable && state.freeSpinCooldownEnd && state.freeSpinCooldownEnd <= Math.floor(Date.now()/1000)) {
             // Кулдаун истек - обновляем состояние и UI
             console.log("Cooldown timer detected expiry.");
             state.isFreeSpinAvailable = true;
             state.freeSpinCooldownEnd = null;
             updateStatusDisplay(); // Обновит и текст, и кнопки
        }
    }, 60000); // Проверка раз в минуту
     console.log("Cooldown update timer started.");
}

export function stopCooldownTimer() {
    if (cooldownIntervalId) {
        clearInterval(cooldownIntervalId);
        cooldownIntervalId = null;
        console.log("Cooldown update timer stopped.");
    }
}