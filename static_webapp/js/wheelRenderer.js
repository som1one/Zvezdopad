// Содержимое файла: js/wheelRenderer.js
// -------------------------------------

// wheelRenderer.js
// УБРАНО: import { canvas, ctx } from './dom.js'; // Больше не импортируем canvas и ctx отсюда
import { state } from './state.js';
import { items as configItems, mainColorPairs } from './config.js';

// --- Внутренние хелперы отрисовки (не экспортируются) ---

// Вычисляет углы для секторов
function computeAngles(numberOfSectors) {
    if (numberOfSectors === 0) return [];
    const angles = [];
    const angleStep = 360 / numberOfSectors;
    const angleOffset = 270 - angleStep / 2;
    if (isNaN(angleOffset) || isNaN(angleStep)) {
        console.error("Angle calculation produced NaN");
        return [];
    }
    for (let i = 0; i < numberOfSectors; i++) {
        const startAngle = angleOffset + i * angleStep;
        const endAngle = startAngle + angleStep;
        const midAngle = startAngle + angleStep / 2;
        const normalize = (a) => ((a % 360) + 360) % 360;
        angles.push({ start: normalize(startAngle), end: normalize(endAngle), mid: normalize(midAngle) });
    }
    return angles;
}

// Насыщение цвета для эффекта подсветки
function saturateColor(hex, factor) {
    function hexToRgb(hex) {
       hex = hex.replace(/^#/, '');
       if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
       const bigint = parseInt(hex, 16);
       return { r: (bigint >> 16) & 255, g: (bigint >> 8) & 255, b: bigint & 255 };
    }
    function rgbToHsl(r, g, b) {
       r /= 255; g /= 255; b /= 255;
       const max = Math.max(r, g, b), min = Math.min(r, g, b);
       let h = 0, s, l = (max + min) / 2;
       if (max === min) { s = 0; } else {
           const d = max - min;
           s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
           switch (max) {
               case r: h = (g - b) / d + (g < b ? 6 : 0); break;
               case g: h = (b - r) / d + 2; break;
               case b: h = (r - g) / d + 4; break;
           }
           h *= 60;
       }
       h = h < 0 ? h + 360 : h;
       return { h, s: s * 100, l: l * 100 };
    }
    function hslToRgb(h, s, l) {
       s /= 100; l /= 100;
       const chroma = (1 - Math.abs(2 * l - 1)) * s;
       const k = chroma * (1 - Math.abs((h / 60) % 2 - 1));
       const lightnessMatch = l - chroma / 2;
       let r = 0, g = 0, b = 0;
       if (h >= 0 && h < 60) { r = chroma; g = k; }
       else if (h >= 60 && h < 120) { r = k; g = chroma; }
       else if (h >= 120 && h < 180) { g = chroma; b = k; }
       else if (h >= 180 && h < 240) { g = k; b = chroma; }
       else if (h >= 240 && h < 300) { r = k; b = chroma; }
       else { r = chroma; b = k; }
       return {
           r: Math.round((r + lightnessMatch) * 255),
           g: Math.round((g + lightnessMatch) * 255),
           b: Math.round((b + lightnessMatch) * 255)
       };
    }
    try {
       const { r, g, b } = hexToRgb(hex);
       let { h, s, l } = rgbToHsl(r, g, b);
       s = Math.min(100, s * factor);
       l = Math.max(0, Math.min(100, l * (1 + (factor - 1) * 0.1)));
       const { r: rr, g: gg, b: bb } = hslToRgb(h, s, l);
       return `#${[rr, gg, bb].map(c => c.toString(16).padStart(2, "0")).join("")}`;
    } catch (e) {
       console.error("Saturate color error for", hex, e);
       return hex;
    }
}


// Базовая функция отрисовки колеса (с возможностью подсветки)
function drawWheelBase(highlightIndex = -1, saturationFactor = 1) {
    // --- ИЗМЕНЕНИЕ: Получаем canvas и ctx динамически ---
    const canvas = document.getElementById('wheel');
    if (!canvas) {
        console.error("drawWheelBase: Canvas element #wheel not found.");
        return;
    }
    const ctx = canvas.getContext("2d", { alpha: true });
     if (!ctx) {
        console.error("drawWheelBase: Failed to get 2D context.");
        return;
    }
    // --- КОНЕЦ ИЗМЕНЕНИЯ ---

    if (state.sectors.length === 0) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        return;
    }

    const baseSize = canvas.clientWidth;
    const centerX = baseSize / 2;
    const centerY = baseSize / 2;
    const radius = Math.max(1, Math.min(centerX, centerY) * 0.98);
    const angles = computeAngles(state.sectors.length);
    if (angles.length === 0) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const baseFontSize = Math.max(9, radius * 0.08);
    const emojiFontSize = Math.max(16, Math.round(baseFontSize * 2));
    const numberFontSize = Math.max(10, Math.round(baseFontSize * 1.1));
    const starFontSize = Math.max(9, Math.round(baseFontSize * 0.9));
    const textOffsetFactor = 0.68;
    const lineSpacing = baseFontSize * 0.25;

    for (let i = 0; i < state.sectors.length; i++) {
        const sectorData = state.sectors[i];
        if (!sectorData) continue;

        const { start, end, mid } = angles[i];
        const startRad = start * Math.PI / 180;
        const endRad = end * Math.PI / 180;
        const midRad = mid * Math.PI / 180;

        const gradientStartX = centerX + Math.cos(midRad) * (radius * 0.1);
        const gradientStartY = centerY + Math.sin(midRad) * (radius * 0.1);
        const gradientEndX = centerX + Math.cos(midRad) * radius;
        const gradientEndY = centerY + Math.sin(midRad) * radius;
        const gradient = ctx.createLinearGradient(gradientStartX, gradientStartY, gradientEndX, gradientEndY);

        const color1 = i === highlightIndex ? saturateColor(sectorData.color1, saturationFactor) : sectorData.color1;
        const color2 = i === highlightIndex ? saturateColor(sectorData.color2, saturationFactor) : sectorData.color2;

        gradient.addColorStop(0, color1);
        gradient.addColorStop(1, color2);

        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.arc(centerX, centerY, radius, startRad, endRad, false);
        ctx.closePath();

        ctx.fillStyle = gradient;
        ctx.fill();
        ctx.lineWidth = 1.5 / (window.devicePixelRatio || 1);
        ctx.strokeStyle = "rgba(255, 255, 255, 0.5)";
        ctx.stroke();

        if (i === highlightIndex) {
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(centerX, centerY);
            ctx.arc(centerX, centerY, radius, startRad, endRad, false);
            ctx.closePath();
            ctx.lineWidth = 4 / (window.devicePixelRatio || 1);
            ctx.strokeStyle = "var(--accent-gold, #FFC107)"; // Добавлен фоллбэк цвет
            ctx.shadowColor = "var(--accent-gold-shadow, rgba(255, 193, 7, 0.6))"; // Добавлен фоллбэк цвет
            ctx.shadowBlur = 15;
            ctx.stroke();
            ctx.restore();
        }
    }

    for (let i = 0; i < state.sectors.length; i++) {
         const sectorData = state.sectors[i];
         if (!sectorData) continue;

        const { mid } = angles[i];
        const midRad = mid * Math.PI / 180;

        ctx.save();
        ctx.translate(centerX, centerY);
        ctx.rotate(midRad);
        ctx.translate(radius * textOffsetFactor, 0);
        ctx.rotate(90 * Math.PI / 180);
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";

        const verticalGap = radius * 0.04;
        const emojiY = -numberFontSize / 2 - lineSpacing / 2 - emojiFontSize/2 - verticalGap/2 ;
        const numberY = 0;
        const starY = numberFontSize / 2 + lineSpacing / 2 + starFontSize / 2 + verticalGap/2;

        ctx.font = `bold ${emojiFontSize}px "Apple Color Emoji", "Segoe UI Emoji", sans-serif`;
        ctx.fillStyle = "#fff";
        ctx.shadowColor = "rgba(0,0,0,0.3)";
        ctx.shadowBlur = 3;
        ctx.fillText(sectorData.emoji, 0, emojiY);

        ctx.font = `bold ${numberFontSize}px 'Montserrat', sans-serif`;
        ctx.fillText(sectorData.costNumber.toString(), 0, numberY);

        ctx.font = `bold ${starFontSize}px 'Montserrat', sans-serif`;
        ctx.fillText("⭐", 0, starY);


        ctx.restore();
    }
}

