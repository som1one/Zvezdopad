import { loadProfileData } from './profile.js';
import { loadGameHistory } from './history.js';
import { initTargetTab } from './target.js';

function switchTab(targetTabId, tabButtons, tabPanels) {
    tabPanels.forEach(panel => {
        panel.classList.remove('active');
    });
    tabButtons.forEach(button => {
        button.classList.remove('active');
    });

    const targetPanel = document.getElementById(targetTabId);
    const targetButton = document.querySelector(`.tab-button[data-tab="${targetTabId}"]`);

    if (targetPanel && targetButton) {
        targetPanel.classList.add('active');
        targetButton.classList.add('active');
        console.log(`Switched to tab: ${targetTabId}`);

        if (targetTabId === 'profile-tab') {
             loadProfileData();
        } else if (targetTabId === 'history-tab') {
             loadGameHistory();
        } else if (targetTabId === 'games-tab') {
             console.log("Games tab activated.");
        } else if (targetTabId === 'target-tab') {
            initTargetTab();
        }
    } else {
        console.error(`Could not find tab panel or button for ID: ${targetTabId}`);
        const firstAvailableTabButton = tabButtons.length > 0 ? tabButtons[0] : null;
        if (firstAvailableTabButton && targetTabId !== firstAvailableTabButton.dataset.tab) {
             console.warn(`Fallback to first tab: ${firstAvailableTabButton.dataset.tab}`);
             switchTab(firstAvailableTabButton.dataset.tab, tabButtons, tabPanels);
        }
    }
}

export function setupTabs() {
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabPanels = document.querySelectorAll('.tab-panel');
    const tabBar = document.getElementById('tab-bar');

    if (!tabBar || tabButtons.length === 0 || tabPanels.length === 0) {
        console.error("Tab elements not found for setupTabs!");
        return;
    }

    function setVhVariable() {
        let vh = window.innerHeight * 0.01;
        document.documentElement.style.setProperty('--vh', `${vh}px`);
    }
    setVhVariable();
    window.addEventListener('resize', setVhVariable);

    tabBar.addEventListener('click', (event) => {
        const button = event.target.closest('.tab-button');
        if (button && button.dataset.tab) {
            const targetTabId = button.dataset.tab;
            if (!button.classList.contains('active')) {
                switchTab(targetTabId, tabButtons, tabPanels);
                if (window.Telegram?.WebApp?.HapticFeedback) {
                    try { window.Telegram.WebApp.HapticFeedback.selectionChanged(); }
                    catch (hfError) { console.warn("HapticFeedback error:", hfError); }
                }
            }
        }
    });

    let activeTabIdFromHTML = null;
    tabPanels.forEach(panel => {
        const correspondingButton = document.querySelector(`.tab-button[data-tab="${panel.id}"]`);
        if (panel.classList.contains('active') && correspondingButton) {
            activeTabIdFromHTML = panel.id;
            correspondingButton.classList.add('active');
        } else if (correspondingButton) {
            correspondingButton.classList.remove('active');
        }
        if (!panel.classList.contains('active')) {
            panel.classList.remove('active');
        }
    });

    if (!activeTabIdFromHTML && tabPanels.length > 0) {
        const firstPanel = tabPanels[0];
        const firstButton = document.querySelector(`.tab-button[data-tab="${firstPanel.id}"]`);
        if (firstPanel && firstButton) {
            firstPanel.classList.add('active');
            firstButton.classList.add('active');
            activeTabIdFromHTML = firstPanel.id;
            console.log(`Defaulting to first tab: ${activeTabIdFromHTML}`);
        }
    }
    console.log("Tab switching logic initialized. Initial data load deferred to main.js.");
}