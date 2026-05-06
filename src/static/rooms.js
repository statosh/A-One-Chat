/**
 * Модуль для централизованного хранения состояния комнат
 * @namespace RoomsState
 */
const RoomsState = {
    allRooms: [],
    pendingRoomId: null,
    userCountsCache: null
};

let allRooms = [],
    pendingRoomId = null;

let searchMode = 'name';
let searchQuery = '';

/**
 * Синхронизирует глобальные переменные с состоянием RoomsState
 * 
 * Входы: отсутствуют
 * Выходы: отсутствуют
 */
function syncRoomsState() {
    RoomsState.allRooms = allRooms;
    RoomsState.pendingRoomId = pendingRoomId;
}

$('create-room-button').addEventListener('click', () => {
    if (!currentUser) return alert('Только зарегистрированные пользователи могут создавать комнаты');
    const myRooms = allRooms.filter(r => r.creator_id === currentUser.id);
    if (currentUser.is_admin !== 1 && myRooms.length >= 3) return alert('Нельзя создать больше 3 комнат');

    $('new-room-name-input').value = '';
    $('new-room-password-input').value = '';
    initColorPicker('room-color-picker', '#007bff');
    toggleModal('create-room-modal', true);
    $('new-room-name-input').focus();
});

$('close-create-room-modal').addEventListener('click', () => toggleModal('create-room-modal', false));
$('cancel-create-room').addEventListener('click', () => toggleModal('create-room-modal', false));

$('create-room-btn').addEventListener('click', async () => {
    const n = sanitizeUserInput($('new-room-name-input').value.trim());
    if (!n) return alert('Введите название');
    if (n.length > 25) return alert('Название не может быть длиннее 25 символов');
    await createRoom(n, getColor('room-color-picker'), $('new-room-password-input').value);
});

$('new-room-name-input').addEventListener('keypress', async e => {
    if (e.key === 'Enter') {
        const n = sanitizeUserInput(e.target.value.trim());
        if (!n) return;
        if (n.length > 25) return alert('Название не может быть длиннее 25 символов');
        await createRoom(n, getColor('room-color-picker'), $('new-room-password-input').value);
    }
});

$('edit-room-btn').addEventListener('click', function() {
    const room = allRooms.find(r => r.id === currentRoomId);
    if (!room) return;

    $('edit-room-name-input').value = room.name;
    $('edit-room-password-input').value = '';
    initColorPicker('edit-room-color-picker', room.color);

    const canDelete = (currentUser && room.creator_id === currentUser.id) || (currentUser && currentUser.is_admin === 1);
    $('delete-room-btn-modal').style.display = canDelete ? 'block' : 'none';

    toggleModal('edit-room-modal', true);
});

$('delete-room-btn-modal').addEventListener('click', async () => {
    if (!confirm('Удалить комнату?')) return;
    await deleteRoom(currentRoomId);
    toggleModal('edit-room-modal', false);
    leaveRoom();
});

$('close-edit-room-modal').addEventListener('click', () => toggleModal('edit-room-modal', false));

