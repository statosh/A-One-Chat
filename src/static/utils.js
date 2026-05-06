const $ = id => document.getElementById(id);

/**
 * Экранирует HTML-символы и удаляет потенциально опасные javascript: ссылки
 * 
 * Входы:
 *     t (string): Текст для экранирования
 * 
 * Выходы:
 *     string: Экранированный текст без HTML-тегов и javascript: ссылок
 */
function escapeHtml(t) {
    if (!t) return '';
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#x27;',
        '/': '&#x2F;',
        '`': '&#x60;',
        '=': '&#x3D;'
    };

    return String(t).replace(/[&<>"'`=\/]/g, function(s) {
        return map[s];
    }).replace(/javascript:/gi, '');
}

/**
 * Очищает пользовательский ввод от потенциально опасного JavaScript кода
 * 
 * Входы:
 *     text (string): Исходный текст для очистки
 * 
 * Выходы:
 *     string: Очищенный текст без javascript:, обработчиков событий и script-тегов
 */
function sanitizeUserInput(text) {
    if (!text) return '';
    return text.replace(/javascript:/gi, '')
        .replace(/on\w+=/gi, '')
        .replace(/<script[^>]*>/gi, '');
}

/**
 * Форматирует временную метку в читаемый формат "день месяц часы:минуты"
 * 
 * Входы:
 *     ts (string|Date): Временная метка в формате ISO или объект Date
 * 
 * Выходы:
 *     string: Отформатированная дата и время (например, "15 января 14:30")
 */
function formatTime(ts) {
    const d = new Date(ts);
    const months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
    return `${d.getDate()} ${months[d.getMonth()]} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/**
 * Открывает или закрывает модальное окно
 * 
 * Входы:
 *     id (string): ID элемента модального окна
 *     show (boolean): true - показать окно, false - скрыть
 * 
 * Выходы: отсутствуют (изменяет CSS свойство display элементов)
 */
function toggleModal(id, show) {
    $(id).style.display = show ? 'block' : 'none';
    $('modal-overlay').style.display = show ? 'block' : 'none';
}

/**
 * Инициализирует палитру цветов с предустановленными вариантами
 * 
 * Входы:
 *     id (string): ID контейнера для палитры цветов
 *     color (string): Выбранный цвет в формате HEX (например, '#007bff')
 * 
 * Выходы: отсутствует (создает DOM-элементы цветов и устанавливает обработчики)
 */
function initColorPicker(id, color) {
    const p = $(id);
    const colors = ['#007bff', '#28a745', '#dc3545', '#ffc107', '#17a2b8', '#6f42c1', '#fd7e14', '#20c997'];

    if (!p.querySelector('.color-option')) {
        p.innerHTML = colors.map(c =>
            `<div class="color-option${c === color ? ' selected' : ''}" data-color="${c}" style="background-color:${c}"></div>`
        ).join('');
    }

    p.querySelectorAll('.color-option').forEach(o => o.classList.remove('selected'));
    const s = p.querySelector(`[data-color="${color}"]`);
    if (s) s.classList.add('selected');

    p.querySelectorAll('.color-option').forEach(o => o.onclick = () => {
        p.querySelectorAll('.color-option').forEach(x => x.classList.remove('selected'));
        o.classList.add('selected');
    });
}

/**
 * Получает выбранный цвет из палитры
 * 
 * Входы:
 *     id (string): ID контейнера с палитрой цветов
 * 
 * Выходы:
 *     string: Выбранный цвет в формате HEX (по умолчанию '#007bff')
 */
function getColor(id) {
    const s = $(id).querySelector('.color-option.selected');
    return s ? s.dataset.color : '#007bff';
}

/**
 * Обрезает длинное имя файла до 30 символов, сохраняя расширение
 * 
 * Входы:
 *     fullName (string): Полное имя файла с расширением
 * 
 * Выходы:
 *     string: Обрезанное имя файла с троеточием или оригинальное имя, если оно короткое
 * 
 * Пример:
 *     "очень_длинное_имя_файла_которое_нужно_обрезать.txt" -> "очень_длинное_имя_фай...зать.txt"
 */
function truncateFileName(fullName) {
    if (!fullName || fullName.length <= 30) return escapeHtml(fullName);

    const dotIndex = fullName.lastIndexOf('.');

    if (dotIndex > 0) {
        const name = fullName.substring(0, dotIndex);
        const ext = fullName.substring(dotIndex);
        const maxNameLength = 27 - ext.length;
        if (maxNameLength > 0) {
            return escapeHtml(name.substring(0, maxNameLength) + '...' + ext);
        }
    }

    return escapeHtml(fullName.substring(0, 27) + '...');
}