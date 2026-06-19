import { tg } from './dom.js';
import { fetchUserState } from './api.js';
import { formatDateTime, formatTimeLeft } from './utils.js';
import { animateCounter } from './ui.js';

const profileContainer = document.querySelector('#profile-tab .profile-container');
const profileHeader = document.querySelector('.profile-header');
const profileStatsContainer = document.querySelector('.profile-stats');
const profileRefSection = document.querySelector('.profile-ref-link-section');
const profileWithdrawalSection = document.querySelector('.profile-withdrawal-status');
const profileNameEl = document.getElementById('profile-name');
const profileUserIdEl = document.getElementById('profile-user-id');
const profileBalanceEl = document.getElementById('profile-balance');
const profileRefsTotalEl = document.getElementById('profile-refs-total');
const profileRefsWeekEl = document.getElementById('profile-refs-week');
const profileRefLinkEl = document.getElementById('profile-ref-link');
const copyRefLinkBtn = document.getElementById('copy-ref-link-btn');
const shareRefLinkBtn = document.getElementById('share-ref-link-btn');
const profileExchangeStatusEl = document.getElementById('profile-exchange-status');
const profileExchangeRequirementEl = document.getElementById('profile-exchange-requirement');
const withdrawalHistoryListEl = document.getElementById('withdrawal-history-list');
const noWithdrawalHistoryEl = document.getElementById('no-withdrawal-history');
const withdrawalHistoryContainer = document.querySelector('.profile-withdrawal-history');
const refsProgressContainer = document.getElementById('refs-progress-container');
const refsProgressBar = document.getElementById('refs-progress-bar');
const refsProgressText = document.getElementById('refs-progress-text');
const boostDisplayEl = document.getElementById('profile-boost-display');
const boostContainerEl = document.querySelector('.profile-boost-status');


function renderWithdrawalHistory(history) {
    if (!withdrawalHistoryListEl || !noWithdrawalHistoryEl || !withdrawalHistoryContainer) return;
    withdrawalHistoryListEl.innerHTML = '';
    if (!history || history.length === 0) {
        noWithdrawalHistoryEl.style.display = 'block';
        withdrawalHistoryListEl.style.display = 'none';
        return;
    }
    noWithdrawalHistoryEl.style.display = 'none';
    withdrawalHistoryListEl.style.display = 'block';
    history.forEach(item => {
        const li = document.createElement('li');
        li.classList.add('withdrawal-item');
        let statusText = '❓ Неизвестно';
        let statusClass = 'status-unknown';
        switch (item.status?.toLowerCase()) {
            case 'pending': statusText = '⏳ В процессе'; statusClass = 'status-pending'; break;
            case 'approved': statusText = '✅ Одобрен'; statusClass = 'status-approved'; break;
            case 'rejected': statusText = '❌ Отклонен'; statusClass = 'status-rejected'; break;
        }
        li.classList.add(statusClass);
        const amount = item.amount || 0;
        const timestampFormatted = item.timestamp ? formatDateTime(item.timestamp) : 'N/A';
        li.innerHTML = `
            <span class="withdrawal-date">${timestampFormatted}</span>
            <span class="withdrawal-amount">${amount.toFixed(0)} ⭐</span>
            <span class="withdrawal-status">${statusText}</span>
        `;
        withdrawalHistoryListEl.appendChild(li);
    });
}

