import sqlite3
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db():
    """
    Инициализирует базу данных, создавая все необходимые таблицы и индексы.
    
    Входы: отсутствуют
    
    Выходы: отсутствуют (создает файл базы данных 'chat.db' и таблицы)
    
    Создаваемые таблицы:
        - User: пользователи системы (id, username, password, color, is_admin)
        - AuthToken: токены авторизации (id, user_id, token, created_at)
        - Room: комнаты чата (id, name, color, password, creator_id)
        - Message: сообщения (id, text, author_id, author_guest, room_id, 
                    timestamp, guest_color, is_reply, reply_msg_id, reply_author, 
                    reply_text, reply_author_color, caption)
    
    Индексы:
        - idx_auth_token: для быстрого поиска по токену
        - idx_message_room: для быстрых запросов сообщений комнаты
        - idx_message_author: для быстрых запросов сообщений автора
        - idx_room_creator: для быстрых запросов комнат создателя
    
    Настройки SQLite:
        - journal_mode=WAL: улучшенный режим журналирования
        - synchronous=NORMAL: баланс производительности и безопасности
        - busy_timeout=5000: таймаут ожидания при блокировке (5 секунд)
    
    Примечание: Если таблица Room пуста, создается комната по умолчанию "Общая комната"
    """
    conn = sqlite3.connect('chat.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS User (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        color TEXT NOT NULL DEFAULT '#007bff',
        is_admin INTEGER NOT NULL DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS AuthToken (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token TEXT NOT NULL UNIQUE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES User (id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS Room (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        color TEXT NOT NULL DEFAULT '#007bff',
        password TEXT NOT NULL DEFAULT '',
        creator_id INTEGER,
        FOREIGN KEY (creator_id) REFERENCES User (id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS Message (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT NOT NULL,
        author_id INTEGER,
        author_guest TEXT DEFAULT '',
        room_id INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        guest_color TEXT DEFAULT '',
        is_reply INTEGER NOT NULL DEFAULT 0,
        reply_msg_id INTEGER,
        reply_author TEXT DEFAULT '',
        reply_text TEXT DEFAULT '',
        reply_author_color TEXT DEFAULT '',
        caption TEXT DEFAULT '',
        FOREIGN KEY (room_id) REFERENCES Room (id)
    )''')

    c.execute('CREATE INDEX IF NOT EXISTS idx_auth_token ON AuthToken(token)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_message_room ON Message(room_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_message_author ON Message(author_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_room_creator ON Room(creator_id)')

    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA synchronous=NORMAL')
    c.execute('PRAGMA busy_timeout=5000')

    c.execute('SELECT COUNT(*) FROM Room')
    if c.fetchone()[0] == 0:
        c.execute(
            'INSERT INTO Room (name,color,password,creator_id) VALUES (?,?,?,?)',
            ('Общая комната', '#28a745', '', None)
        )
        logger.info('Создана комната по умолчанию')

    conn.commit()
    conn.close()
    logger.info('База данных инициализирована')


def get_db():
    """
    Устанавливает соединение с базой данных и настраивает row_factory для удобной работы.
    
    Входы: отсутствуют
    
    Выходы:
        sqlite3.Connection: Объект соединения с БД с настроенным row_factory=sqlite3.Row,
                           что позволяет обращаться к колонкам по имени (как к словарю)
    
    Примечание: Соединение должно быть закрыто после использования вызовом conn.close()
    """
    conn = sqlite3.connect('chat.db')
    conn.row_factory = sqlite3.Row
    return conn


def generate_token() -> str:
    """
    Генерирует криптографически безопасный токен для авторизации пользователя.
    
    Входы: отсутствуют
    
    Выходы:
        str: Случайная строка из 64 шестнадцатеричных символов (32 байта в HEX)
    
    Примечание: Используется secrets.token_hex для обеспечения криптографической безопасности
    """
    import secrets
    return secrets.token_hex(32)


def save_token(user_id: int, token: str):
    """
    Сохраняет токен авторизации в базе данных для указанного пользователя.
    
    Входы:
        user_id (int): ID пользователя, которому выдается токен
        token (str): Токен авторизации для сохранения
    
    Выходы: отсутствуют (сохраняет запись в таблицу AuthToken)
    
    Примечание: Логирует информацию о сохранении токена
    """
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO AuthToken (user_id, token) VALUES (?,?)',
              (user_id, token))
    conn.commit()
    conn.close()
    logger.info(f'Токен сохранен для пользователя {user_id}')


def verify_token(token: str):
    """
    Проверяет валидность токена и возвращает информацию о пользователе.
    
    Входы:
        token (str): Токен авторизации для проверки
    
    Выходы:
        dict or None: Словарь с данными пользователя (id, username, color, is_admin),
                     если токен валиден; None - если токен не передан или не найден
    
    Примечание: Выполняет JOIN между таблицами User и AuthToken для получения данных
    """
    if not token:
        return None
    conn = get_db()
    c = conn.cursor()
    c.execute(
        'SELECT u.id, u.username, u.color, u.is_admin FROM User u '
        'JOIN AuthToken t ON u.id=t.user_id WHERE t.token=?',
        (token,)
    )
    u = c.fetchone()
    conn.close()
    return dict(u) if u else None


def log_auth_attempt(username: str, success: bool):
    """
    Логирует попытку аутентификации пользователя.
    
    Входы:
        username (str): Имя пользователя, предпринявшего попытку входа
        success (bool): True - успешный вход, False - неудачная попытка
    
    Выходы: отсутствуют (записывает информацию в лог)
    
    Уровни логирования:
        - INFO: для успешных попыток входа
        - WARNING: для неудачных попыток входа
    """
    if success:
        logger.info(f'Успешный вход: {username}')
    else:
        logger.warning(f'Неудачная попытка входа: {username}')


def log_suspicious_activity(user_id: int, action: str):
    """
    Логирует подозрительную активность пользователя в системе.
    
    Входы:
        user_id (int): ID пользователя, совершившего подозрительное действие
        action (str): Описание подозрительного действия
    
    Выходы: отсутствуют (записывает предупреждение в лог)
    
    Примеры действий:
        - "попытка удаления сообщения без прав"
        - "попытка изменения комнаты"
        - "попытка удаления комнаты"
    
    Примечание: Используется уровень логирования WARNING для привлечения внимания
    """
    logger.warning(
        f'Подозрительная активность: пользователь {user_id}, действие: {action}')