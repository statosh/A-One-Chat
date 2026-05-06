$('close-change-modal').addEventListener('click', () => toggleModal('change-nickname-modal', false));

$('modal-overlay').addEventListener('click', () => {
    ['change-nickname-modal', 'create-room-modal', 'edit-room-modal', 'room-password-modal', 'welcome-modal', 'users-modal'].forEach(id => {
        if ($(id).style.display === 'block') toggleModal(id, false);
    });
});

['change-nickname-modal', 'welcome-modal', 'create-room-modal', 'edit-room-modal', 'room-password-modal', 'users-modal'].forEach(id => {
    $(id).addEventListener('click', e => e.stopPropagation());
});

Object.assign(RoomsState, {
    userCountsCache: null
});

/**
 * Инициализирует тему оформления (светлая/темная) из сохраненных настроек
 * 
 * Входы: отсутствуют
 * Выходы: отсутствует (устанавливает атрибут data-theme и иконку кнопки)
 */
function initTheme() {
    const saved = localStorage.getItem('theme');
    if (saved === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        const btn = document.getElementById('theme-toggle-btn');
        if (btn) btn.innerHTML = '<i class="fa-solid fa-sun"></i>';
    }
}

const themeBtn = document.getElementById('theme-toggle-btn');
if (themeBtn) {
    themeBtn.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme');
        if (current === 'dark') {
            document.documentElement.removeAttribute('data-theme');
            localStorage.setItem('theme', 'light');
            themeBtn.innerHTML = '<i class="fa-solid fa-moon"></i>';
        } else {
            document.documentElement.setAttribute('data-theme', 'dark');
            localStorage.setItem('theme', 'dark');
            themeBtn.innerHTML = '<i class="fa-solid fa-sun"></i>';
        }
    });
}

/**
 * Инициализирует приложение: загружает гостевые данные, проверяет токен,
 * загружает комнаты и устанавливает WebSocket соединение
 * 
 * Входы: отсутствуют
 * Выходы: отсутствует
 */
async function init() {
    initTheme();
    await fetchGuestData();

    const token = localStorage.getItem('auth_token');
    if (token) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000);

            const r = await fetch('/api/verify-token', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    token
                }),
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            if (r.ok) {
                currentUser = await r.json();
                syncState();
            } else localStorage.removeItem('auth_token');
        } catch (e) {}
    }

    updateHeader();
    loadRooms();
    connectGlobalWs();
}

init();