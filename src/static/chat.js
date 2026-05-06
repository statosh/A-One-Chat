/**
 * Модуль для централизованного хранения состояния чата
 * @namespace ChatState
 */
const ChatState = {
    currentRoomId: null,
    ws: null,
    globalWs: null,
    reconnectTimer: null,
    reconnectAttempts: 0,
    lastUserList: [],
    isSending: false
};

const MAX_RECONNECT_ATTEMPTS = 3;
const RECONNECT_BASE_DELAY = 1000;
const RECONNECT_MAX_DELAY = 5000;
const SEND_DEBOUNCE_DELAY = 500;

let currentRoomId = null;
let ws = null;
let globalWs = null;
let reconnectTimer = null;
let reconnectAttempts = 0;
let replyTo = null;
let pendingFile = null;

/**
 * Синхронизирует глобальные переменные с состоянием ChatState
 * 
 * Входы: отсутствуют
 * Выходы: отсутствуют
 */
function syncChatState() {
    ChatState.currentRoomId = currentRoomId;
    ChatState.ws = ws;
    ChatState.globalWs = globalWs;
    ChatState.reconnectTimer = reconnectTimer;
    ChatState.reconnectAttempts = reconnectAttempts;
}

$('cancel-reply-btn').addEventListener('click', () => {
    replyTo = null;
    $('reply-block').style.display = 'none';
});

$('cancel-attachment-btn').addEventListener('click', () => {
    pendingFile = null;
    $('attachment-preview').style.display = 'none';
});

/**
 * Добавляет сообщение в контейнер сообщений
 * 
 * Входы:
 *     m {Object} - Объект сообщения с полями:
 *         - id {number} - ID сообщения
 *         - type {string} - Тип сообщения ('system', 'file' или обычное)
 *         - text {string} - Текст сообщения
 *         - author_id {number} - ID автора
 *         - author {string} - Имя автора
 *         - author_color {string} - Цвет автора
 *         - timestamp {string} - Временная метка
 *         - is_admin {boolean} - Флаг администратора
 *         - is_reply {boolean} - Флаг ответа
 *         - reply_msg_id {number} - ID исходного сообщения
 *         - reply_author {string} - Имя автора исходного сообщения
 *         - reply_text {string} - Текст исходного сообщения
 *         - reply_author_color {string} - Цвет автора исходного сообщения
 *         - file_type, file_url, original_name, caption (для файловых сообщений)
 * 
 * Выходы: отсутствует (добавляет DOM-элемент сообщения)
 */