function showProfilePlaceholders() {
    if (profileNameEl) profileNameEl.innerHTML = '<div class="profile-placeholder" style="width: 60%;"></div>';
    if (profileUserIdEl) profileUserIdEl.textContent = '...';

    const avatarElement = document.getElementById('profile-avatar-img');
    if (avatarElement) {
        avatarElement.src = '';
        avatarElement.classList.add('no-photo');
        avatarElement.alt = "Loading Avatar...";
    }

    const topUpBtnPlaceholder = document.getElementById('profile-topup-button-placeholder');
    if (topUpBtnPlaceholder) {
        topUpBtnPlaceholder.innerHTML = '<div class="profile-placeholder" style="width: 100%; height: 38px;"></div>';
    }

    if (profileBalanceEl) profileBalanceEl.innerHTML = '<div class="profile-placeholder" style="width: 50%; margin: auto;"></div>';
    if (profileRefsTotalEl) profileRefsTotalEl.innerHTML = '<div class="profile-placeholder" style="width: 30%; margin: auto;"></div>';
    if (profileRefsWeekEl) profileRefsWeekEl.innerHTML = '<div class="profile-placeholder" style="width: 30%; margin: auto;"></div>';
    if (refsProgressContainer) refsProgressContainer.style.visibility = 'hidden';
    if (refsProgressBar) refsProgressBar.style.width = '0%';
    if (refsProgressText) refsProgressText.textContent = '-/-';
    if (profileRefLinkEl) profileRefLinkEl.textContent = 'Загрузка...';
    if (profileExchangeStatusEl) profileExchangeStatusEl.innerHTML = '<div class="profile-placeholder" style="width: 60%; margin: auto;"></div>';
    if (profileExchangeRequirementEl) profileExchangeRequirementEl.textContent = '(Требуется: ... реф. за неделю)';
    if (boostDisplayEl) boostDisplayEl.innerHTML = '<div class="profile-placeholder" style="width: 70%; margin: auto;"></div>';
    if (copyRefLinkBtn) copyRefLinkBtn.disabled = true;
    if (shareRefLinkBtn) shareRefLinkBtn.disabled = true;
    if (withdrawalHistoryListEl) withdrawalHistoryListEl.innerHTML = '<li class="loading-placeholder">Загрузка истории...</li>';
    if (noWithdrawalHistoryEl) noWithdrawalHistoryEl.style.display = 'none';
    if (withdrawalHistoryListEl) withdrawalHistoryListEl.style.display = 'block';
    if (withdrawalHistoryContainer) withdrawalHistoryContainer.style.display = 'block';
    if (boostContainerEl) boostContainerEl.style.display = 'block';


    if (profileHeader) profileHeader.style.opacity = '1';
    if (profileStatsContainer) profileStatsContainer.style.opacity = '1';
    if (profileRefSection) profileRefSection.style.opacity = '1';
    if (profileWithdrawalSection) profileWithdrawalSection.style.opacity = '1';
    if (withdrawalHistoryContainer) withdrawalHistoryContainer.style.opacity = '1';
    if (boostContainerEl) boostContainerEl.style.opacity = '1';
}

function hideProfilePlaceholders() {
    if (profileContainer) profileContainer.style.opacity = '1';
    if (refsProgressContainer) refsProgressContainer.style.visibility = 'visible';
    const topUpBtnPlaceholder = document.getElementById('profile-topup-button-placeholder');
    if (topUpBtnPlaceholder) {
        topUpBtnPlaceholder.innerHTML = '';
    }
}

function showProfileError(message) {
    hideProfilePlaceholders();
    if (profileNameEl) profileNameEl.textContent = "Ошибка";
    if (profileUserIdEl) profileUserIdEl.textContent = '-';
    const avatarElement = document.getElementById('profile-avatar-img');
    if (avatarElement) {
        avatarElement.src = '';
        avatarElement.classList.add('no-photo');
        avatarElement.alt = "Error loading avatar";
    }
    if (profileBalanceEl) profileBalanceEl.textContent = '-';
    if (profileRefsTotalEl) profileRefsTotalEl.textContent = '-';
    if (profileRefsWeekEl) profileRefsWeekEl.textContent = '-';
    if (refsProgressContainer) refsProgressContainer.style.visibility = 'hidden';
    if (profileRefLinkEl) profileRefLinkEl.textContent = 'Ошибка';
    if (profileExchangeStatusEl) profileExchangeStatusEl.textContent = 'Ошибка';
    if (profileExchangeRequirementEl) profileExchangeRequirementEl.textContent = '';
    if (boostDisplayEl) boostDisplayEl.textContent = 'Ошибка загрузки бустов.';
    if (withdrawalHistoryListEl) withdrawalHistoryListEl.innerHTML = `<li class="error-placeholder">${message}</li>`;
    if (noWithdrawalHistoryEl) noWithdrawalHistoryEl.style.display = 'none';
    if (withdrawalHistoryListEl) withdrawalHistoryListEl.style.display = 'block';
    if (withdrawalHistoryContainer) withdrawalHistoryContainer.style.display = 'block';
    if (boostContainerEl) boostContainerEl.style.display = 'block';
    tg?.showAlert(message);
}

