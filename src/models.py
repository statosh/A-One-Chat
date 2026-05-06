from pydantic import BaseModel, Field, validator
from typing import Optional
import re

MAX_USERNAME_LENGTH = 25
MAX_PASSWORD_LENGTH = 35
MAX_MESSAGE_LENGTH = 3000
COLOR_PATTERN = r'^#[0-9a-fA-F]{6}$'


def validate_color_field(v: str) -> str:
    """
    Проверяет корректность формата цвета.
    
    Входы:
        v (str): Цвет для проверки в формате HEX (например, #RRGGBB)
    
    Выходы:
        str: Исходное значение цвета, если оно корректно
    
    Исключения:
        ValueError: Если цвет не соответствует формату HEX
    """
    if not re.match(COLOR_PATTERN, v):
        raise ValueError('Неверный формат цвета')
    return v


def validate_username_field(v: str) -> str:
    """
    Проверяет корректность имени пользователя.
    
    Входы:
        v (str): Имя пользователя для проверки
    
    Выходы:
        str: Очищенное имя пользователя (без пробелов в начале и конце)
    
    Исключения:
        ValueError: Если имя пустое или превышает максимальную длину
    """
    if not v or not v.strip():
        raise ValueError('Имя не может быть пустым')
    if len(v.strip()) > MAX_USERNAME_LENGTH:
        raise ValueError(
            f'Имя не может быть длиннее {MAX_USERNAME_LENGTH} символов')
    return v.strip()


class MessageCreate(BaseModel):
    """
    Модель для создания нового сообщения.
    
    Атрибуты:
        text (str): Текст сообщения (от 1 до MAX_MESSAGE_LENGTH символов)
        room_id (int): ID комнаты, в которую отправляется сообщение
        token (str): Токен авторизации пользователя или гостя
        author (str): Имя автора (опционально, для гостей)
        author_color (str): Цвет автора (по умолчанию '#888888')
        reply_msg_id (Optional[int]): ID сообщения, на которое дан ответ
        reply_author (Optional[str]): Имя автора исходного сообщения
        reply_text (Optional[str]): Текст исходного сообщения
        reply_author_color (Optional[str]): Цвет автора исходного сообщения
    """
    text: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    room_id: int
    token: str = ''
    author: str = ''
    author_color: str = '#888888'
    reply_msg_id: Optional[int] = None
    reply_author: Optional[str] = ''
    reply_text: Optional[str] = ''
    reply_author_color: Optional[str] = ''

    @validator('text')
    def validate_text(cls, v):
        """
        Проверяет, что текст сообщения не пустой.
        
        Входы:
            v (str): Текст сообщения для проверки
        
        Выходы:
            str: Очищенный текст сообщения
        
        Исключения:
            ValueError: Если текст состоит только из пробелов
        """
        if not v.strip():
            raise ValueError('Сообщение не может быть пустым')
        return v.strip()


class MessageResponse(BaseModel):
    """
    Модель ответа с данными сообщения.
    
    Атрибуты:
        id (int): Уникальный ID сообщения
        text (str): Текст сообщения
        author_id (int): ID автора (0 для гостей)
        author (str): Имя автора
        author_color (str): Цвет автора
        is_admin (int): Флаг администратора (1 - да, 0 - нет)
        room_id (int): ID комнаты
        timestamp (str): Временная метка в формате ISO
        type (str): Тип сообщения ("message" или "file")
        is_reply (int): Флаг ответа на другое сообщение
        reply_msg_id (Optional[int]): ID исходного сообщения для ответа
        reply_author (Optional[str]): Имя автора исходного сообщения
        reply_text (Optional[str]): Текст исходного сообщения
        reply_author_color (Optional[str]): Цвет автора исходного сообщения
    """
    id: int
    text: str
    author_id: int
    author: str = ''
    author_color: str = ''
    is_admin: int = 0
    room_id: int
    timestamp: str
    type: str = "message"
    is_reply: int = 0
    reply_msg_id: Optional[int] = None
    reply_author: Optional[str] = ''
    reply_text: Optional[str] = ''
    reply_author_color: Optional[str] = ''


class RoomBase(BaseModel):
    """
    Базовая модель комнаты с общими атрибутами.
    
    Атрибуты:
        name (str): Название комнаты (не может быть пустым)
        color (str): Цвет комнаты в формате HEX (по умолчанию '#007bff')
        password (str): Пароль комнаты (опционально, по умолчанию пустая строка)
    """
    name: str = Field(..., min_length=1)
    color: str = Field(default='#007bff')
    password: str = ''

    @validator('color')
    def validate_color(cls, v):
        """
        Проверяет корректность цвета комнаты.
        
        Входы:
            v (str): Цвет для проверки
        
        Выходы:
            str: Исходное значение цвета
        
        Исключения:
            ValueError: Если цвет не соответствует формату HEX
        """
        return validate_color_field(v)