function addMsg(m) {
    if (m.room_id && m.room_id !== currentRoomId) return;

    if (m.id) {
        const existing = document.querySelector(`.message[data-msg-id="${m.id}"]`);
        if (existing) return;
    }

    const div = document.createElement('div');
    if (m.id) {
        div.id = 'msg-' + m.id;
    }

    if (m.type === 'system') {
        div.className = 'system-message';
        div.textContent = m.text;
    } else if (m.type === 'file' || (m.text && m.text.startsWith('[FILE]'))) {
        let isMine = currentUser ? m.author_id === currentUser.id : m.author === guestNickname;

        let fileType, fileUrl, originalName, caption;

        if (m.file_type) {
            fileType = m.file_type;
            fileUrl = m.file_url;
            originalName = m.original_name;
            caption = m.caption || '';
        } else {
            const match = m.text.match(/\[FILE\](.+?)\|(.+?)\|(.+?)\[\/FILE\]/);
            if (!match) return;
            fileType = match[1];
            fileUrl = match[2];
            originalName = match[3];
            caption = '';
        }

        div.className = 'message file-message' + (isMine ? ' message-mine' : '');
        if (m.id) div.dataset.msgId = m.id;
        div.style.borderLeftColor = m.author_color || '#007bff';

        let fileContent = '';

        switch (fileType) {
            case 'image':
                fileContent = `<div class="file-media-wrapper"><img src="${fileUrl}" class="file-image" alt="${escapeHtml(originalName)}" onclick="window.open('${fileUrl}', '_blank')"><div class="file-media-name" title="${escapeHtml(originalName)}">${truncateFileName(originalName)}</div></div>`;
                break;
            case 'video':
                fileContent = `<div class="file-media-wrapper"><video controls class="file-video"><source src="${fileUrl}" type="video/mp4">Ваш браузер не поддерживает видео</video><div class="file-media-name" title="${escapeHtml(originalName)}">${truncateFileName(originalName)}</div></div>`;
                break;
            case 'audio':
                fileContent = `<div class="file-media-wrapper"><audio controls class="file-audio"><source src="${fileUrl}">Ваш браузер не поддерживает аудио</audio><div class="file-media-name" title="${escapeHtml(originalName)}">${truncateFileName(originalName)}</div></div>`;
                break;
            case 'document':
                fileContent = `<a href="${fileUrl}" download="${escapeHtml(originalName)}" class="file-document"><i class="fa-solid fa-file"></i><div><div>${truncateFileName(originalName)}</div><div class="file-name">Скачать файл</div></div></a>`;
                break;
        }

        let captionHTML = caption ? `<div class="file-caption">${escapeHtml(caption)}</div>` : '';

        const authorColor = m.author_color || '#007bff';
        const authorName = escapeHtml(m.author);
        const adminIcon = m.is_admin ? '<i class="fa-solid fa-shield-halved admin-shield" title="Администратор"></i>' : '';
        const msgTime = formatTime(m.timestamp);

        let replyHTML = buildReplyHTML(m);

        let menuHTML = buildMenuHTML();

        div.innerHTML = menuHTML + replyHTML + `<div class="msg-header"><span class="nickname" style="color:${authorColor}">${authorName}${adminIcon}</span><span class="msg-time">${msgTime}</span></div><div class="msg-body"><div>${fileContent}${captionHTML}</div></div>`;

        const replyBtn = div.querySelector('.reply-btn');
        if (replyBtn) replyBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            setReplyTo(m);
        });

        const deleteBtn = div.querySelector('.delete-btn');
        if (deleteBtn) deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteMessage(m.id);
        });
    } else {
        let isMine = currentUser ? m.author_id === currentUser.id : m.author === guestNickname;

        div.className = 'message' + (isMine ? ' message-mine' : '');
        if (m.id) div.dataset.msgId = m.id;
        div.style.borderLeftColor = m.author_color || '#007bff';

        const authorColor = m.author_color || '#007bff';
        const authorName = escapeHtml(m.author);
        const adminIcon = m.is_admin ? '<i class="fa-solid fa-shield-halved admin-shield" title="Администратор"></i>' : '';
        const msgTime = formatTime(m.timestamp);

        let replyHTML = buildReplyHTML(m);
        let menuHTML = buildMenuHTML();

        div.innerHTML = menuHTML + replyHTML + `<div class="msg-header"><span class="nickname" style="color:${authorColor}">${authorName}${adminIcon}</span><span class="msg-time">${msgTime}</span></div><div class="msg-body"><span class="message-text"></span></div>`;

        const textSpan = div.querySelector('.message-text');
        if (textSpan) textSpan.textContent = m.text;

        const replyBtn = div.querySelector('.reply-btn');
        if (replyBtn) replyBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            setReplyTo(m);
        });

        const deleteBtn = div.querySelector('.delete-btn');
        if (deleteBtn) deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteMessage(m.id);
        });
    }

    $('messages-container').appendChild(div);
    setTimeout(() => {
        $('messages-container').scrollTop = $('messages-container').scrollHeight;
    }, 250);
}

/**
 * Строит HTML для цитируемого сообщения (ответа)
 * 
 * Входы:
 *     m {Object} - Объект сообщения с полями is_reply, reply_author, reply_author_color, reply_text, reply_msg_id
 * 
 * Выходы:
 *     {string} HTML-строка цитаты или пустая строка
 */