// --- Экспортируемые функции ---

/**
 * Создает массив секторов на основе конфига и выбранной стоимости.
 * Возвращает новый массив секторов, не изменяет state напрямую.
 * @param {number} cost - Выбранная стоимость (25, 50, 100) для определения весов в демо.
 * @returns {Array} - Массив объектов секторов с добавленными цветами и весами.
 */
export function buildSectors(cost = 25) {
    const sectors = configItems.map((item, i) => ({
        ...item,
        weight: item.distribution?.[cost] ?? 0,
        ...mainColorPairs[i % mainColorPairs.length]
    }));
    // console.log(`Sectors built for cost ${cost}:`, sectors); // Можно раскомментировать для отладки
    return sectors;
}

/**
 * Настраивает размер Canvas в соответствии с DPR.
 */
export function setupCanvas() {
     // --- ИЗМЕНЕНИЕ: Получаем canvas динамически ---
    const canvas = document.getElementById('wheel');
    if (!canvas) {
        console.warn("setupCanvas: Canvas element #wheel not found.");
        return null; // Возвращаем null, если canvas не найден
    }
    const ctx = canvas.getContext("2d", { alpha: true });
     if (!ctx) {
        console.warn("setupCanvas: Failed to get 2D context.");
        return null; // Возвращаем null, если контекст не получен
    }
     // --- КОНЕЦ ИЗМЕНЕНИЯ ---

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) {
        console.warn("Canvas dimensions are zero during setup.");
        return ctx; // Возвращаем ctx, но размеры могут быть некорректны
    }
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;
    ctx.scale(dpr, dpr);
    console.log(`Canvas setup: ${canvas.width}x${canvas.height} (logical ${rect.width}x${rect.height}), DPR=${dpr}`);
    return ctx; // Возвращаем полученный контекст
}


