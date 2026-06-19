// dom.js
console.log("--- EXECUTING dom.js v_FINAL (No Canvas/Ctx Check) ---"); // Проверочный лог

export const tg = window.Telegram.WebApp;

// --- Основные элементы, которые есть всегда ---
export const appContainer = document.getElementById("appContainer");
export const errorMessageEl = document.getElementById("errorMessage");

// --- Элементы, специфичные для игр (колесо и т.д.), УБРАНЫ ОТСЮДА ---
// Они будут получаться динамически внутри функций, которые их используют.

// --- Инициализация и проверка TG ---
if (!tg) {
    console.error("TG WebApp not loaded!");
    if (errorMessageEl) {
        errorMessageEl.textContent = "Не удалось загрузить API Telegram. Функциональность может быть ограничена.";
        errorMessageEl.style.display = 'block';
    }
} else {
    console.log("TG WebApp API found:", tg);
    // Инициализация TG (ready, expand) лучше делать в main.js после загрузки DOM
    // tg.ready();
    tg.BackButton.hide(); // Скрытие кнопки Назад можно оставить здесь или перенести
}

console.log("--- FINISHED dom.js v_FINAL ---"); // Проверочный лог