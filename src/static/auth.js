/**
 * Модуль для централизованного хранения состояния приложения
 * @namespace AppState
 */
const AppState = (function() {
    let _currentUser = null;
    let _guestNickname = '';
    let _guestColor = '#888888';
    let _creatorNames = {};

    return {
        /**
         * Возвращает текущего авторизованного пользователя
         * @returns {Object|null} Объект пользователя или null
         */
        get currentUser() {
            return _currentUser;
        },
        
        /**
         * Устанавливает текущего пользователя с валидацией
         * @param {Object|null} val - Объект пользователя (должен содержать id, username, token)
         */
        set currentUser(val) {
            if (val && typeof val === 'object') {
                if (!val.id || !val.username || !val.token) {
                    return;
                }
            }
            _currentUser = val;
        },
        
        /**
         * Возвращает гостевой никнейм
         * @returns {string} Гостевой никнейм
         */
        get guestNickname() {
            return _guestNickname;
        },
        
        /**
         * Устанавливает гостевой никнейм с ограничением длины
         * @param {string} val - Гостевой никнейм (обрезается до 25 символов)
         */
        set guestNickname(val) {
            _guestNickname = String(val).substring(0, 25);
        },
        
        /**
         * Возвращает цвет гостя
         * @returns {string} Цвет в формате HEX
         */
        get guestColor() {
            return _guestColor;
        },
        
        /**
         * Устанавливает цвет гостя с проверкой формата
         * @param {string} val - Цвет в формате HEX
         */
        set guestColor(val) {
            if (/^#[0-9a-fA-F]{6}$/.test(val)) {
                _guestColor = val;
            }
        },
        
        /**
         * Возвращает объект с именами создателей комнат
         * @returns {Object} Объект вида {creatorId: creatorName}
         */
        get creatorNames() {
            return _creatorNames;
        },
        
        /**
         * Сохраняет имя создателя комнаты
         * @param {number|string} id - ID создателя
         * @param {string} name - Имя создателя (обрезается до 25 символов)
         */
        setCreatorName(id, name) {
            if (id && name) {
                _creatorNames[id] = String(name).substring(0, 25);
            }
        }
    };
})();

let currentUser = null,
    guestNickname = '',
    guestColor = '#888888',
    creatorNames = {};

/**
 * Синхронизирует глобальные переменные с состоянием AppState
 * 
 * Входы: отсутствуют
 * Выходы: отсутствуют
 */
function syncState() {
    AppState.currentUser = currentUser;
    AppState.guestNickname = guestNickname;
    AppState.guestColor = guestColor;
    AppState.creatorNames = creatorNames;
}

/**
 * Получает сохраненный токен авторизации из хранилища
 * 
 * Входы: отсутствуют
 * Выходы:
 *     {string|null} Токен авторизации или null, если не найден
 */
function getStoredToken() {
    try {
        return sessionStorage.getItem('auth_token') || localStorage.getItem('auth_token');
    } catch (e) {
        return null;
    }
}

/**
 * Сохраняет токен авторизации в sessionStorage и localStorage
 * 
 * Входы:
 *     token {string} - Токен для сохранения
 * 
 * Выходы: отсутствуют
 */
function storeToken(token) {
    try {
        sessionStorage.setItem('auth_token', token);
        localStorage.setItem('auth_token', token);
    } catch (e) {}
}

/**
 * Удаляет токен авторизации из хранилищ
 * 
 * Входы: отсутствуют
 * Выходы: отсутствуют
 */
function clearToken() {
    try {
        sessionStorage.removeItem('auth_token');
        localStorage.removeItem('auth_token');
    } catch (e) {}
}

/**
 * Загружает гостевые данные (никнейм, цвет, токен) с сервера
 * 
 * Входы: отсутствуют
 * Выходы: отсутствуют (обновляет глобальные переменные guestNickname, guestColor)
 */