function buildReplyHTML(m) {
    if (!m.is_reply || !m.reply_author) return '';

    const replyColor = m.reply_author_color || '#007bff';
    const replyText = m.reply_text && m.reply_text.startsWith('[FILE]') ? 'файл' : (m.reply_text || '');
    const truncated = replyText.length > 30 ? replyText.substring(0, 30) + '...' : replyText;
    const quotedMsgExists = m.reply_msg_id && document.getElementById('msg-' + m.reply_msg_id);

    if (quotedMsgExists || !m.reply_msg_id) {
        return `<a href="#msg-${m.reply_msg_id}" class="reply-quote"><i class="fa-solid fa-reply" style="color:${replyColor}"></i><span style="color:${replyColor};font-weight:bold;">${escapeHtml(m.reply_author)}</span>: ${escapeHtml(truncated)}</a>`;
    }
    return `<span class="reply-quote deleted"><i class="fa-solid fa-reply"></i><em>удалено</em></span>`;
}

/**
 * Строит HTML для меню сообщения (кнопки ответа и удаления)
 * 
 * Входы: отсутствуют (использует currentUser)
 * 
 * Выходы:
 *     {string} HTML-строка с кнопками меню
 */
function buildMenuHTML() {
    if (currentUser && currentUser.is_admin === 1) {
        return `<div class="message-menu"><button class="message-menu-btn reply-btn" title="Ответить"><i class="fa-solid fa-reply"></i></button><div class="message-menu-separator"></div><button class="message-menu-btn delete-btn" title="Удалить сообщение"><i class="fa-solid fa-trash"></i></button></div>`;
    }
    return `<div class="message-menu"><button class="message-menu-btn reply-btn" title="Ответить"><i class="fa-solid fa-reply"></i></button></div>`;
}

/**
 * Устанавливает сообщение для ответа
 * 
 * Входы:
 *     m {Object} - Объект сообщения с полями id, author, text, author_color
 * 
 * Выходы: отсутствует (обновляет replyTo и отображает блок ответа)
 */
function setReplyTo(m) {
    replyTo = {
        id: m.id,
        author: m.author,
        text: m.text,
        color: m.author_color
    };
    const replyText = m.text && m.text.startsWith('[FILE]') ? 'файл' : m.text;
    const truncated = replyText.length > 30 ? replyText.substring(0, 30) + '...' : replyText;
    $('reply-text').innerHTML = `Отвечает на <span style="color:${m.author_color};font-weight:bold;">${escapeHtml(m.author)}</span>: ${escapeHtml(truncated)}`;
    $('reply-block').style.display = 'flex';
    $('message-input').focus();
}

/**
 * Удаляет сообщение на сервере
 * 
 * Входы:
 *     id {number} - ID сообщения для удаления
 * 
 * Выходы: отсутствует
 */
async function deleteMessage(id) {
    if (!confirm('Удалить сообщение?')) return;
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);
        await fetch(`/api/messages/${id}`, {
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
        if (e.name !== 'AbortError') console.error('Ошибка удаления сообщения');
    }
}

/**
 * Отправляет сообщение или файл на сервер
 * 
 * Входы: отсутствуют (использует глобальные переменные currentRoomId, replyTo, pendingFile)
 * 
 * Выходы: отсутствует
 */