$('save-room-btn').addEventListener('click', async () => {
    const n = sanitizeUserInput($('edit-room-name-input').value.trim());
    if (!n) return alert('Введите название');
    if (n.length > 25) return alert('Название не может быть длиннее 25 символов');

    const color = getColor('edit-room-color-picker');
    const password = $('edit-room-password-input').value;

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        const r = await fetch(`/api/rooms/${currentRoomId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: n,
                color,
                password,
                token: currentUser.token
            }),
            signal: controller.signal
        });
        clearTimeout(timeoutId);

        if (r.ok) {
            toggleModal('edit-room-modal', false);
            const updated = await r.json();
            const idx = allRooms.findIndex(x => x.id === currentRoomId);
            if (idx >= 0) {
                allRooms[idx] = updated;
                syncRoomsState();
            }
            updateRoomInDOM(updated);
            $('current-room-title').textContent = updated.name;
            $('current-room-title').style.color = updated.color;
            highlightRoom(currentRoomId, updated.color);
            updateRoomCreatorInfo(updated);
        } else {
            const err = await r.json();
            alert(err.detail || 'Ошибка обновления комнаты');
        }
    } catch (e) {
        if (e.name === 'AbortError') {
            alert('Превышено время ожидания');
        } else {
            alert('Ошибка сети');
        }
    }
});

$('close-password-modal').addEventListener('click', () => {
    pendingRoomId = null;
    syncRoomsState();
    toggleModal('room-password-modal', false);
});

$('submit-password-btn').addEventListener('click', async () => {
    const pwd = $('room-password-input').value;
    if (!pwd) return;

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        const r = await fetch(`/api/room/${pendingRoomId}/check-password`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                password: pwd,
                token: currentUser ? currentUser.token : ''
            }),
            signal: controller.signal
        });
        clearTimeout(timeoutId);

        if (r.ok) {
            const data = await r.json();
            if (data.valid) {
                toggleModal('room-password-modal', false);
                const room = allRooms.find(r => r.id === pendingRoomId);
                highlightRoom(pendingRoomId, room?.color);
                doSelectRoom(pendingRoomId, room.name, room.color);
            } else {
                alert('Неверный пароль');
            }
        }
    } catch (e) {
        if (e.name === 'AbortError') {
            alert('Превышено время ожидания');
        } else {
            alert('Ошибка сети');
        }
    }
});

$('room-password-input').addEventListener('keypress', e => {
    if (e.key === 'Enter') $('submit-password-btn').click();
});

$('search-mode-btn').addEventListener('click', () => {
    searchMode = searchMode === 'name' ? 'author' : 'name';

    const icon = $('search-mode-btn').querySelector('i');
    if (searchMode === 'name') {
        icon.className = 'fa-solid fa-font';
        $('search-mode-btn').title = 'Поиск по названию';
        $('search-input').placeholder = 'Поиск комнат...';
    } else {
        icon.className = 'fa-solid fa-user';
        $('search-mode-btn').title = 'Поиск по автору';
        $('search-input').placeholder = 'Поиск по автору...';
    }

    if (searchQuery) {
        filterRooms(searchQuery);
    }
});

$('search-input').addEventListener('input', (e) => {
    searchQuery = e.target.value.trim().toLowerCase();
    filterRooms(searchQuery);
});

/**
 * Фильтрует и отображает комнаты по поисковому запросу
 * 
 * Входы:
 *     query {string} - Поисковый запрос (в нижнем регистре)
 * 
 * Выходы: отсутствует (обновляет DOM)
 */
async function filterRooms(query) {
    const list = $('rooms-list');

    if (!query) {
        rebuildRoomSections();
        return;
    }

    let filtered;

    if (searchMode === 'name') {
        filtered = allRooms.filter(r => r.name.toLowerCase().includes(query));
    } else {
        const creators = {};
        for (const r of allRooms) {
            if (r.creator_id && !creators[r.creator_id]) {
                const name = await fetchCreatorName(r.creator_id);
                creators[r.creator_id] = name.toLowerCase();
            }
        }
        filtered = allRooms.filter(r => {
            const creatorName = creators[r.creator_id] || '';
            return creatorName.includes(query);
        });
    }

    list.innerHTML = '';

    if (filtered.length === 0) {
        list.innerHTML = '<div style="text-align:center;color:#999;padding:20px;">Ничего не найдено</div>';
        return;
    }

    if (currentUser) {
        const myRooms = filtered.filter(r => r.creator_id === currentUser.id);
        const otherRooms = filtered.filter(r => r.creator_id !== currentUser.id);

        if (myRooms.length > 0) {
            const h = document.createElement('div');
            h.className = 'room-section-header';
            h.textContent = 'Ваши комнаты';
            list.appendChild(h);
            for (const r of myRooms) list.appendChild(await createRoomElement(r));
        }

        if (otherRooms.length > 0) {
            const h = document.createElement('div');
            h.className = 'room-section-header';
            h.textContent = myRooms.length > 0 ? 'Остальные комнаты' : '';
            if (h.textContent) list.appendChild(h);
            for (const r of otherRooms) list.appendChild(await createRoomElement(r));
        }
    } else {
        for (const r of filtered) list.appendChild(await createRoomElement(r));
    }

    if (currentRoomId) {
        const room = allRooms.find(r => r.id === currentRoomId);
        highlightRoom(currentRoomId, room?.color);
    }

    if (RoomsState.userCountsCache) {
        updateUserCounts(RoomsState.userCountsCache);
    } else {
        fetch('/api/user-counts')
            .then(r => r.json())
            .then(d => {
                RoomsState.userCountsCache = d.counts;
                updateUserCounts(d.counts);
            })
            .catch(() => {});
    }
}

/**
 * Создает новую комнату на сервере
 * 
 * Входы:
 *     name {string} - Название комнаты
 *     color {string} - Цвет комнаты в формате HEX
 *     password {string} - Пароль комнаты
 * 
 * Выходы: отсутствует (закрывает модальное окно при успехе)
 */
async function createRoom(name, color, password) {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        const r = await fetch('/api/rooms', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name,
                color,
                password,
                token: currentUser.token
            }),
            signal: controller.signal
        });
        clearTimeout(timeoutId);

        if (r.ok) {
            toggleModal('create-room-modal', false);
        } else {
            const err = await r.json();
            alert(err.detail || 'Ошибка создания комнаты');
        }
    } catch (e) {
        if (e.name === 'AbortError') {
            alert('Превышено время ожидания');
        } else {
            alert('Ошибка сети');
        }
    }
}

/**
 * Удаляет комнату с сервера
 * 
 * Входы:
 *     id {number} - ID комнаты для удаления
 * 
 * Выходы: отсутствует
 */
async function deleteRoom(id) {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        await fetch(`/api/rooms/${id}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                token: currentUser.token
            }),
            signal: controller.signal
        });
        clearTimeout(timeoutId);
    } catch (e) {
        if (e.name !== 'AbortError') {
            alert('Ошибка сети');
        }
    }
}