export async function loadProfileData() {
    if (!profileContainer) {
        return;
    }
    profileContainer.classList.remove('loaded');
    showProfilePlaceholders();

    try {
        const data = await fetchUserState();

        if (data && data.ok) {
            hideProfilePlaceholders();

            const avatarElement = document.getElementById('profile-avatar-img');
            const photoUrl = data.photo_url;
            if (avatarElement) {
                if (photoUrl) {
                    avatarElement.src = photoUrl;
                    avatarElement.alt = "User Avatar";
                    avatarElement.classList.remove('no-photo');
                    avatarElement.onerror = () => {
                        avatarElement.classList.add('no-photo');
                        avatarElement.src = '';
                    };
                } else {
                    avatarElement.src = '';
                    avatarElement.alt = "Default Avatar";
                    avatarElement.classList.add('no-photo');
                }
            }

            const userName = data.username || 'Пользователь';
            const userId = data.user_id || 'N/A';
            if (profileNameEl) profileNameEl.textContent = userName;
            if (profileUserIdEl) profileUserIdEl.textContent = userId;

            if (profileBalanceEl) animateCounter(profileBalanceEl, data.balance ?? 0, '', 0.6, 2);
            if (profileRefsTotalEl) animateCounter(profileRefsTotalEl, data.total_referrals ?? 0, '', 0.6, 0);
            const weeklyRefs = data.weekly_referrals ?? 0;
            if (profileRefsWeekEl) animateCounter(profileRefsWeekEl, weeklyRefs, '', 0.6, 0);

            const userBotUsername = "zvezdopadtg_bot";
            const refLink = userId !== 'N/A' ? `https://t.me/${userBotUsername}?start=${userId}` : 'Недоступна';
            if (profileRefLinkEl) profileRefLinkEl.textContent = refLink;
            if (copyRefLinkBtn) copyRefLinkBtn.disabled = (refLink === 'Недоступна');
            if (shareRefLinkBtn) shareRefLinkBtn.disabled = (refLink === 'Недоступна');

            const requirement = data.withdrawal_requirement ?? 10;
            const canExchange = weeklyRefs >= requirement;
            if (profileExchangeStatusEl) {
                profileExchangeStatusEl.textContent = canExchange ? "✅ Доступен" : `❌ Не доступен`;
                profileExchangeStatusEl.className = canExchange ? 'available' : 'unavailable';
            }
            if (profileExchangeRequirementEl) profileExchangeRequirementEl.textContent = `(Требуется: ${requirement} реф. за неделю)`;

            if(refsProgressBar && refsProgressText && refsProgressContainer) {
                const progressPercent = Math.min(100, Math.max(0, (weeklyRefs / requirement) * 100));
                refsProgressBar.style.width = `${progressPercent}%`;
                refsProgressText.textContent = `${weeklyRefs}/${requirement}`;
                refsProgressContainer.title = `Прогресс до обмена: ${progressPercent.toFixed(0)}%`;
                refsProgressContainer.style.visibility = 'visible';
            }

            if (boostDisplayEl && boostContainerEl) {
                if (data.active_boosts && data.active_boosts.length > 0) {
                    let boostsText = "";
                    data.active_boosts.forEach(boost => {
                        const expiresDate = boost.expires_at_iso ? new Date(boost.expires_at_iso) : null;
                        const expiresDisplay = expiresDate ? formatDateTime(expiresDate.getTime() / 1000) : 'N/A';
                        let timeLeftDisplay = 'Вечный';
                        if (expiresDate) {
                            const secondsLeft = (expiresDate.getTime() - Date.now()) / 1000;
                            if (secondsLeft > 0) {
                                timeLeftDisplay = formatTimeLeft(secondsLeft);
                            } else {
                                timeLeftDisplay = 'Истёк';
                            }
                        }

                        let boostName = boost.type_name || 'Активный Буст';

                        boostsText += `<strong style="color: var(--text-color-main);">${boostName}</strong>: Активен <br>(до ${expiresDisplay}, ост. ~${timeLeftDisplay})<br><br>`;
                    });
                    boostDisplayEl.innerHTML = boostsText.trimEnd().replace(/<br><br>$/,'<br>');
                    boostContainerEl.style.display = 'block';
                } else {
                    boostDisplayEl.textContent = 'Нет активных бустов.';
                    boostContainerEl.style.display = 'block';
                }
            }


            renderWithdrawalHistory(data.withdrawal_history);

            const profileHeaderDiv = document.querySelector('.profile-header');
            const topUpButtonContainer = document.getElementById('profile-topup-button-placeholder');

            if (profileHeaderDiv && topUpButtonContainer) {
                topUpButtonContainer.innerHTML = '';
                let topUpButton = document.getElementById('top-up-balance-profile-btn');
                if (!topUpButton) {
                    topUpButton = document.createElement('button');
                    topUpButton.id = 'top-up-balance-profile-btn';
                    topUpButton.innerHTML = '💰 <span class="profile-topup-button-text">Пополнить</span>';
                    topUpButton.title = 'Пополнить баланс';
                    topUpButton.classList.add('profile-topup-action-button');

                    topUpButton.addEventListener('click', () => {
                        window.open('https://t.me/payZvezdopadtg_bot', '_blank');
                    });
                    topUpButtonContainer.appendChild(topUpButton);
                }
            } else {
                 console.error("Элемент .profile-header или #profile-topup-button-placeholder не найден для кнопки пополнения.");
            }

            setTimeout(() => {
                profileContainer.classList.add('loaded');
                if (profileContainer) void profileContainer.offsetWidth;
            }, 50);

        } else {
            console.error("Failed to fetch profile data or data.ok is false. Response:", data);
            showProfileError(data?.error || 'Не удалось загрузить данные профиля.');
            profileContainer.classList.add('loaded');
        }

    } catch (error) {
        console.error("Error fetching profile data:", error);
        showProfileError(`Ошибка сети: ${error.message}`);
        profileContainer.classList.add('loaded');
    }
}