async function sendMessage() {
    if (ChatState.isSending) return;
    const text = $('message-input').value.trim();
    if (!text && !pendingFile) return;
    if (!currentRoomId) return;
    if (text.length > 3000) return alert('Сообщение слишком длинное (максимум 3000 символов)');

    ChatState.isSending = true;

    try {
        if (pendingFile) {
            const msgBody = {
                token: currentUser ? currentUser.token : sessionStorage.getItem('guest_token'),
                room_id: currentRoomId,
                file_url: pendingFile.url,
                file_type: pendingFile.type,
                original_name: pendingFile.name,
                caption: text || ''
            };
            if (replyTo) {
                msgBody.reply_msg_id = replyTo.id;
                msgBody.reply_author = replyTo.author;
                msgBody.reply_text = replyTo.text;
                msgBody.reply_author_color = replyTo.color;
            }
            const msgR = await fetch('/api/messages/file', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(msgBody)
            });
            if (msgR.ok) {
                resetInput();
                pendingFile = null;
                $('attachment-preview').style.display = 'none';
                replyTo = null;
                $('reply-block').style.display = 'none';
            } else {
                const err = await msgR.json();
                alert(err.detail || 'Ошибка отправки');
            }
        } else {
            const body = {
                text,
                room_id: currentRoomId
            };
            if (currentUser) body.token = currentUser.token;
            else {
                body.token = sessionStorage.getItem('guest_token') || '';
                body.author = guestNickname;
                body.author_color = guestColor;
            }
            if (replyTo) {
                body.reply_msg_id = replyTo.id;
                body.reply_author = replyTo.author;
                body.reply_text = replyTo.text;
                body.reply_author_color = replyTo.color;
            }
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000);
            const r = await fetch('/api/messages', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(body),
                signal: controller.signal,
                credentials: 'same-origin'
            });
            clearTimeout(timeoutId);
            if (r.ok) {
                resetInput();
                replyTo = null;
                $('reply-block').style.display = 'none';
            } else {
                const err = await r.json();
                alert(err.detail || 'Ошибка отправки');
            }
        }
    } catch (e) {
        if (e.name === 'AbortError') alert('Превышено время ожидания');
    } finally {
        setTimeout(() => {
            ChatState.isSending = false;
        }, SEND_DEBOUNCE_DELAY);
    }
}

/**
 * Сбрасывает поле ввода сообщения и счетчик символов
 * 
 * Входы: отсутствуют
 * Выходы: отсутствует
 */
function resetInput() {
    $('message-input').value = '';
    $('char-counter').textContent = '0 / 3000';
    $('char-counter').style.color = '#999';
    $('send-button').style.opacity = '1';
    $('send-button').style.pointerEvents = 'auto';
    $('message-input').focus();
}

/**
 * Выбирает комнату с проверкой пароля
 * 
 * Входы:
 *     rid {number} - ID комнаты
 *     rname {string} - Название комнаты
 *     rcolor {string} - Цвет комнаты
 * 
 * Выходы: отсутствует
 */
function selectRoom(rid, rname, rcolor) {
    if (currentRoomId === rid) return;
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
    reconnectAttempts = 0;
    syncChatState();
    const room = allRooms.find(r => r.id === rid);
    if (room && room.has_password && !(currentUser && (room.creator_id === currentUser.id || currentUser.is_admin === 1))) {
        pendingRoomId = rid;
        syncRoomsState();
        $('room-password-input').value = '';
        toggleModal('room-password-modal', true);
        $('room-password-input').focus();
        return;
    }
    highlightRoom(rid, room?.color || rcolor);
    doSelectRoom(rid, rname, rcolor);
}

/**
 * Выполняет выбор комнаты (подключение, загрузка сообщений)
 * 
 * Входы:
 *     rid {number} - ID комнаты
 *     rname {string} - Название комнаты
 *     rcolor {string} - Цвет комнаты
 * 
 * Выходы: отсутствует
 */
function doSelectRoom(rid, rname, rcolor) {
    if (currentRoomId === rid) return;
    closeWebSocket();
    currentRoomId = rid;
    syncChatState();
    if (window.location.hash) history.replaceState(null, '', window.location.pathname + window.location.search);
    $('current-room-title').textContent = rname;
    $('current-room-title').style.color = rcolor;
    $('room-header').style.display = 'flex';
    $('room-header-hr').style.display = 'block';
    $('input-block').style.display = 'flex';
    $('input-block-hr').style.display = 'block';
    $('messages-container').classList.remove('empty-state');
    $('messages-container').innerHTML = '<div style="text-align:center;color:#999;padding:20px;">Загрузка сообщений...</div>';
    const room = allRooms.find(r => r.id === rid);
    const canEdit = room && currentUser && (room.creator_id === currentUser.id || currentUser.is_admin === 1);
    $('edit-room-btn').style.display = canEdit ? 'inline-block' : 'none';
    $('users-btn').style.display = 'inline-block';
    updateRoomCreatorInfo(room);
    replyTo = null;
    $('reply-block').style.display = 'none';
    pendingFile = null;
    $('attachment-preview').style.display = 'none';
    fetch(`/api/rooms/${rid}/messages?limit=250`)
        .then(r => {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        })
        .then(msgs => {
            if (currentRoomId === rid) {
                $('messages-container').innerHTML = '';
                if (!msgs || msgs.length === 0) $('messages-container').innerHTML = '<div style="text-align:center;color:#999;padding:20px;">Нет сообщений</div>';
                else msgs.forEach(m => addMsg(m));
                setTimeout(() => {
                    $('messages-container').scrollTop = $('messages-container').scrollHeight;
                }, 100);
                connectWs(rid);
            }
        })
        .catch(() => {
            if (currentRoomId === rid) {
                $('messages-container').innerHTML = '<div style="text-align:center;color:#999;padding:20px;">Ошибка загрузки сообщений</div>';
                connectWs(rid);
            }
        });
}