async function fetchGuestData() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);

        const r = await fetch('/api/guest-nickname', {
            signal: controller.signal,
            credentials: 'same-origin'
        });
        clearTimeout(timeoutId);

        const d = await r.json();
        guestNickname = d.nickname;
        guestColor = d.color;

        if (d.token) {
            sessionStorage.setItem('guest_token', d.token);
        }

        AppState.guestNickname = guestNickname;
        AppState.guestColor = guestColor;
    } catch (e) {
        guestNickname = 'Guest_' + Math.random().toString(36).substr(2, 5);
        guestColor = '#888888';
        AppState.guestNickname = guestNickname;
        AppState.guestColor = guestColor;
    }
}

/**
 * Обновляет шапку интерфейса в зависимости от статуса авторизации
 * 
 * Входы: отсутствуют (использует глобальные переменные currentUser, guestNickname, guestColor)
 * Выходы: отсутствуют (обновляет DOM-элементы)
 */
function updateHeader() {
    if (currentUser) {
        $('username-display').textContent = currentUser.username;
        $('username-display').style.color = currentUser.color;
        $('auth-action-btn').textContent = 'Выйти';
        $('username-display').style.cursor = 'pointer';
        $('create-room-button').style.display = 'block';
    } else {
        $('username-display').textContent = guestNickname;
        $('username-display').style.color = guestColor;
        $('auth-action-btn').textContent = 'Войти';
        $('username-display').style.cursor = 'default';
        $('create-room-button').style.display = 'none';
    }
}

/**
 * Загружает имя создателя комнаты по ID
 * 
 * Входы:
 *     creatorId {number|string|null} - ID создателя комнаты
 * 
 * Выходы:
 *     {Promise<string>} Имя создателя или 'Система' при ошибке
 */
async function fetchCreatorName(creatorId) {
    if (!creatorId) return 'Система';
    if (creatorNames[creatorId]) return creatorNames[creatorId];

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);

        const r = await fetch(`/api/user/${creatorId}`, {
            signal: controller.signal,
            credentials: 'same-origin'
        });
        clearTimeout(timeoutId);

        if (r.ok) {
            const d = await r.json();
            const name = sanitizeUserInput(d.username).substring(0, 25);
            creatorNames[creatorId] = name;
            AppState.setCreatorName(creatorId, name);
            return name;
        }
    } catch (e) {}

    creatorNames[creatorId] = 'Система';
    return 'Система';
}

/**
 * Обработчик кнопки авторизации (вход/выход)
 * @async
 */
$('auth-action-btn').addEventListener('click', async () => {
    if (currentUser) {
        currentUser = null;
        clearToken();
        AppState.currentUser = null;

        if (currentRoomId) {
            leaveRoom();
        }

        await fetchGuestData();
        updateHeader();
        loadRooms();
    } else {
        if (currentRoomId) leaveRoom();
        $('login-username').value = '';
        $('login-password').value = '';
        toggleModal('welcome-modal', true);
    }
});

/**
 * Обработчик кнопки входа как гость
 * @async
 */
$('guest-btn').addEventListener('click', async () => {
    if (currentRoomId) leaveRoom();

    await fetchGuestData();
    currentUser = null;
    clearToken();
    AppState.currentUser = null;
    updateHeader();
    toggleModal('welcome-modal', false);
});

/**
 * Обработчик кнопки регистрации
 * @async
 */