/**
 * Подсвечивает выбранную комнату в списке
 * 
 * Входы:
 *     roomId {number} - ID комнаты для подсветки
 *     color {string} - Цвет рамки подсветки
 * 
 * Выходы: отсутствует (изменяет CSS классы элементов)
 */
function highlightRoom(roomId, color) {
    document.querySelectorAll('.room').forEach(r => {
        r.classList.remove('active');
        r.style.borderColor = '';
    });
    const el = document.querySelector(`.room[data-room-id="${roomId}"]`);
    if (el) {
        el.classList.add('active');
        if (color) el.style.borderColor = color;
    }
}

/**
 * Обновляет отображение комнаты в DOM после изменений
 * 
 * Входы:
 *     room {Object} - Обновленный объект комнаты
 * 
 * Выходы: отсутствует (обновляет DOM-элементы)
 */
function updateRoomInDOM(room) {
    const el = document.querySelector(`.room[data-room-id="${room.id}"]`);
    if (!el) return;

    el.dataset.roomName = escapeHtml(room.name);
    el.dataset.roomColor = room.color;
    el.title = room.name;

    const colorDot = el.querySelector('.room-color-dot');
    if (colorDot) colorDot.style.backgroundColor = room.color;

    const title = el.querySelector('.room-title');
    if (title) title.textContent = room.name;

    let sub = el.querySelector('.room-subtitle');
    if (room.has_password) {
        if (!sub) {
            sub = document.createElement('div');
            sub.className = 'room-subtitle';
            const container = el.querySelector('div');
            if (container) container.appendChild(sub);
        }
        sub.innerHTML = '<i>*с паролем*</i>';
    } else if (sub) {
        sub.remove();
    }

    if (parseInt(el.dataset.roomId) === currentRoomId) {
        el.style.borderColor = room.color;
    }
}

/**
 * Создает DOM-элемент комнаты
 * 
 * Входы:
 *     room {Object} - Объект комнаты с полями id, name, color, has_password
 * 
 * Выходы:
 *     {Promise<HTMLElement>} DOM-элемент комнаты
 */
async function createRoomElement(room) {
    const div = document.createElement('div');
    div.className = 'room';
    div.dataset.roomId = room.id;
    div.dataset.roomName = escapeHtml(room.name);
    div.dataset.roomColor = room.color;
    div.dataset.creatorId = room.creator_id || '';
    div.title = room.name;

    let sub = '';
    if (room.has_password) sub = '<div class="room-subtitle"><i>*с паролем*</i></div>';

    div.innerHTML = `<span class="room-color-dot" style="background-color:${room.color}"></span><div style="flex:1;min-width:0;"><h3 class="room-title">${escapeHtml(room.name)}</h3>${sub}</div><span class="user-count" style="display:none;">0</span>`;

    div.addEventListener('click', function() {
        const roomId = parseInt(this.dataset.roomId);
        const roomName = this.dataset.roomName;
        const roomColor = this.dataset.roomColor;
        selectRoom(roomId, roomName, roomColor);
    });

    return div;
}