/**
 * Закрывает WebSocket соединение
 * 
 * Входы: отсутствуют
 * Выходы: отсутствует
 */
function closeWebSocket() {
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
    if (ws) {
        ws.onclose = null;
        ws.onerror = null;
        ws.onmessage = null;
        ws.close();
        ws = null;
    }
    syncChatState();
}

/**
 * Выходит из текущей комнаты
 * 
 * Входы: отсутствуют
 * Выходы: отсутствует
 */
function leaveRoom() {
    closeWebSocket();
    reconnectAttempts = 0;
    currentRoomId = null;
    syncChatState();
    if (window.location.hash) history.replaceState(null, '', window.location.pathname + window.location.search);
    document.querySelectorAll('.room').forEach(r => {
        r.classList.remove('active');
        r.style.borderColor = '';
    });
    $('room-header').style.display = 'none';
    $('room-header-hr').style.display = 'none';
    $('input-block').style.display = 'none';
    $('input-block-hr').style.display = 'none';
    $('edit-room-btn').style.display = 'none';
    $('users-btn').style.display = 'none';
    $('room-creator-info').textContent = '';
    $('messages-container').classList.add('empty-state');
    $('messages-container').innerHTML = '<p>Выберите или создайте комнату чтобы начать общение</p>';
    replyTo = null;
    $('reply-block').style.display = 'none';
    pendingFile = null;
    $('attachment-preview').style.display = 'none';
}

$('leave-room-btn').addEventListener('click', leaveRoom);
$('send-button').addEventListener('click', sendMessage);
$('message-input').addEventListener('keypress', e => {
    if (e.key === 'Enter') {
        e.preventDefault();
        sendMessage();
    }
});
$('message-input').addEventListener('input', () => {
    const len = $('message-input').value.length;
    $('char-counter').textContent = len + ' / 3000';
    $('char-counter').style.color = len > 3000 ? '#dc3545' : '#999';
    $('send-button').style.opacity = len > 3000 ? '0.5' : '1';
    $('send-button').style.pointerEvents = len > 3000 ? 'none' : 'auto';
});

/**
 * Загружает и отправляет файл на сервер
 * 
 * Входы:
 *     file {File} - Файл для загрузки
 * 
 * Выходы: отсутствует
 */
