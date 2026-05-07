from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.responses import HTMLResponse
import html
import re
import secrets
import time
import json
import os
import sqlite3
import logging
import magic
from datetime import datetime
from typing import List, Dict, Optional
from connection_manager import ConnectionManager

from config import (
    app, BASE_DIR, MAX_ROOM_NAME_LENGTH, MAX_MESSAGE_LENGTH,
    MAX_PASSWORD_LENGTH, RATE_LIMIT_MAX_MESSAGES, RATE_LIMIT_WINDOW,
    RATE_LIMIT_MIN_INTERVAL, MAX_ROOMS_PER_USER, UPLOAD_DIR,
    ALLOWED_EXTENSIONS, ALLOWED_MIMETYPES, MAX_FILE_SIZE,
    EXTENSION_MIME_MAP
)

from database import (
    init_db, get_db, generate_token, save_token, verify_token,
    log_auth_attempt, log_suspicious_activity
)

from models import (
    MessageCreate, MessageResponse, RoomResponse, RoomCreate, RoomUpdate,
    UserRegister, UserLogin, UserResponse, RoomDelete, TokenVerify,
    UpdateProfile, MessageDelete, PasswordCheck, MAX_USERNAME_LENGTH
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

manager = ConnectionManager()
message_timestamps: Dict[str, List[float]] = {}
password_attempts: Dict[str, List[float]] = {}
guest_tokens: Dict[str, dict] = {}

AVAILABLE_COLORS = ['#007bff', '#28a745', '#dc3545',
                    '#ffc107', '#17a2b8', '#6f42c1', '#fd7e14', '#20c997']

def get_room_for_access(room_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, password, creator_id FROM Room WHERE id=?', (room_id,))
    room = c.fetchone()
    conn.close()
    return dict(room) if room else None


def can_access_room(token: str, room_id: int, user: dict | None, guest: dict | None) -> bool:
    room = get_room_for_access(room_id)

    if not room:
        return False

    # Комната без пароля доступна всем валидным пользователям/гостям
    if not room["password"]:
        return True

    # Админ может входить везде
    if user and user.get("is_admin") == 1:
        return True

    # Создатель комнаты может входить
    if user and room["creator_id"] == user["id"]:
        return True

    # Пользователь/гость уже вводил пароль
    if token and manager.has_access(token, room_id):
        return True

    return False

def check_rate_limit(ip: str, max_count: int = RATE_LIMIT_MAX_MESSAGES,
                     window: float = RATE_LIMIT_WINDOW,
                     min_interval: float = RATE_LIMIT_MIN_INTERVAL) -> bool:
    """
    Проверяет ограничение скорости отправки сообщений для IP-адреса.
    
    Входы:
        ip (str): IP-адрес пользователя для проверки
        max_count (int): Максимальное количество сообщений за временной интервал (по умолчанию из конфига)
        window (float): Временное окно в секундах для подсчета сообщений (по умолчанию из конфига)
        min_interval (float): Минимальный интервал между сообщениями в секундах (по умолчанию из конфига)
    
    Выходы:
        bool: True - если лимит не превышен, сообщение разрешено; False - если лимит превышен
    """
    now = time.time()
    if ip not in message_timestamps:
        message_timestamps[ip] = []

    timestamps = message_timestamps[ip]
    timestamps[:] = [t for t in timestamps if now - t < window]

    if len(timestamps) >= max_count:
        return False

    if timestamps and now - timestamps[-1] < min_interval:
        return False

    timestamps.append(now)
    return True


def check_password_rate_limit(ip: str) -> bool:
    """
    Проверяет ограничение скорости попыток ввода пароля для IP-адреса.
    
    Входы:
        ip (str): IP-адрес пользователя для проверки
    
    Выходы:
        bool: True - если попытки в пределах лимита (не более 5 за 60 секунд); 
              False - если лимит превышен
    """
    now = time.time()
    if ip not in password_attempts:
        password_attempts[ip] = []

    attempts = password_attempts[ip]
    attempts[:] = [t for t in attempts if now - t < 60]

    if len(attempts) >= 5:
        return False

    attempts.append(now)
    return True


def sanitize_html(text: str) -> str:
    """
    Очищает текст от потенциально опасного HTML-кода и JavaScript.
    
    Входы:
        text (str): Исходный текст для очистки
    
    Выходы:
        str: Очищенный текст с экранированными HTML-сущностями и удаленными javascript: ссылками
    """
    if not text:
        return ""
    escaped = html.escape(text, quote=True)
    return re.sub(r'javascript:', '', escaped, flags=re.IGNORECASE)


def get_file_extension(filename: str) -> str:
    """
    Извлекает расширение файла из имени файла.
    
    Входы:
        filename (str): Имя файла для анализа
    
    Выходы:
        str: Расширение файла в нижнем регистре без точки; пустая строка, если расширение не найдено
    """
    if not filename:
        return ""

    basename = os.path.basename(filename)

    if basename.startswith('.'):
        if basename.count('.') == 1:
            return basename.lstrip('.').lower()

    if '.' in basename:
        return basename.rsplit('.', 1)[-1].lower()

    return ""


def get_file_type(extension: str) -> str:
    """
    Определяет тип файла на основе его расширения.
    
    Входы:
        extension (str): Расширение файла
    
    Выходы:
        str: Тип файла ('image', 'video', 'document', 'audio', 'archive' или 'other')
    """
    for file_type, extensions in ALLOWED_EXTENSIONS.items():
        if extension in extensions:
            return file_type
    return 'other'


def validate_file(file_content: bytes, filename: str) -> tuple:
    """
    Проверяет файл на соответствие требованиям: размер, тип, MIME-тип.
    
    Входы:
        file_content (bytes): Содержимое файла в байтах
        filename (str): Имя файла для определения типа
    
    Выходы:
        tuple: (file_type, extension) - тип файла и его расширение
    
    Исключения:
        HTTPException 400: Файл пустой или недопустимого типа
        HTTPException 413: Файл слишком большой
    """
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(413, "Файл слишком большой (максимум 50MB)")

    if len(file_content) == 0:
        raise HTTPException(400, "Файл пустой")

    if not filename or filename.startswith('.'):
        mime = magic.Magic(mime=True)
        detected_mime = mime.from_buffer(file_content[:1024])

        extension = None
        for ext, mime_type in EXTENSION_MIME_MAP.items():
            if detected_mime == mime_type or detected_mime.startswith(mime_type.split('/')[0]):
                extension = ext
                break

        if not extension:
            raise HTTPException(400, "Не удалось определить тип файла")

        file_type = get_file_type(extension)
        if file_type == 'other':
            raise HTTPException(400, "Недопустимый тип файла")

        return file_type, extension

    extension = get_file_extension(filename)

    if not extension:
        raise HTTPException(400, "Не удалось определить расширение файла")

    file_type = get_file_type(extension)

    if file_type == 'other':
        raise HTTPException(
            400, f"Недопустимое расширение файла: .{extension}")

    mime = magic.Magic(mime=True)
    detected_mime = mime.from_buffer(file_content[:1024])

    expected_mime = EXTENSION_MIME_MAP.get(extension)

    if detected_mime in ALLOWED_MIMETYPES:
        if detected_mime == 'application/octet-stream':
            if expected_mime and expected_mime in ALLOWED_MIMETYPES:
                return file_type, extension
        return file_type, extension

    if detected_mime == 'application/octet-stream' and expected_mime:
        return file_type, extension

    if extension == 'doc' and detected_mime in ('application/x-ole-storage', 'application/CDFV2', 'application/msword'):
        return file_type, extension

    if extension == 'docx' and detected_mime == 'application/zip':
        return file_type, extension

    if extension == 'wav' and detected_mime in ('audio/wav', 'audio/x-wav'):
        return file_type, extension

    if extension == 'flac' and detected_mime in ('audio/flac', 'audio/x-flac'):
        return file_type, extension

    raise HTTPException(400, f"Недопустимый тип файла: {detected_mime}")


@app.on_event("startup")
async def startup_event():
    """
    Выполняется при запуске приложения. Инициализирует базу данных и запускает очистку подключений.
    
    Входы: отсутствуют
    
    Выходы: отсутствуют (логирует запуск приложения)
    """
    init_db()
    await manager.start_cleanup()
    logger.info("Приложение запущено")


@app.get("/api/rooms", response_model=List[RoomResponse])
async def get_rooms():
    """
    Возвращает список всех доступных комнат.
    
    Входы: отсутствуют
    
    Выходы:
        List[RoomResponse]: Список комнат с информацией: id, name, color, has_password, creator_id
    """
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, name, color, password, creator_id FROM Room ORDER BY id')
    rooms = []
    for r in c.fetchall():
        room = dict(r)
        room['has_password'] = bool(room.pop('password'))
        rooms.append(room)
    conn.close()
    return rooms


@app.get("/api/guest-nickname")
async def get_guest_nickname():
    """
    Генерирует случайное гостевой никнейм, цвет и токен для неавторизованного пользователя.
    
    Входы: отсутствуют
    
    Выходы:
        dict: Словарь с полями nickname (str), color (str), token (str) - гостевой токен
    """
    adjectives = ['Happy', 'Cool', 'Smart', 'Fast', 'Brave', 'Gentle']
    nouns = ['Cat', 'Dog', 'Fox', 'Bear', 'Wolf', 'Eagle']
    adj = secrets.choice(adjectives)
    noun = secrets.choice(nouns)
    num = secrets.randbelow(1000)
    nick = sanitize_html(f"{adj}_{noun}_{num}")[:MAX_USERNAME_LENGTH]
    color = secrets.choice(AVAILABLE_COLORS)

    guest_token = secrets.token_hex(32)
    guest_tokens[guest_token] = {
        "nickname": nick,
        "color": color,
        "created_at": datetime.now()
    }

    return {"nickname": nick, "color": color, "token": guest_token}


@app.get("/api/user-counts")
async def get_user_counts():
    """
    Возвращает количество пользователей в каждой комнате.
    
    Входы: отсутствуют
    
    Выходы:
        dict: Словарь с полем counts, где ключ - room_id, значение - количество подключений
    """
    counts = {room_id: len(conns)
              for room_id, conns in manager.active_connections.items()}
    return {"counts": counts}


@app.get("/api/room/{room_id}/users")
async def get_room_users(room_id: int):
    """
    Возвращает список пользователей в указанной комнате.
    
    Входы:
        room_id (int): ID комнаты
    
    Выходы:
        List[dict]: Список пользователей с их данными (username, color, user_id, is_admin, connection_id)
    """
    return manager.get_room_users(room_id)


@app.get("/api/user/{user_id}")
async def get_username(user_id: int):
    """
    Возвращает информацию о пользователе по его ID.
    
    Входы:
        user_id (int): ID пользователя
    
    Выходы:
        dict: Словарь с полями username, color, is_admin
    
    Исключения:
        HTTPException 404: Пользователь не найден
    """
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT username, color, is_admin FROM User WHERE id=?', (user_id,))
    r = c.fetchone()
    conn.close()
    if not r:
        raise HTTPException(404, "Пользователь не найден")
    return {
        "username": sanitize_html(r['username']),
        "color": r['color'],
        "is_admin": r['is_admin']
    }


@app.get("/api/rooms/{room_id}/messages")
async def get_room_messages(room_id: int, request: Request, limit: int = 250, token: str = ""):
    """
    Возвращает историю сообщений в указанной комнате.
    
    Входы:
        room_id (int): ID комнаты
        limit (int): Максимальное количество сообщений для возврата (макс. 250)
    
    Выходы:
        List[dict]: Список сообщений с полями id, text, author, author_color, is_admin, room_id, timestamp, и полями для ответов
    
    Исключения:
        HTTPException 400: Неверный ID комнаты
        HTTPException 404: Комната не найдена
    """
    if room_id < 1:
        raise HTTPException(400, "Неверный ID комнаты")

    user = verify_token(token) if token else None
    guest = guest_tokens.get(token) if token else None

    if not user and not guest:
        raise HTTPException(401, "Требуется авторизация или гостевой токен")

    if not can_access_room(token, room_id, user, guest):
        raise HTTPException(403, "Нет доступа к комнате")

    if limit > 250:
        limit = 250

    conn = get_db()
    c = conn.cursor()

    c.execute('SELECT id FROM Room WHERE id=?', (room_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(404, "Комната не найдена")

    c.execute('''SELECT m.id, m.text, m.author_id,
                 COALESCE(u.username, m.author_guest) as author,
                 CASE
                     WHEN u.color IS NOT NULL THEN u.color
                     WHEN m.guest_color IS NOT NULL AND m.guest_color != '' THEN m.guest_color
                     ELSE '#888888'
                 END as author_color,
                 COALESCE(u.is_admin, 0) as is_admin,
                 m.room_id, m.timestamp,
                 m.is_reply, m.reply_msg_id, m.reply_author, m.reply_text, m.reply_author_color,
                 m.caption
                 FROM Message m LEFT JOIN User u ON m.author_id = u.id
                 WHERE m.room_id=? ORDER BY m.id DESC LIMIT ?''',
              (room_id, limit))

    msgs = []
    for r in c.fetchall():
        msg = dict(r)
        msg['author'] = sanitize_html(msg['author']) if msg['author'] else ''
        if not msg['author_color']:
            msg['author_color'] = '#888888'
        msgs.append(msg)

    msgs.reverse()
    conn.close()
    return msgs


@app.post("/api/update-profile")
async def update_profile(data: UpdateProfile):
    """
    Обновляет профиль пользователя (имя и/или цвет).
    
    Входы:
        data (UpdateProfile): Объект с полями token (str), username (str, опционально), color (str, опционально)
    
    Выходы:
        dict: Словарь с полем ok: True
    
    Исключения:
        HTTPException 401: Требуется авторизация (неверный токен)
        HTTPException 422: Некорректное имя (пустое, слишком длинное) или неверный формат цвета
    """
    user = verify_token(data.token)
    if not user:
        raise HTTPException(401, "Требуется авторизация")

    conn = get_db()
    c = conn.cursor()

    if data.username:
        u = sanitize_html(data.username.strip())
        if not u:
            conn.close()
            raise HTTPException(422, "Имя не может быть пустым")
        if len(u) > MAX_USERNAME_LENGTH:
            conn.close()
            raise HTTPException(
                422, f"Имя не может быть длиннее {MAX_USERNAME_LENGTH} символов")
        c.execute('UPDATE User SET username=? WHERE id=?', (u, user['id']))

    if data.color:
        if not re.match(r'^#[0-9a-fA-F]{6}$', data.color):
            conn.close()
            raise HTTPException(422, "Неверный формат цвета")
        c.execute('UPDATE User SET color=? WHERE id=?',
                  (data.color, user['id']))

    conn.commit()
    conn.close()
    logger.info(f'Профиль обновлен: user_id={user["id"]}')
    return {"ok": True}


@app.post("/api/messages", response_model=MessageResponse)
async def create_message(message: MessageCreate, request: Request):
    """
    Создает новое текстовое сообщение в комнате.
    
    Входы:
        message (MessageCreate): Объект с полями token (str), room_id (int), text (str), 
                                 reply_msg_id (int, опционально), reply_author (str, опционально),
                                 reply_text (str, опционально), reply_author_color (str, опционально)
        request (Request): Объект запроса для получения IP-адреса
    
    Выходы:
        MessageResponse: Объект созданного сообщения со всеми полями
    
    Исключения:
        HTTPException 401: Требуется авторизация (неверный токен)
        HTTPException 404: Комната не найдена
        HTTPException 422: Некорректное сообщение (пустое или слишком длинное)
        HTTPException 429: Превышен лимит отправки сообщений
    """
    user = verify_token(message.token) if message.token else None
    guest = guest_tokens.get(message.token) if message.token else None
    ip = request.client.host

    if not user and not guest:
        raise HTTPException(401, "Требуется авторизация или гостевой токен")
    
    if not can_access_room(message.token, message.room_id, user, guest):
        raise HTTPException(403, "Нет доступа к комнате")

    if not user or user['is_admin'] != 1:
        if not check_rate_limit(ip):
            logger.warning(f'Rate limit exceeded for IP: {ip}')
            raise HTTPException(429, "Слишком много сообщений. Подождите.")

    text = message.text.strip()
    if not text or len(text) > MAX_MESSAGE_LENGTH:
        raise HTTPException(422, "Некорректное сообщение")

    text = re.sub(r'<[^>]*>', '', text)
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)

    if not text.strip():
        raise HTTPException(422, "Сообщение не может быть пустым")

    conn = get_db()
    c = conn.cursor()

    c.execute('SELECT id FROM Room WHERE id=?', (message.room_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(404, "Комната не найдена")

    ts = datetime.now().isoformat()

    if user:
        author_id = user['id']
        author_guest = ''
        guest_color = ''
    else:
        author_id = 0
        author_guest = sanitize_html(guest["nickname"])
        guest_color = guest["color"]

    is_reply = 1 if message.reply_msg_id else 0
    reply_msg_id = message.reply_msg_id if is_reply else None
    reply_author = sanitize_html(message.reply_author) if is_reply else ''
    reply_text = message.reply_text if is_reply else ''
    reply_author_color = message.reply_author_color if is_reply else ''

    c.execute('''INSERT INTO Message (text, author_id, author_guest, room_id, timestamp, guest_color,
                 is_reply, reply_msg_id, reply_author, reply_text, reply_author_color)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
              (text, author_id, author_guest, message.room_id, ts, guest_color,
               is_reply, reply_msg_id, reply_author, reply_text, reply_author_color))
    mid = c.lastrowid
    conn.commit()

    if user:
        c.execute('''SELECT m.id, m.text, m.author_id, u.username as author,
                    u.color as author_color, u.is_admin, m.room_id, m.timestamp,
                    m.is_reply, m.reply_msg_id, m.reply_author, m.reply_text, m.reply_author_color,
                    m.caption
                    FROM Message m JOIN User u ON m.author_id = u.id
                    WHERE m.id=?''', (mid,))
    else:
        c.execute('''SELECT m.id, m.text, m.author_id, m.author_guest as author,
                    ? as author_color, 0 as is_admin, m.room_id, m.timestamp,
                    m.is_reply, m.reply_msg_id, m.reply_author, m.reply_text, m.reply_author_color,
                    m.caption
                    FROM Message m WHERE m.id=?''', (guest_color, mid))

    new_msg = dict(c.fetchone())
    new_msg['author'] = sanitize_html(
        new_msg['author']) if new_msg['author'] else ''
    conn.close()

    await manager.broadcast_to_room(message.room_id, {"type": "new_message", "message": new_msg})

    return new_msg


@app.post("/api/messages/file")
async def create_file_message(request: Request):
    """
    Создает сообщение с файлом в комнате.
    
    Входы:
        request (Request): JSON-объект с полями token, room_id, file_url, file_type, original_name, caption, 
                          reply_msg_id, reply_author, reply_text, reply_author_color
    
    Выходы:
        dict: Объект созданного файлового сообщения со всеми полями
    
    Исключения:
        HTTPException 401: Требуется авторизация (неверный токен)
        HTTPException 404: Комната не найдена или файл не найден
    """
    data = await request.json()
    token = data.get('token', '')
    room_id = data.get('room_id', 0)
    file_url = data.get('file_url', '')
    file_type = data.get('file_type', '')
    original_name = data.get('original_name', '')
    caption = data.get('caption', '')

    user = verify_token(token) if token else None
    guest = guest_tokens.get(token) if token else None

    if not user and not guest:
        raise HTTPException(401, "Требуется авторизация")
    
    if not can_access_room(token, room_id, user, guest):
        raise HTTPException(403, "Нет доступа к комнате")

    file_path = os.path.join(UPLOAD_DIR, os.path.basename(file_url))
    if not os.path.exists(file_path):
        raise HTTPException(404, "Файл не найден")

    conn = get_db()
    c = conn.cursor()

    c.execute('SELECT id FROM Room WHERE id=?', (room_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(404, "Комната не найдена")

    ts = datetime.now().isoformat()

    if user:
        author_id = user['id']
        author_guest = ''
        author_name = sanitize_html(user['username'])
        author_color = user['color']
        guest_color = ''
    else:
        author_id = 0
        author_guest = sanitize_html(guest["nickname"])
        author_name = author_guest
        author_color = guest["color"]
        guest_color = guest["color"]

    file_info = f"[FILE]{file_type}|{file_url}|{sanitize_html(original_name)}[/FILE]"

    is_reply = 1 if data.get('reply_msg_id') else 0
    reply_msg_id = data.get('reply_msg_id') if is_reply else None
    reply_author = sanitize_html(
        data.get('reply_author', '')) if is_reply else ''
    reply_text = data.get('reply_text', '') if is_reply else ''
    reply_author_color = data.get('reply_author_color', '') if is_reply else ''
    caption = sanitize_html(caption)[:MAX_MESSAGE_LENGTH] if caption else ''

    c.execute('''INSERT INTO Message (text, author_id, author_guest, room_id, timestamp, guest_color,
                 is_reply, reply_msg_id, reply_author, reply_text, reply_author_color, caption)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
              (file_info, author_id, author_guest, room_id, ts, guest_color,
               is_reply, reply_msg_id, reply_author, reply_text, reply_author_color, caption))
    mid = c.lastrowid
    conn.commit()

    new_msg = {
        "id": mid,
        "text": file_info,
        "author_id": author_id,
        "author": author_name,
        "author_color": author_color,
        "is_admin": user['is_admin'] if user else 0,
        "room_id": room_id,
        "timestamp": ts,
        "type": "file",
        "file_type": file_type,
        "file_url": file_url,
        "original_name": original_name,
        "caption": caption,
        "is_reply": is_reply,
        "reply_msg_id": reply_msg_id,
        "reply_author": reply_author,
        "reply_text": reply_text,
        "reply_author_color": reply_author_color
    }

    conn.close()

    await manager.broadcast_to_room(room_id, {"type": "new_message", "message": new_msg})

    return new_msg


@app.delete("/api/messages/{message_id}")
async def delete_message(message_id: int, data: MessageDelete):
    """
    Удаляет сообщение (доступно только администраторам).
    
    Входы:
        message_id (int): ID сообщения для удаления
        data (MessageDelete): Объект с полем token (str)
    
    Выходы:
        dict: Словарь с полем ok: True
    
    Исключения:
        HTTPException 401: Требуется авторизация (неверный токен)
        HTTPException 403: Недостаточно прав (только администраторы)
        HTTPException 404: Сообщение не найдено
    """
    user = verify_token(data.token)
    if not user:
        raise HTTPException(401, "Требуется авторизация")
    if user['is_admin'] != 1:
        log_suspicious_activity(
            user['id'], 'попытка удаления сообщения без прав')
        raise HTTPException(
            403, "Только администраторы могут удалять сообщения")

    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT room_id FROM Message WHERE id=?', (message_id,))
    msg = c.fetchone()

    if not msg:
        conn.close()
        raise HTTPException(404, "Сообщение не найдено")

    room_id = msg['room_id']
    c.execute('DELETE FROM Message WHERE id=?', (message_id,))
    conn.commit()
    conn.close()

    await manager.broadcast_to_room(room_id, {
        "type": "delete_message",
        "message_id": message_id,
        "room_id": room_id
    })

    logger.info(f'Сообщение {message_id} удалено админом {user["id"]}')
    return {"ok": True}


@app.post("/api/rooms", response_model=RoomResponse)
async def create_room(room: RoomCreate, request: Request):
    """
    Создает новую комнату чата.
    
    Входы:
        room (RoomCreate): Объект с полями token (str), name (str), color (str), password (str, опционально)
        request (Request): Объект запроса для получения IP-адреса
    
    Выходы:
        RoomResponse: Объект созданной комнаты с полями id, name, color, has_password, creator_id
    
    Исключения:
        HTTPException 401: Требуется авторизация (неверный токен)
        HTTPException 400: Комната с таким названием уже существует
        HTTPException 422: Некорректное название или неверный формат цвета
        HTTPException 429: Превышен лимит создания комнат (слишком много запросов или комнат)
    """
    user = verify_token(room.token)
    if not user:
        raise HTTPException(401, "Требуется авторизация")

    ip = request.client.host
    if not check_rate_limit(ip, 3, 60):
        raise HTTPException(429, "Слишком много запросов")

    name = sanitize_html(room.name.strip())
    if not name:
        raise HTTPException(422, "Название не может быть пустым")
    if len(name) > MAX_ROOM_NAME_LENGTH:
        raise HTTPException(
            422, f"Название не может быть длиннее {MAX_ROOM_NAME_LENGTH} символов")

    if not re.match(r'^#[0-9a-fA-F]{6}$', room.color):
        raise HTTPException(422, "Неверный формат цвета")

    if user['is_admin'] != 1:
        conn_check = get_db()
        c = conn_check.cursor()
        c.execute(
            'SELECT COUNT(*) as count FROM Room WHERE creator_id=?', (user['id'],))
        if c.fetchone()['count'] >= MAX_ROOMS_PER_USER:
            conn_check.close()
            raise HTTPException(
                429, f"Нельзя создать больше {MAX_ROOMS_PER_USER} комнат")
        conn_check.close()

    conn = get_db()
    c = conn.cursor()

    try:
        c.execute('INSERT INTO Room (name,color,password,creator_id) VALUES (?,?,?,?)',
                  (name, room.color, room.password[:100] if room.password else '', user['id']))
        rid = c.lastrowid
        conn.commit()
        c.execute(
            'SELECT id,name,color,password,creator_id FROM Room WHERE id=?', (rid,))
        new_room = dict(c.fetchone())
        conn.close()

        manager.grant_access(room.token, rid)

        broadcast_room = {
            "id": new_room['id'],
            "name": new_room['name'],
            "color": new_room['color'],
            "has_password": bool(new_room['password']),
            "creator_id": new_room['creator_id']
        }

        await manager.broadcast_global({"type": "new_room", "room": broadcast_room})
        await manager.broadcast_user_counts()

        logger.info(f'Комната создана: {name} (user_id={user["id"]})')
        return broadcast_room

    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(400, "Комната с таким названием уже существует")


@app.put("/api/rooms/{room_id}", response_model=RoomResponse)
async def update_room(room_id: int, room: RoomUpdate):
    """
    Обновляет информацию о комнате (название, цвет, пароль).
    
    Входы:
        room_id (int): ID комнаты для обновления
        room (RoomUpdate): Объект с полями token (str), name (str), color (str), password (str, опционально)
    
    Выходы:
        RoomResponse: Обновленный объект комнаты
    
    Исключения:
        HTTPException 401: Требуется авторизация (неверный токен)
        HTTPException 403: Нет прав на изменение комнаты
        HTTPException 404: Комната не найдена
        HTTPException 400: Комната с таким названием уже существует
        HTTPException 422: Некорректное название или неверный формат цвета
    """
    user = verify_token(room.token)
    if not user:
        raise HTTPException(401, "Требуется авторизация")

    name = sanitize_html(room.name.strip())
    if not name:
        raise HTTPException(422, "Название не может быть пустым")
    if len(name) > MAX_ROOM_NAME_LENGTH:
        raise HTTPException(
            422, f"Название не может быть длиннее {MAX_ROOM_NAME_LENGTH} символов")

    if not re.match(r'^#[0-9a-fA-F]{6}$', room.color):
        raise HTTPException(422, "Неверный формат цвета")

    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT creator_id FROM Room WHERE id=?', (room_id,))
    ex = c.fetchone()

    if not ex:
        conn.close()
        raise HTTPException(404, "Комната не найдена")

    if ex['creator_id'] != user['id'] and user['is_admin'] != 1:
        conn.close()
        log_suspicious_activity(
            user['id'], f'попытка изменения комнаты {room_id}')
        raise HTTPException(403, "Нет прав на изменение")

    try:
        c.execute('UPDATE Room SET name=?,color=?,password=? WHERE id=?',
                  (name, room.color, room.password[:100] if room.password else '', room_id))
        conn.commit()
        c.execute(
            'SELECT id,name,color,password,creator_id FROM Room WHERE id=?', (room_id,))
        upd = dict(c.fetchone())
        conn.close()

        broadcast_room = {
            "id": upd['id'],
            "name": upd['name'],
            "color": upd['color'],
            "has_password": bool(upd['password']),
            "creator_id": upd['creator_id']
        }

        await manager.broadcast_global({"type": "update_room", "room": broadcast_room})
        await manager.broadcast_to_room(room_id, {"type": "room_updated", "room": broadcast_room})

        logger.info(f'Комната обновлена: {room_id}')
        return broadcast_room

    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(400, "Комната с таким названием уже существует")


@app.delete("/api/rooms/{room_id}")
async def delete_room(room_id: int, data: RoomDelete):
    """
    Удаляет комнату и все её сообщения.
    
    Входы:
        room_id (int): ID комнаты для удаления
        data (RoomDelete): Объект с полем token (str)
    
    Выходы:
        dict: Словарь с полем ok: True
    
    Исключения:
        HTTPException 401: Требуется авторизация (неверный токен)
        HTTPException 403: Нет прав на удаление комнаты
        HTTPException 404: Комната не найдена
    """
    user = verify_token(data.token)
    if not user:
        raise HTTPException(401, "Требуется авторизация")

    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT creator_id FROM Room WHERE id=?', (room_id,))
    room = c.fetchone()

    if not room:
        conn.close()
        raise HTTPException(404, "Комната не найдена")

    if room['creator_id'] != user['id'] and user['is_admin'] != 1:
        conn.close()
        log_suspicious_activity(
            user['id'], f'попытка удаления комнаты {room_id}')
        raise HTTPException(403, "Вы не можете удалить эту комнату")

    c.execute('DELETE FROM Message WHERE room_id=?', (room_id,))
    c.execute('DELETE FROM Room WHERE id=?', (room_id,))
    conn.commit()
    conn.close()

    await manager.broadcast_global({"type": "delete_room", "room_id": room_id})
    await manager.broadcast_user_counts()

    logger.info(f'Комната удалена: {room_id}')
    return {"ok": True}


@app.post("/api/register", response_model=UserResponse)
async def register(user: UserRegister, request: Request):
    """
    Регистрирует нового пользователя.
    
    Входы:
        user (UserRegister): Объект с полями username (str), password (str)
        request (Request): Объект запроса для получения IP-адреса
    
    Выходы:
        UserResponse: Объект пользователя с полями id, username, color, token, is_admin
    
    Исключения:
        HTTPException 400: Пользователь с таким именем уже существует
        HTTPException 422: Некорректное имя (пустое или слишком длинное)
        HTTPException 429: Слишком много попыток регистрации
    """
    ip = request.client.host
    if not check_rate_limit(ip, 5, 3600):
        raise HTTPException(429, "Слишком много попыток регистрации")

    conn = get_db()
    c = conn.cursor()
    username = sanitize_html(user.username.strip())

    if not username:
        raise HTTPException(422, "Имя не может быть пустым")
    if len(username) > MAX_USERNAME_LENGTH:
        raise HTTPException(
            422, f"Имя не может быть длиннее {MAX_USERNAME_LENGTH} символов")

    c.execute('SELECT id FROM User WHERE username=?', (username,))
    if c.fetchone():
        conn.close()
        raise HTTPException(400, "Пользователь с таким именем уже существует")

    c.execute('INSERT INTO User (username,password,color) VALUES (?,?,?)',
              (username, user.password, '#007bff'))
    uid = c.lastrowid
    conn.commit()
    conn.close()

    token = generate_token()
    save_token(uid, token)

    log_auth_attempt(username, True)
    logger.info(f'Новый пользователь зарегистрирован: {username}')

    return {
        "id": uid,
        "username": username,
        "color": "#007bff",
        "token": token,
        "is_admin": 0
    }


@app.post("/api/login", response_model=UserResponse)
async def login(user: UserLogin, request: Request):
    """
    Авторизует существующего пользователя.
    
    Входы:
        user (UserLogin): Объект с полями username (str), password (str)
        request (Request): Объект запроса для получения IP-адреса
    
    Выходы:
        UserResponse: Объект пользователя с полями id, username, color, token, is_admin
    
    Исключения:
        HTTPException 401: Неверное имя пользователя или пароль
        HTTPException 429: Слишком много попыток входа
    """
    ip = request.client.host
    if not check_rate_limit(ip, 10, 3600):
        raise HTTPException(429, "Слишком много попыток входа")

    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id,username,password,color,is_admin FROM User WHERE username=?',
              (user.username,))
    row = c.fetchone()

    if not row:
        conn.close()
        log_auth_attempt(user.username, False)
        raise HTTPException(401, "Неверное имя пользователя или пароль")

    if row['password'] != user.password:
        conn.close()
        log_auth_attempt(user.username, False)
        raise HTTPException(401, "Неверное имя пользователя или пароль")

    conn.close()

    token = generate_token()
    save_token(row['id'], token)

    log_auth_attempt(user.username, True)
    logger.info(f'Пользователь вошел: {user.username}')

    return {
        "id": row['id'],
        "username": sanitize_html(row['username']),
        "color": row['color'],
        "token": token,
        "is_admin": row['is_admin']
    }


@app.post("/api/verify-token", response_model=UserResponse)
async def verify_token_endpoint(data: TokenVerify):
    """
    Проверяет валидность токена и возвращает информацию о пользователе.
    
    Входы:
        data (TokenVerify): Объект с полем token (str)
    
    Выходы:
        UserResponse: Объект пользователя с полями id, username, color, token, is_admin
    
    Исключения:
        HTTPException 401: Токен недействителен
    """
    user = verify_token(data.token)
    if not user:
        raise HTTPException(401, "Токен недействителен")

    return {
        "id": user['id'],
        "username": sanitize_html(user['username']),
        "color": user['color'],
        "token": data.token,
        "is_admin": user['is_admin']
    }


@app.post("/api/room/{room_id}/check-password")
async def check_room_password(room_id: int, data: PasswordCheck, request: Request):
    """
    Проверяет пароль для доступа к защищенной комнате.
    
    Входы:
        room_id (int): ID комнаты для проверки
        data (PasswordCheck): Объект с полями token (str, опционально), password (str)
        request (Request): Объект запроса для получения IP-адреса
    
    Выходы:
        dict: Словарь с полем valid (bool) - правильность пароля
    
    Исключения:
        HTTPException 404: Комната не найдена
        HTTPException 429: Слишком много попыток ввода пароля
    """
    ip = request.client.host

    if not check_password_rate_limit(ip):
        raise HTTPException(429, "Слишком много попыток. Попробуйте позже.")

    user = verify_token(data.token) if data.token else None
    guest = guest_tokens.get(data.token) if data.token else None

    if not user and not guest:
        raise HTTPException(401, "Требуется авторизация или гостевой токен")

    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT password FROM Room WHERE id=?', (room_id,))
    room = c.fetchone()
    conn.close()

    if not room:
        raise HTTPException(404, "Комната не найдена")

    valid = room['password'] == data.password

    if valid:
        manager.grant_access(data.token, room_id)

    return {"valid": valid}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), token: str = Form("")):
    """
    Загружает файл на сервер.
    
    Входы:
        file (UploadFile): Загружаемый файл
        token (str): Токен авторизации (для пользователей или гостей)
    
    Выходы:
        dict: Словарь с полями filename, original_name, url, type, size
    
    Исключения:
        HTTPException 400: Недопустимый тип файла или файл пустой
        HTTPException 401: Требуется авторизация (неверный токен)
        HTTPException 413: Файл слишком большой
    """
    user = verify_token(token) if token else None
    guest = guest_tokens.get(token) if token else None

    if not user and not guest:
        raise HTTPException(401, "Требуется авторизация или гостевой токен")

    content = await file.read()
    file_type, extension = validate_file(content, file.filename)

    safe_filename = f"{secrets.token_hex(16)}.{extension}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    with open(file_path, 'wb') as f:
        f.write(content)

    file_url = f"/files/{safe_filename}"

    logger.info(f'Файл загружен: {safe_filename} (тип: {file_type})')

    return {
        "filename": safe_filename,
        "original_name": sanitize_html(file.filename),
        "url": file_url,
        "type": file_type,
        "size": len(content)
    }


@app.websocket("/ws/global")
async def websocket_global(websocket: WebSocket):
    """
    Глобальный WebSocket-эндпоинт для получения обновлений о комнатах и пользователях.
    
    Входы:
        websocket (WebSocket): Объект WebSocket-соединения
    
    Выходы: отсутствуют (асинхронная обработка соединения)
    """
    await manager.connect_global(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                json.loads(data)
            except:
                pass
    except WebSocketDisconnect:
        await manager.disconnect_global(websocket)
    except Exception as e:
        logger.error(f'Ошибка глобального WebSocket: {e}')
        await manager.disconnect_global(websocket)


@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: int):
    """
    WebSocket-эндпоинт для подключения к конкретной комнате чата.
    
    Входы:
        websocket (WebSocket): Объект WebSocket-соединения
        room_id (int): ID комнаты для подключения
    
    Выходы: отсутствуют (асинхронная обработка соединения)
    
    Параметры запроса:
        token (str, опционально): Токен авторизации пользователя
        username (str, опционально): Имя гостя
        color (str, опционально): Цвет гостя в формате HEX
    """
    token = websocket.query_params.get("token", "")
    username = websocket.query_params.get("username", "Гость")
    color = websocket.query_params.get("color", "#888888")

    user = verify_token(token) if token else None
    guest = guest_tokens.get(token) if token else None

    if not user and not guest:
        await websocket.close(code=4001, reason="Требуется авторизация")
        return

    if not can_access_room(token, room_id, user, guest):
        await websocket.close(code=4003, reason="Нет доступа")
        return

    if user:
        username = sanitize_html(user['username'])
        color = user['color']
    else:
        username = sanitize_html(guest["nickname"])
        color = guest["color"]

    if not re.match(r'^#[0-9a-fA-F]{6}$', color):
        color = "#888888"

    user_id = user['id'] if user else 0
    is_admin = 1 if user and user['is_admin'] == 1 else 0

    await manager.connect(websocket, room_id, username, color, user_id, is_admin, token)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, room_id)
    except Exception as e:
        logger.error(f'Ошибка WebSocket комнаты {room_id}: {e}')
        await manager.disconnect(websocket, room_id)


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """
    Возвращает главную HTML-страницу приложения.
    
    Входы: отсутствуют
    
    Выходы:
        HTMLResponse: HTML-содержимое главной страницы
    
    Исключения: отсутствуют
    """
    with open(os.path.join(BASE_DIR, "templates", "index.html"), encoding='utf-8') as f:
        return HTMLResponse(content=f.read())