export function initProfileTab() {
    if (copyRefLinkBtn && profileRefLinkEl) {
        const originalIcon = copyRefLinkBtn.innerHTML;
        const successIcon = '✅';
        copyRefLinkBtn.addEventListener('click', () => {
            const link = profileRefLinkEl.textContent;
            if (link && link !== 'Недоступна' && !copyRefLinkBtn.disabled && !copyRefLinkBtn.classList.contains('copied')) {
                navigator.clipboard.writeText(link)
                    .then(() => {
                        copyRefLinkBtn.innerHTML = successIcon;
                        copyRefLinkBtn.classList.add('copied');
                        copyRefLinkBtn.disabled = true;
                        tg?.showPopup({ message: 'Ссылка скопирована!' });
                        if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
                        setTimeout(() => {
                            copyRefLinkBtn.innerHTML = originalIcon;
                            copyRefLinkBtn.classList.remove('copied');
                            copyRefLinkBtn.disabled = (profileRefLinkEl.textContent === 'Недоступна');
                        }, 2000);
                    })
                    .catch(err => {
                        console.error('Failed to copy ref link: ', err);
                        tg?.showAlert('Не удалось скопировать ссылку.');
                        if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('error');
                    });
            }
        });
    }

    if (shareRefLinkBtn && profileRefLinkEl) {
        shareRefLinkBtn.addEventListener('click', () => {
            const link = profileRefLinkEl.textContent;
            const shareText = `🚀 Присоединяйся к боту и зарабатывай звезды!\n\nМоя ссылка: ${link}`;
            if (link && link !== 'Недоступна' && !shareRefLinkBtn.disabled && tg?.openTelegramLink) {
                try {
                    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(shareText)}`;
                    tg.openTelegramLink(shareUrl);
                } catch (e) {
                    console.error("Error opening share link:", e);
                    tg?.showAlert("Не удалось открыть окно 'Поделиться'.");
                }
            } else if (!tg?.openTelegramLink) {
                console.warn("Telegram share method (openTelegramLink) unavailable.");
                tg?.showAlert("Функция 'Поделиться' недоступна в вашем клиенте Telegram.");
            }
        });
    }
}