$('register-btn-modal').addEventListener('click', async () => {
    const u = sanitizeUserInput($('login-username').value.trim());
    const p = $('login-password').value;

    if (!u || !p) return alert('Заполните логин и пароль');
    if (u.length > 25) return alert('Имя не может быть длиннее 25 символов');
    if (p.length > 35) return alert('Пароль не может быть длиннее 35 символов');
    if (p.length < 4) return alert('Пароль должен быть не менее 4 символов');

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        const r = await fetch('/api/register', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                username: u,
                password: p
            }),
            signal: controller.signal,
            credentials: 'same-origin'
        });
        clearTimeout(timeoutId);

        if (r.ok) {
            const d = await r.json();
            if (currentRoomId) leaveRoom();
            currentUser = d;
            AppState.currentUser = d;
            storeToken(d.token);
            updateHeader();
            toggleModal('welcome-modal', false);
            loadRooms();
        } else {
            const err = await r.json();
            alert(err.detail || 'Ошибка регистрации');
        }
    } catch (e) {
        if (e.name === 'AbortError') {
            alert('Превышено время ожидания.');
        } else {
            alert('Ошибка сети.');
        }
    }
});

/**
 * Обработчик кнопки входа в систему
 * @async
 */
$('login-btn-modal').addEventListener('click', async () => {
    const u = sanitizeUserInput($('login-username').value.trim());
    const p = $('login-password').value;

    if (!u || !p) return alert('Заполните логин и пароль');

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        const r = await fetch('/api/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                username: u,
                password: p
            }),
            signal: controller.signal,
            credentials: 'same-origin'
        });
        clearTimeout(timeoutId);

        if (r.ok) {
            const d = await r.json();
            if (currentRoomId) leaveRoom();
            currentUser = d;
            AppState.currentUser = d;
            storeToken(d.token);
            updateHeader();
            toggleModal('welcome-modal', false);
            loadRooms();
        } else {
            const err = await r.json();
            alert(err.detail || 'Ошибка входа');
        }
    } catch (e) {
        if (e.name === 'AbortError') {
            alert('Превышено время ожидания.');
        } else {
            alert('Ошибка сети.');
        }
    }
});

/**
 * Обработчик клика по отображаемому имени пользователя (открытие модального окна профиля)
 */
$('username-display').addEventListener('click', () => {
    if (!currentUser) return;
    $('new-nickname-input').value = currentUser.username;
    initColorPicker('change-color-picker', currentUser.color);
    toggleModal('change-nickname-modal', true);
});

/**
 * Обработчик сохранения изменений профиля
 * @async
 */
$('save-profile-btn').addEventListener('click', async () => {
    const nick = sanitizeUserInput($('new-nickname-input').value.trim());
    const color = getColor('change-color-picker');

    if (!nick) return alert('Имя не может быть пустым');
    if (nick.length > 25) return alert('Имя не может быть длиннее 25 символов');
    if (!/^#[0-9a-fA-F]{6}$/.test(color)) return alert('Некорректный цвет');

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        const r = await fetch('/api/update-profile', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                token: currentUser.token,
                username: nick,
                color
            }),
            signal: controller.signal,
            credentials: 'same-origin'
        });
        clearTimeout(timeoutId);

        if (r.ok) {
            currentUser.username = nick;
            currentUser.color = color;
            AppState.currentUser = currentUser;
        } else {
            const err = await r.json();
            alert(err.detail || 'Ошибка обновления профиля');
        }
    } catch (e) {
        if (e.name === 'AbortError') {
            alert('Превышено время ожидания');
        }
    }

    updateHeader();
    toggleModal('change-nickname-modal', false);
});

/**
 * Обработчик нажатия Enter в поле ввода имени
 * @param {KeyboardEvent} e - Событие клавиатуры
 */
$('new-nickname-input').addEventListener('keypress', e => {
    if (e.key === 'Enter') $('save-profile-btn').click();
});

/**
 * Устанавливает глобальный геттер/сеттер для currentUser
 */
Object.defineProperty(window, 'currentUser', {
    get: function() {
        return AppState.currentUser;
    },
    set: function(val) {
        AppState.currentUser = val;
    },
    configurable: false
});

/**
 * Устанавливает глобальный геттер/сеттер для guestNickname
 */
Object.defineProperty(window, 'guestNickname', {
    get: function() {
        return AppState.guestNickname;
    },
    set: function(val) {
        AppState.guestNickname = val;
    },
    configurable: false
});