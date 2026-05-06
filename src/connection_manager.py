from fastapi import WebSocket
from typing import List, Dict, Optional, Set
from datetime import datetime
import asyncio
import logging
import re
from collections import defaultdict

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Менеджер WebSocket-соединений для управления комнатами чата.
    
    Управляет подключениями к комнатам, глобальными подключениями,
    доступом к комнатам, ограничениями по IP и рассылкой сообщений.
    """
    
    def __init__(self):
        """
        Инициализирует менеджер соединений.
        
        Входы: отсутствуют
        
        Выходы: отсутствуют (инициализирует внутренние структуры данных)
        """
        self.active_connections: Dict[int, List[dict]] = {}
        """Словарь активных подключений: ключ - room_id, значение - список подключений"""
        
        self.global_connections: List[WebSocket] = []
        """Список глобальных WebSocket-подключений"""
        
        self.room_access: Dict[str, Set[int]] = {}
        """Словарь доступа к комнатам: ключ - токен, значение - множество ID комнат"""
        
        self._lock = asyncio.Lock()
        """Асинхронная блокировка для потокобезопасной работы"""
        
        self._cleanup_task: Optional[asyncio.Task] = None
        """Задача фоновой очистки неактивных соединений"""
        
        self.ip_connections: Dict[str, int] = defaultdict(int)
        """Словарь количества подключений по IP-адресам"""
        
        self.MAX_CONNECTIONS_PER_IP = 5
        """Максимальное количество подключений с одного IP-адреса"""

    async def start_cleanup(self):
        """
        Запускает фоновую задачу очистки неактивных соединений.
        
        Входы: отсутствуют
        
        Выходы: отсутствуют (создает асинхронную задачу, если она еще не запущена)
        """
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(
                self._cleanup_dead_connections())

    async def _cleanup_dead_connections(self):
        """
        Фоновая задача для периодической очистки неактивных соединений.
        
        Входы: отсутствуют
        
        Выходы: отсутствуют (бесконечный цикл с паузой 60 секунд)
        """
        while True:
            await asyncio.sleep(60)
            async with self._lock:
                dead_rooms = []
                for room_id, connections in self.active_connections.items():
                    alive_connections = [
                        conn for conn in connections
                        if conn["ws"].client_state.name != "DISCONNECTED"
                    ]
                    if alive_connections:
                        self.active_connections[room_id] = alive_connections
                    else:
                        dead_rooms.append(room_id)

                for room_id in dead_rooms:
                    del self.active_connections[room_id]

                self.global_connections = [
                    conn for conn in self.global_connections
                    if conn.client_state.name != "DISCONNECTED"
                ]

    def check_ip_limit(self, client_ip: str) -> bool:
        """
        Проверяет, не превышен ли лимит подключений для данного IP-адреса.
        
        Входы:
            client_ip (str): IP-адрес клиента для проверки
        
        Выходы:
            bool: True - если лимит не превышен, False - если превышен
        """
        return self.ip_connections[client_ip] < self.MAX_CONNECTIONS_PER_IP

    def add_ip_connection(self, client_ip: str):
        """
        Увеличивает счетчик подключений для IP-адреса.
        
        Входы:
            client_ip (str): IP-адрес клиента
        
        Выходы: отсутствуют (увеличивает счетчик в self.ip_connections)
        """
        self.ip_connections[client_ip] += 1

    def remove_ip_connection(self, client_ip: str):
        """
        Уменьшает счетчик подключений для IP-адреса.
        
        Входы:
            client_ip (str): IP-адрес клиента
        
        Выходы: отсутствуют (уменьшает счетчик, если он больше 0)
        """
        if self.ip_connections[client_ip] > 0:
            self.ip_connections[client_ip] -= 1

    def validate_username(self, username: str) -> str:
        """
        Очищает и валидирует имя пользователя.
        
        Входы:
            username (str): Исходное имя пользователя
        
        Выходы:
            str: Очищенное имя пользователя (обрезано до 25 символов, удалены HTML-теги) 
                 или "Гость" при пустом значении
        """
        if not username:
            return "Гость"
        cleaned = username.strip()[:25]
        cleaned = cleaned.replace('<', '').replace(
            '>', '').replace('&', '&amp;')
        return cleaned or "Гость"

    def validate_color(self, color: str) -> str:
        """
        Проверяет и валидирует цвет в формате HEX.
        
        Входы:
            color (str): Цвет в формате HEX (например, #RRGGBB)
        
        Выходы:
            str: Исходный цвет, если он соответствует формату, иначе '#888888'
        """
        if re.match(r'^#[0-9a-fA-F]{6}$', color):
            return color
        return '#888888'

    def grant_access(self, token: str, room_id: int):
        """
        Предоставляет доступ к комнате по токену.
        
        Входы:
            token (str): Токен пользователя для авторизации
            room_id (int): ID комнаты, к которой предоставляется доступ
        
        Выходы: отсутствуют (добавляет room_id в список доступных комнат для токена)
        """
        if not token:
            return
        if token not in self.room_access:
            self.room_access[token] = set()
        self.room_access[token].add(room_id)

    def has_access(self, token: str, room_id: int) -> bool:
        """
        Проверяет, есть ли у токена доступ к комнате.
        
        Входы:
            token (str): Токен пользователя для проверки
            room_id (int): ID комнаты для проверки доступа
        
        Выходы:
            bool: True - если доступ есть, False - если доступа нет
        """
        return token in self.room_access and room_id in self.room_access[token]

    async def broadcast_user_counts(self):
        """
        Рассылает всем глобальным подключениям количество пользователей в каждой комнате.
        
        Входы: отсутствуют
        
        Выходы: отсутствует (отправляет сообщение типа "user_counts" всем глобальным сокетам)
        """
        async with self._lock:
            counts = {room_id: len(conns) for room_id,
                      conns in self.active_connections.items()}
        await self.broadcast_global({"type": "user_counts", "counts": counts})

    async def broadcast_user_list(self, room_id: int):
        """
        Рассылает в комнату обновленный список пользователей.
        
        Входы:
            room_id (int): ID комнаты, в которую отправляется список пользователей
        
        Выходы: отсутствует (отправляет сообщение типа "user_list" всем в комнате)
        """
        users = self.get_room_users(room_id)
        await self.broadcast_to_room(room_id, {"type": "user_list", "users": users})

    async def connect(self, websocket: WebSocket, room_id: int, username: str,
                      color: str, user_id: int = 0, is_admin: int = 0, token: str = ""):
        """
        Подключает WebSocket к указанной комнате.
        
        Входы:
            websocket (WebSocket): Объект WebSocket для подключения
            room_id (int): ID комнаты для подключения
            username (str): Имя пользователя
            color (str): Цвет пользователя в формате HEX
            user_id (int): ID пользователя (по умолчанию 0 для гостей)
            is_admin (int): Флаг администратора (1 - администратор, 0 - обычный пользователь)
            token (str): Токен авторизации (по умолчанию пустая строка)
        
        Выходы: отсутствует (подключает сокет, проверяет IP-лимит, рассылает уведомления)
        """
        try:
            if websocket.client_state.name == "CONNECTED":
                pass
            else:
                await websocket.accept()
        except Exception as e:
            logger.error(f'Ошибка accept WebSocket: {e}')
            return

        username = self.validate_username(username)
        color = self.validate_color(color)
        user_id = max(0, int(user_id))
        is_admin = 1 if is_admin == 1 else 0

        client_ip = "unknown"
        try:
            client_ip = websocket.client.host if hasattr(
                websocket, 'client') else "unknown"
        except:
            pass

        if not self.check_ip_limit(client_ip):
            await websocket.close(code=4000, reason="Слишком много подключений")
            return

        self.add_ip_connection(client_ip)

        async with self._lock:
            if room_id not in self.active_connections:
                self.active_connections[room_id] = []

            existing = [
                conn for conn in self.active_connections[room_id]
                if conn["ws"] == websocket
            ]
            if not existing:
                self.active_connections[room_id].append({
                    "ws": websocket,
                    "username": username,
                    "color": color,
                    "user_id": user_id,
                    "is_admin": is_admin,
                    "token": token,
                    "connected_at": datetime.now(),
                    "client_ip": client_ip
                })

        await self.broadcast_user_counts()
        await self.broadcast_user_list(room_id)

        notification = {
            "type": "system",
            "text": f"{username} подключился к комнате",
            "author": "Система",
            "author_color": "#888888",
            "room_id": room_id,
            "timestamp": datetime.now().isoformat()
        }

        async with self._lock:
            connections = self.active_connections.get(room_id, [])

        for conn in connections:
            if conn["ws"] != websocket:
                try:
                    await conn["ws"].send_json(notification)
                except Exception:
                    pass

        try:
            await websocket.send_json({
                "type": "system",
                "text": "Вы подключились к комнате",
                "author": "Система",
                "author_color": "#888888",
                "room_id": room_id,
                "timestamp": datetime.now().isoformat()
            })
        except Exception:
            pass

    async def connect_global(self, websocket: WebSocket):
        """
        Подключает глобальный WebSocket для получения общих уведомлений.
        
        Входы:
            websocket (WebSocket): Объект WebSocket для глобального подключения
        
        Выходы: отсутствует (подключает сокет и отправляет текущие счетчики пользователей)
        """
        try:
            if websocket.client_state.name == "CONNECTED":
                pass
            else:
                await websocket.accept()
        except Exception as e:
            logger.error(f'Ошибка accept глобального WebSocket: {e}')
            return

        client_ip = websocket.client.host if hasattr(
            websocket, 'client') else "unknown"

        if not self.check_ip_limit(client_ip):
            await websocket.close(code=4000, reason="Слишком много подключений")
            return

        self.add_ip_connection(client_ip)

        async with self._lock:
            if websocket not in self.global_connections:
                self.global_connections.append(websocket)

        async with self._lock:
            counts = {room_id: len(conns) for room_id,
                      conns in self.active_connections.items()}

        try:
            await websocket.send_json({"type": "user_counts", "counts": counts})
        except Exception:
            pass

    async def disconnect(self, websocket: WebSocket, room_id: int):
        """
        Отключает WebSocket от комнаты.
        
        Входы:
            websocket (WebSocket): Объект WebSocket для отключения
            room_id (int): ID комнаты, из которой отключается пользователь
        
        Выходы: отсутствует (удаляет соединение, уведомляет других пользователей)
        """
        user_info = None

        async with self._lock:
            if room_id in self.active_connections:
                for conn in self.active_connections[room_id]:
                    if conn["ws"] == websocket:
                        user_info = conn
                        break

                if user_info:
                    self.active_connections[room_id].remove(user_info)
                    self.remove_ip_connection(
                        user_info.get("client_ip", "unknown"))

                if not self.active_connections[room_id]:
                    del self.active_connections[room_id]

        if user_info:
            asyncio.create_task(self._notify_disconnect(room_id, user_info))

        asyncio.create_task(self.broadcast_user_counts())
        asyncio.create_task(self.broadcast_user_list(room_id))

    async def _notify_disconnect(self, room_id: int, user_info: dict):
        """
        Уведомляет пользователей комнаты об отключении участника.
        
        Входы:
            room_id (int): ID комнаты, где произошло отключение
            user_info (dict): Информация об отключившемся пользователе
        
        Выходы: отсутствует (отправляет системное сообщение всем в комнате)
        """
        notification = {
            "type": "system",
            "text": f"{user_info['username']} отключился от комнаты",
            "author": "Система",
            "author_color": "#888888",
            "room_id": room_id,
            "timestamp": datetime.now().isoformat()
        }

        async with self._lock:
            connections = self.active_connections.get(room_id, [])

        for conn in connections:
            try:
                await conn["ws"].send_json(notification)
            except Exception:
                pass

    async def disconnect_global(self, websocket: WebSocket):
        """
        Отключает глобальный WebSocket.
        
        Входы:
            websocket (WebSocket): Объект глобального WebSocket для отключения
        
        Выходы: отсутствует (удаляет соединение из глобального списка)
        """
        async with self._lock:
            if websocket in self.global_connections:
                self.global_connections.remove(websocket)
                self.remove_ip_connection(websocket.client.host if hasattr(
                    websocket, 'client') else "unknown")

    async def broadcast_to_room(self, room_id: int, message: dict):
        """
        Рассылает сообщение всем пользователям в указанной комнате.
        
        Входы:
            room_id (int): ID комнаты для рассылки
            message (dict): Сообщение для отправки (должно содержать поле 'type')
        
        Выходы: отсутствует (отправляет сообщение, удаляет мертвые соединения)
        """
        if not isinstance(message, dict) or 'type' not in message:
            return

        async with self._lock:
            connections = self.active_connections.get(room_id, [])

        dead = []
        for conn in connections:
            try:
                await conn["ws"].send_json(message)
            except Exception:
                dead.append(conn)

        if dead:
            async with self._lock:
                if room_id in self.active_connections:
                    self.active_connections[room_id] = [
                        c for c in self.active_connections[room_id]
                        if c not in dead
                    ]
                    if not self.active_connections[room_id]:
                        del self.active_connections[room_id]

    async def broadcast_global(self, message: dict):
        """
        Рассылает сообщение всем глобальным подключениям.
        
        Входы:
            message (dict): Сообщение для отправки (должно содержать поле 'type')
        
        Выходы: отсутствует (отправляет сообщение, удаляет мертвые соединения)
        """
        if not isinstance(message, dict) or 'type' not in message:
            return

        async with self._lock:
            connections = self.global_connections.copy()

        dead = []
        for conn in connections:
            try:
                await conn.send_json(message)
            except Exception:
                dead.append(conn)

        if dead:
            async with self._lock:
                self.global_connections = [
                    c for c in self.global_connections if c not in dead
                ]

    def get_room_users(self, room_id: int) -> List[dict]:
        """
        Возвращает список пользователей в указанной комнате.
        
        Входы:
            room_id (int): ID комнаты для получения списка пользователей
        
        Выходы:
            List[dict]: Список словарей с ключами 'username', 'color', 'is_admin'
        """
        connections = self.active_connections.get(room_id, [])
        return [
            {
                "username": c["username"],
                "color": c["color"],
                "is_admin": c.get("is_admin", 0)
            }
            for c in connections
        ]