class RoomResponse(BaseModel):
    """
    Модель ответа с данными комнаты.
    
    Атрибуты:
        id (int): Уникальный ID комнаты
        name (str): Название комнаты
        color (str): Цвет комнаты
        has_password (bool): Есть ли у комнаты пароль (по умолчанию False)
        creator_id (Optional[int]): ID создателя комнаты
    """
    id: int
    name: str
    color: str
    has_password: bool = False
    creator_id: Optional[int] = None


class RoomCreate(RoomBase):
    """
    Модель для создания новой комнаты.
    
    Атрибуты:
        name (str): Название комнаты
        color (str): Цвет комнаты
        password (str): Пароль комнаты
        token (str): Токен авторизации пользователя-создателя
    """
    token: str


class RoomUpdate(RoomBase):
    """
    Модель для обновления существующей комнаты.
    
    Атрибуты:
        name (str): Новое название комнаты
        color (str): Новый цвет комнаты
        password (str): Новый пароль комнаты
        token (str): Токен авторизации пользователя
    """
    token: str


class UserRegister(BaseModel):
    """
    Модель для регистрации нового пользователя.
    
    Атрибуты:
        username (str): Имя пользователя (от 1 до MAX_USERNAME_LENGTH символов)
        password (str): Пароль пользователя (от 4 до MAX_PASSWORD_LENGTH символов)
    """
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=4, max_length=MAX_PASSWORD_LENGTH)

    @validator('username')
    def validate_username(cls, v):
        """
        Проверяет корректность имени пользователя при регистрации.
        
        Входы:
            v (str): Имя пользователя для проверки
        
        Выходы:
            str: Очищенное имя пользователя
        
        Исключения:
            ValueError: Если имя пустое или превышает максимальную длину
        """
        return validate_username_field(v)


class UserLogin(BaseModel):
    """
    Модель для входа существующего пользователя.
    
    Атрибуты:
        username (str): Имя пользователя
        password (str): Пароль пользователя
    """
    username: str
    password: str


class UserResponse(BaseModel):
    """
    Модель ответа с данными пользователя.
    
    Атрибуты:
        id (int): Уникальный ID пользователя
        username (str): Имя пользователя
        color (str): Цвет пользователя
        token (str): Токен авторизации
        is_admin (int): Флаг администратора (1 - да, 0 - нет)
    """
    id: int
    username: str
    color: str
    token: str
    is_admin: int = 0


class RoomDelete(BaseModel):
    """
    Модель для удаления комнаты.
    
    Атрибуты:
        token (str): Токен авторизации пользователя
    """
    token: str


class TokenVerify(BaseModel):
    """
    Модель для проверки токена авторизации.
    
    Атрибуты:
        token (str): Токен для проверки
    """
    token: str


class UpdateProfile(BaseModel):
    """
    Модель для обновления профиля пользователя.
    
    Атрибуты:
        token (str): Токен авторизации пользователя
        username (Optional[str]): Новое имя пользователя (опционально)
        color (Optional[str]): Новый цвет пользователя в формате HEX (опционально)
    """
    token: str
    username: Optional[str] = None
    color: Optional[str] = None

    @validator('username')
    def validate_username(cls, v):
        """
        Проверяет корректность нового имени пользователя (если указано).
        
        Входы:
            v (Optional[str]): Новое имя пользователя
        
        Выходы:
            Optional[str]: Исходное значение, если оно None, иначе очищенное имя
        
        Исключения:
            ValueError: Если имя пустое или превышает максимальную длину
        """
        if v is not None:
            return validate_username_field(v)
        return v

    @validator('color')
    def validate_color(cls, v):
        """
        Проверяет корректность нового цвета пользователя (если указан).
        
        Входы:
            v (Optional[str]): Новый цвет в формате HEX
        
        Выходы:
            Optional[str]: Исходное значение, если оно None, иначе проверенный цвет
        
        Исключения:
            ValueError: Если цвет не соответствует формату HEX
        """
        if v is not None:
            return validate_color_field(v)
        return v


class MessageDelete(BaseModel):
    """
    Модель для удаления сообщения.
    
    Атрибуты:
        token (str): Токен авторизации пользователя (должен быть администратором)
    """
    token: str


class PasswordCheck(BaseModel):
    """
    Модель для проверки пароля комнаты.
    
    Атрибуты:
        token (str): Токен авторизации пользователя или гостя
        password (str): Пароль для проверки
    """
    token: str
    password: str