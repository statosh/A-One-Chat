/**
 * Устанавливает WebSocket соединение с указанной комнатой
 * 
 * Входы:
 *     rid {number} - ID комнаты для подключения
 * 
 * Выходы: отсутствует (создает WebSocket соединение и настраивает обработчики)
 */
function connectWs(rid) {
    if (ws && ws.roomId === rid && ws.readyState === WebSocket.OPEN) return;

    if (ws) {
        ws.onclose = null;
        ws.onerror = null;
        ws.onmessage = null;
        try {
            if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) ws.close(1000, 'Переподключение');
        } catch (e) {}
        ws = null;
    }

    if (currentRoomId !== rid) return;

    const p = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const token = currentUser ? currentUser.token : (sessionStorage.getItem('guest_token') || '');
    const username = currentUser ? currentUser.username : guestNickname;
    const color = currentUser ? currentUser.color : guestColor;

    try {
        ws = new WebSocket(`${p}//${location.host}/ws/${rid}?token=${encodeURIComponent(token)}&username=${encodeURIComponent(username)}&color=${encodeURIComponent(color)}`);
    } catch (e) {
        ws = null;
        setTimeout(() => {
            if (currentRoomId === rid) connectWs(rid);
        }, 2000);
        return;
    }

    ws.roomId = rid;

    ws.onopen = () => {
        reconnectAttempts = 0;
        syncChatState();
    };

    ws.onmessage = e => {
        try {
            const d = JSON.parse(e.data);

            if (d.type === 'new_message') addMsg(d.message);
            if (d.type === 'system') addMsg(d);
            if (d.type === 'delete_message') {
                const el = document.querySelector(`.message[data-msg-id="${d.message_id}"]`);
                if (el) el.remove();
                document.querySelectorAll(`a.reply-quote[href="#msg-${d.message_id}"]`).forEach(quote => {
                    quote.outerHTML = `<span class="reply-quote deleted"><i class="fa-solid fa-reply"></i><em>удалено</em></span>`;
                });
            }
            if (d.type === 'user_list') updateUsersModal(d.users);
            if (d.type === 'room_updated') {
                const updatedRoom = d.room;
                const idx = allRooms.findIndex(r => r.id === updatedRoom.id);
                if (idx >= 0) {
                    allRooms[idx] = updatedRoom;
                    syncRoomsState();
                }
                updateRoomInDOM(updatedRoom);
                if (currentRoomId === updatedRoom.id) {
                    $('current-room-title').textContent = updatedRoom.name;
                    $('current-room-title').style.color = updatedRoom.color;
                    highlightRoom(currentRoomId, updatedRoom.color);
                    updateRoomCreatorInfo(updatedRoom);
                }
            }
        } catch (ex) {}
    };

    ws.onclose = (event) => {
        if (currentRoomId !== rid) return;
        if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS && event.code !== 1000) {
            reconnectAttempts++;
            const delay = Math.min(RECONNECT_BASE_DELAY * reconnectAttempts, RECONNECT_MAX_DELAY);
            addSystemMessage(`⚠️ Соединение потеряно. Переподключение через ${Math.round(delay / 1000)}с...`);
            reconnectTimer = setTimeout(() => {
                if (currentRoomId === rid) connectWs(rid);
            }, delay);
            syncChatState();
        } else if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
            addSystemMessage('❌ Не удалось переподключиться.');
        }
        if (event.code === 4003) addSystemMessage('🔒 Нет доступа к комнате');
    };

    ws.onerror = () => {};
    syncChatState();
}

/**
 * Добавляет системное сообщение в текущую комнату
 * 
 * Входы:
 *     text {string} - Текст системного сообщения
 * 
 * Выходы: отсутствует
 */
function addSystemMessage(text) {
    addMsg({
        type: 'system',
        text,
        room_id: currentRoomId,
        timestamp: new Date().toISOString()
    });
}

/**
 * Устанавливает глобальное WebSocket соединение для получения обновлений о комнатах
 * 
 * Входы: отсутствуют
 * Выходы: отсутствует (создает глобальное WebSocket соединение)
 */
function connectGlobalWs() {
    if (globalWs) {
        globalWs.onclose = null;
        globalWs.onerror = null;
        try {
            globalWs.close();
        } catch (e) {}
        globalWs = null;
    }

    const p = location.protocol === 'https:' ? 'wss:' : 'ws:';
    try {
        globalWs = new WebSocket(`${p}//${location.host}/ws/global`);
    } catch (e) {
        return;
    }

    globalWs.onmessage = e => {
        try {
            const d = JSON.parse(e.data);

            if (d.type === 'new_room') {
                if (!allRooms.find(r => r.id === d.room.id)) {
                    allRooms.push(d.room);
                    syncRoomsState();
                    rebuildRoomSections();
                }
            }
            if (d.type === 'update_room') {
                const idx = allRooms.findIndex(r => r.id === d.room.id);
                if (idx >= 0) allRooms[idx] = d.room;
                else allRooms.push(d.room);
                syncRoomsState();
                rebuildRoomSections();
                if (currentRoomId === d.room.id) {
                    $('current-room-title').textContent = d.room.name;
                    $('current-room-title').style.color = d.room.color;
                    updateRoomCreatorInfo(d.room);
                }
            }
            if (d.type === 'delete_room') {
                allRooms = allRooms.filter(r => r.id !== d.room_id);
                syncRoomsState();
                rebuildRoomSections();
                if (currentRoomId === d.room_id) {
                    addSystemMessage('Комната была удалена');
                    leaveRoom();
                }
            }
            if (d.type === 'user_counts') {
                RoomsState.userCountsCache = d.counts;
                updateUserCounts(d.counts);
            }
        } catch (ex) {}
    };

    globalWs.onclose = () => setTimeout(connectGlobalWs, 3000);
    syncChatState();
}