/**
 * Перестраивает список комнат в DOM
 * 
 * Входы:
 *     newRooms {Array|null} - Новые комнаты для добавления (опционально)
 *     append {boolean} - Флаг добавления вместо полной замены
 * 
 * Выходы: отсутствует (полностью перестраивает список комнат)
 */
async function rebuildRoomSections(newRooms, append) {
    const list = $('rooms-list');

    if (append && newRooms) {
        for (const r of newRooms) {
            if (!allRooms.find(x => x.id === r.id)) {
                allRooms.push(r);
                syncRoomsState();
            }
        }
    }

    list.innerHTML = '';

    if (allRooms.length === 0) {
        list.innerHTML = '<div style="text-align:center;color:#999;padding:20px;">Нет доступных комнат</div>';
        return;
    }

    if (currentUser) {
        const myRooms = allRooms.filter(r => r.creator_id === currentUser.id);
        const otherRooms = allRooms.filter(r => r.creator_id !== currentUser.id);

        if (myRooms.length > 0) {
            const h = document.createElement('div');
            h.className = 'room-section-header';
            h.textContent = 'Ваши комнаты';
            list.appendChild(h);
            for (const r of myRooms) {
                list.appendChild(await createRoomElement(r));
            }
        }

        if (otherRooms.length > 0) {
            const h = document.createElement('div');
            h.className = 'room-section-header';
            h.textContent = myRooms.length > 0 ? 'Остальные комнаты' : '';
            if (h.textContent) list.appendChild(h);
            for (const r of otherRooms) {
                list.appendChild(await createRoomElement(r));
            }
        }
    } else {
        for (const r of allRooms) {
            list.appendChild(await createRoomElement(r));
        }
    }

    if (currentRoomId) {
        const room = allRooms.find(r => r.id === currentRoomId);
        if (room) {
            highlightRoom(currentRoomId, room.color);
        }
    }

    fetch('/api/user-counts')
        .then(r => r.json())
        .then(d => {
            RoomsState.userCountsCache = d.counts;
            updateUserCounts(d.counts);
        })
        .catch(() => {});
}

/**
 * Загружает список комнат с сервера
 * 
 * Входы: отсутствуют
 * Выходы: отсутствует (обновляет глобальный массив allRooms и перестраивает список)
 */
async function loadRooms() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        const rooms = await fetch('/api/rooms', {
            signal: controller.signal
        }).then(r => r.json());
        clearTimeout(timeoutId);

        allRooms = rooms;
        syncRoomsState();
        rebuildRoomSections();
    } catch (e) {
        if (e.name !== 'AbortError') {
            console.error('Ошибка загрузки комнат');
        }
    }
}

/**
 * Обновляет счетчики пользователей в комнатах
 * 
 * Входы:
 *     counts {Object} - Объект вида {roomId: userCount}
 * 
 * Выходы: отсутствует (обновляет бейджи с количеством пользователей)
 */
function updateUserCounts(counts) {
    document.querySelectorAll('.room').forEach(el => {
        const rid = parseInt(el.dataset.roomId);
        const count = counts[rid] || 0;
        let badge = el.querySelector('.user-count');
        if (!badge) {
            badge = document.createElement('span');
            badge.className = 'user-count';
            el.appendChild(badge);
        }
        badge.textContent = count;
        badge.style.display = count > 0 ? 'inline' : 'none';
    });
}

/**
 * Обновляет отображение информации о создателе комнаты
 * 
 * Входы:
 *     room {Object|null} - Объект комнаты или null
 * 
 * Выходы: отсутствует (обновляет элемент с информацией)
 */
function updateRoomCreatorInfo(room) {
    const info = $('room-creator-info');
    if (!room) {
        info.textContent = '';
        return;
    }
    fetchCreatorName(room.creator_id).then(name => {
        info.textContent = 'Создал: ' + name;
    });
}