/**
 * Обновляет размер колеса и перерисовывает его.
 * Вызывается при инициализации и ресайзе окна.
 */
export function updateWheelSizeAndRedraw() {
     // --- ИЗМЕНЕНИЕ: Получаем canvas динамически ---
     const canvas = document.getElementById('wheel');
     if (!canvas || !window.gsap) {
         console.warn("updateWheelSizeAndRedraw: canvas or gsap not available.");
         return;
     }
     // --- КОНЕЦ ИЗМЕНЕНИЯ ---

     const ctx = setupCanvas(); // Настраиваем размер и scale, получаем контекст
     if (!ctx) return; // Выходим, если контекст не получен

     const baseSize = canvas.clientWidth;
     state.wheelSize = baseSize > 10 ? baseSize : 300;
     console.log(`Wheel size updated to: ${state.wheelSize}`);

     gsap.set(canvas, { rotation: state.currentRotation, overwrite: true });

     drawWheel(); // Перерисовываем колесо с новым размером
}

/**
 * Рисует колесо в его текущем состоянии (без подсветки).
 */
export function drawWheel() {
    drawWheelBase(-1); // Вызов базовой отрисовки без подсветки
}

/**
 * Рисует колесо, подсвечивая указанный сектор.
 * @param {number} winningIndex - Индекс сектора для подсветки.
 * @param {number} saturationFactor - Фактор насыщенности для эффекта пульсации.
 */
export function drawWheelHighlight(winningIndex, saturationFactor = 1.6) {
    drawWheelBase(winningIndex, saturationFactor);
}