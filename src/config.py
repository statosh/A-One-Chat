import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_ROOM_NAME_LENGTH = 25
MAX_MESSAGE_LENGTH = 3000
MAX_PASSWORD_LENGTH = 35
RATE_LIMIT_MAX_MESSAGES = 20
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MIN_INTERVAL = 1
MAX_ROOMS_PER_USER = 3
MAX_WEBSOCKET_CONNECTIONS_PER_IP = 5
MAX_FILE_SIZE = 50 * 1024 * 1024
UPLOAD_DIR = os.path.join(BASE_DIR, "user_files")


os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {
    'image': {'png', 'jpg', 'jpeg', 'gif'},
    'video': {'mp4'},
    'audio': {'ogg', 'wav', 'mp3', 'flac'},
    'document': {'txt', 'doc', 'docx', 'md'}
}

ALLOWED_MIMETYPES = {
    'image/png', 'image/jpeg', 'image/gif',
    'video/mp4',
    'audio/ogg', 'audio/wav', 'audio/x-wav', 'audio/mpeg', 'audio/mp3',
    'audio/flac', 'audio/x-flac',
    'text/plain', 'application/msword', 'application/CDFV2',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/zip', 'application/x-ole-storage',
    'text/markdown',
    'application/octet-stream'
}

EXTENSION_MIME_MAP = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'gif': 'image/gif',
    'mp4': 'video/mp4',
    'ogg': 'audio/ogg',
    'wav': 'audio/wav',
    'mp3': 'audio/mpeg',
    'flac': 'audio/flac',
    'txt': 'text/plain',
    'doc': 'application/msword',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'md': 'text/markdown'
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Промежуточное программное обеспечение для добавления заголовков безопасности.
    
    Назначение:
        Добавляет HTTP-заголовки безопасности ко всем ответам сервера для защиты
        от распространенных веб-уязвимостей.
    
    Добавляемые заголовки:
        Content-Security-Policy (CSP): 
            - default-src 'self' - загрузка ресурсов только с того же источника
            - script-src 'self' https://cdnjs.cloudflare.com - скрипты с текущего сайта и Cloudflare CDN
            - style-src 'self' https://cdnjs.cloudflare.com 'unsafe-inline' - стили с разрешением inline
            - font-src 'self' https://cdnjs.cloudflare.com - шрифты
            - connect-src 'self' ws: wss: - WebSocket-соединения
            - img-src 'self' data: blob: - изображения с data URL и blob
            - media-src 'self' blob: - медиафайлы
        
        X-Content-Type-Options: nosniff - запрещает MIME-тип sniffing
        X-Frame-Options: DENY - запрещает вложение в фреймы (защита от clickjacking)
        X-XSS-Protection: 1; mode=block - включает защиту браузера от XSS
        Referrer-Policy: strict-origin-when-cross-origin - контроль передачи referrer
    
    Входы:
        request: Запрос от клиента
        call_next: Функция для передачи запроса дальше по цепочке
    
    Выходы:
        Response: Ответ с добавленными заголовками безопасности
    """
    
    async def dispatch(self, request, call_next):
        """
        Обрабатывает запрос и добавляет заголовки безопасности в ответ.
        
        Входы:
            request: Входящий HTTP-запрос
            call_next: Функция следующего middleware или обработчика
        
        Выходы:
            Response: HTTP-ответ с добавленными заголовками безопасности
        """
        response = await call_next(request)
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' https://cdnjs.cloudflare.com; style-src 'self' https://cdnjs.cloudflare.com 'unsafe-inline'; font-src 'self' https://cdnjs.cloudflare.com; connect-src 'self' ws: wss:; img-src 'self' data: blob:; media-src 'self' blob:;"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response


app = FastAPI()

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],         
    allow_credentials=True,       
    allow_methods=["*"],         
    allow_headers=["*"]          
)

app.mount(
    "/static", 
    StaticFiles(directory=os.path.join(BASE_DIR, "static")), 
    name="static"
)

app.mount("/files", StaticFiles(directory=UPLOAD_DIR), name="files")

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))