async function uploadAndSendFile(file) {
    if (!currentRoomId) return alert('Выберите комнату для отправки файла');
    if (pendingFile) return alert('Нельзя загрузить больше одного файла');
    const allowedExtensions = ['png', 'jpg', 'jpeg', 'gif', 'mp4', 'ogg', 'wav', 'mp3', 'flac', 'txt', 'doc', 'docx', 'md'];
    const extension = file.name.split('.').pop().toLowerCase();
    if (!allowedExtensions.includes(extension)) return alert('Недопустимый формат файла');
    if (file.size > 50 * 1024 * 1024) return alert('Файл слишком большой (максимум 50MB)');
    try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('token', currentUser ? currentUser.token : sessionStorage.getItem('guest_token'));
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 120000);
        const r = await fetch('/api/upload', {
            method: 'POST',
            body: formData,
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        if (r.ok) {
            const fileData = await r.json();
            pendingFile = {
                file,
                url: fileData.url,
                type: fileData.type,
                name: fileData.original_name
            };
            const previewHTML = fileData.type === 'image' ? `<img src="${fileData.url}" alt="${escapeHtml(fileData.original_name)}">` : '<i class="fa-solid fa-paperclip"></i>';
            const fullName = fileData.original_name;
            const dotIndex = fullName.lastIndexOf('.');
            let displayName;
            if (dotIndex > 0) {
                const name = fullName.substring(0, dotIndex);
                const ext = fullName.substring(dotIndex);
                displayName = fullName.length > 30 ? name.substring(0, 27 - ext.length) + '...' + ext : fullName;
            } else {
                displayName = fullName.length > 30 ? fullName.substring(0, 27) + '...' : fullName;
            }
            $('attachment-preview').innerHTML = `<div class="attachment-info">${previewHTML}<span title="${escapeHtml(fileData.original_name)}">${escapeHtml(displayName)}</span></div><button id="cancel-attachment-btn" class="cancel-attachment-btn" title="Убрать вложение">&times;</button>`;
            $('attachment-preview').style.display = 'flex';
            document.getElementById('cancel-attachment-btn').addEventListener('click', () => {
                pendingFile = null;
                $('attachment-preview').style.display = 'none';
            });
            $('message-input').focus();
        } else {
            const err = await r.json();
            alert(err.detail || 'Ошибка загрузки файла');
        }
    } catch (e) {
        alert(e.name === 'AbortError' ? 'Превышено время загрузки' : 'Ошибка загрузки файла');
    }
}

$('file-upload-btn').addEventListener('click', () => $('file-input').click());
$('file-input').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    await uploadAndSendFile(file);
    $('file-input').value = '';
});

const rightPanel = document.querySelector('.right');
const dropOverlay = document.createElement('div');
dropOverlay.className = 'drop-overlay';
dropOverlay.innerHTML = '<i class="fa-solid fa-cloud-upload"></i> Отпустите файл для отправки';
rightPanel.appendChild(dropOverlay);

let dragCounter = 0;
document.addEventListener('dragenter', (e) => {
    e.preventDefault();
    dragCounter++;
    if (currentRoomId) dropOverlay.classList.add('active');
});
document.addEventListener('dragleave', (e) => {
    e.preventDefault();
    dragCounter--;
    if (dragCounter === 0) dropOverlay.classList.remove('active');
});
document.addEventListener('dragover', (e) => e.preventDefault());
document.addEventListener('drop', async (e) => {
    e.preventDefault();
    dragCounter = 0;
    dropOverlay.classList.remove('active');
    if (e.dataTransfer.files.length > 0) await uploadAndSendFile(e.dataTransfer.files[0]);
});

let lastUserList = [];
$('users-btn').addEventListener('click', async () => {
    if (!currentRoomId) return;
    renderUsersModal(lastUserList);
    toggleModal('users-modal', true);
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        const r = await fetch(`/api/room/${currentRoomId}/users`, {
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        updateUsersModal(await r.json());
    } catch (e) {}
});
$('close-users-modal').addEventListener('click', () => toggleModal('users-modal', false));

/**
 * Обновляет модальное окно списка пользователей
 * 
 * Входы:
 *     users {Array} - Массив объектов пользователей с полями username, color, is_admin
 * 
 * Выходы: отсутствует
 */
function updateUsersModal(users) {
    lastUserList = users;
    if ($('users-modal').style.display === 'block') renderUsersModal(users);
}

/**
 * Отображает список пользователей в модальном окне
 * 
 * Входы:
 *     users {Array} - Массив объектов пользователей с полями username, color, is_admin
 * 
 * Выходы: отсутствует
 */
function renderUsersModal(users) {
    $('users-list').innerHTML = users.map(u => `<div class="user-item" style="display:flex;align-items:center;gap:8px;padding:8px 0;"><span style="width:10px;height:10px;border-radius:50%;background:${u.color};flex-shrink:0;"></span><span>${escapeHtml(u.username)}</span>${u.is_admin ? '<i class="fa-solid fa-shield-halved admin-shield" title="Администратор"></i>' : ''}</div>`).join('');
}