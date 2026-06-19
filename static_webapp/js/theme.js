import { tg } from './dom.js';

function applyThemeStyles() {
    if (!tg || !tg.themeParams) {
        console.warn("Telegram themeParams not available.");
        return;
    }

    const theme = tg.themeParams;
    console.log("Applying theme params:", theme);

    document.documentElement.style.setProperty('--app-bg-color', theme.bg_color || '#ffffff');
    document.documentElement.style.setProperty('--secondary-bg-color', theme.secondary_bg_color || '#f8f9fa');
    document.documentElement.style.setProperty('--text-color-main', theme.text_color || '#212121');
    document.documentElement.style.setProperty('--text-color-secondary', theme.hint_color || '#616161');
    document.documentElement.style.setProperty('--text-color-link', theme.link_color || '#4094ff');

    document.documentElement.style.setProperty('--button-bg-color', theme.button_color || '#7e57c2');
    document.documentElement.style.setProperty('--button-text-color', theme.button_text_color || '#ffffff');

    document.documentElement.style.setProperty('--primary-purple', theme.button_color || '#7e57c2');
    document.documentElement.style.setProperty('--primary-purple-dark', theme.button_color || '#6b44af');
    document.documentElement.style.setProperty('--text-dark', theme.text_color || '#212121');
    document.documentElement.style.setProperty('--text-medium', theme.text_color || '#424242');
    document.documentElement.style.setProperty('--text-light', theme.hint_color || '#616161');
    document.documentElement.style.setProperty('--text-link', theme.link_color || '#4094ff');
    document.documentElement.style.setProperty('--text-white', theme.button_text_color || '#ffffff');
    document.documentElement.style.setProperty('--container-bg', theme.bg_color || 'rgba(255, 255, 255, 0.98)');
    document.documentElement.style.setProperty('--card-bg-color', theme.secondary_bg_color || '#ffffff');

    document.body.style.backgroundColor = theme.bg_color || '#eeeeee';
    const appContainerEl = document.getElementById('appContainer');
    if(appContainerEl) appContainerEl.style.backgroundColor = theme.bg_color || 'rgba(255, 255, 255, 0.98)';

    if (tg.setHeaderColor) {
         tg.setHeaderColor(theme.secondary_bg_color || '#ffffff');
    }
     if (tg.setBackgroundColor) {
         tg.setBackgroundColor(theme.bg_color || '#ffffff');
     }

    console.log("Theme styles applied.");
}

export function initTheme() {
    applyThemeStyles();

    if (tg && tg.onEvent) {
        tg.onEvent('themeChanged', applyThemeStyles);
        console.log("Theme change listener added.");
    } else {
        console.log("Could not add theme change listener (tg or onEvent not available).");
    }
}