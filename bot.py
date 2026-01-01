import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import requests
from deep_translator import GoogleTranslator

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# API ключи из переменных окружения
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8305087339:AAGHOIGKPC9DjAkxfEQEIsXblXOE0xG0IDU')
OMDB_API_KEY = os.environ.get('OMDB_API_KEY', 'd6e8cba2')

# Функция для определения языка и перевода
def translate_to_english(text):
    try:
        # Проверяем, есть ли русские буквы
        if any('\u0400' <= char <= '\u04FF' for char in text):
            translated = GoogleTranslator(source='ru', target='en').translate(text)
            logger.info(f"Перевод: '{text}' -> '{translated}'")
            return translated
        return text
    except Exception as e:
        logger.error(f"Ошибка перевода: {e}")
        return text

# Функция для поиска фильма
def search_movie(title):
    # Переводим название на английский если нужно
    english_title = translate_to_english(title)
    url = f'http://www.omdbapi.com/?t={english_title}&apikey={OMDB_API_KEY}'
    try:
        response = requests.get(url)
        data = response.json()
        if data.get('Response') == 'True':
            return data
        return None
    except Exception as e:
        logger.error(f"Ошибка при запросе к API: {e}")
        return None

# Функция для поиска списка фильмов
def search_movies_list(query):
    # Переводим запрос на английский если нужно
    english_query = translate_to_english(query)
    url = f'http://www.omdbapi.com/?s={english_query}&apikey={OMDB_API_KEY}'
    try:
        response = requests.get(url)
        data = response.json()
        if data.get('Response') == 'True':
            return data.get('Search', [])
        return []
    except Exception as e:
        logger.error(f"Ошибка при запросе к API: {e}")
        return []

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '🎬 Привет! Я бот для поиска информации о фильмах.\n\n'
        'Просто отправь мне название фильма на русском или английском, и я найду информацию о нём!\n\n'
        'Команды:\n'
        '/start - показать это сообщение\n'
        '/help - помощь'
    )

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '📖 Как пользоваться:\n\n'
        '1. Отправьте название фильма на русском или английском\n'
        '2. Если найдено несколько фильмов, выберите нужный из списка\n'
        '3. Получите полную информацию о фильме\n\n'
        'Примеры:\n'
        '• Inception\n'
        '• Матрица\n'
        '• Начало\n'
        '• Interstellar\n'
        '• Интерстеллар'
    )

# Форматирование информации о фильме
def format_movie_info(movie):
    info = f"🎬 <b>{movie.get('Title', 'N/A')}</b> ({movie.get('Year', 'N/A')})\n\n"
    
    if movie.get('Plot') != 'N/A':
        info += f"📝 <b>Описание:</b>\n{movie.get('Plot')}\n\n"
    
    info += f"⭐ <b>Рейтинг:</b> {movie.get('imdbRating', 'N/A')}/10\n"
    info += f"🎭 <b>Жанр:</b> {movie.get('Genre', 'N/A')}\n"
    info += f"🎬 <b>Режиссёр:</b> {movie.get('Director', 'N/A')}\n"
    info += f"🎭 <b>Актёры:</b> {movie.get('Actors', 'N/A')}\n"
    info += f"⏱ <b>Длительность:</b> {movie.get('Runtime', 'N/A')}\n"
    info += f"🌍 <b>Страна:</b> {movie.get('Country', 'N/A')}\n"
    info += f"🗣 <b>Язык:</b> {movie.get('Language', 'N/A')}\n"
    
    if movie.get('Awards') != 'N/A':
        info += f"🏆 <b>Награды:</b> {movie.get('Awards')}\n"
    
    if movie.get('BoxOffice') != 'N/A':
        info += f"💰 <b>Кассовые сборы:</b> {movie.get('BoxOffice')}\n"
    
    return info

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    
    # Показываем разные сообщения в зависимости от языка
    if any('\u0400' <= char <= '\u04FF' for char in query):
        await update.message.reply_text('🔍 Ищу фильм... (перевожу на английский)')
    else:
        await update.message.reply_text('🔍 Ищу фильм...')
    
    # Сначала пробуем точный поиск
    movie = search_movie(query)
    
    if movie:
        # Нашли точное совпадение
        poster_url = movie.get('Poster')
        info = format_movie_info(movie)
        
        if poster_url and poster_url != 'N/A':
            await update.message.reply_photo(
                photo=poster_url,
                caption=info,
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(info, parse_mode='HTML')
    else:
        # Ищем список фильмов
        movies = search_movies_list(query)
        
        if movies:
            keyboard = []
            for movie in movies[:10]:  # Показываем первые 10 результатов
                button_text = f"{movie.get('Title')} ({movie.get('Year')})"
                callback_data = f"movie_{movie.get('imdbID')}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                '🎬 Найдено несколько фильмов. Выберите нужный:',
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                '😔 К сожалению, фильм не найден.\n'
                'Попробуйте изменить запрос или проверить правильность названия.'
            )

# Обработка нажатий на кнопки
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    imdb_id = query.data.replace('movie_', '')
    
    # Получаем информацию по IMDb ID
    url = f'http://www.omdbapi.com/?i={imdb_id}&apikey={OMDB_API_KEY}'
    try:
        response = requests.get(url)
        movie = response.json()
        
        if movie.get('Response') == 'True':
            poster_url = movie.get('Poster')
            info = format_movie_info(movie)
            
            if poster_url and poster_url != 'N/A':
                await query.message.reply_photo(
                    photo=poster_url,
                    caption=info,
                    parse_mode='HTML'
                )
            else:
                await query.message.reply_text(info, parse_mode='HTML')
        else:
            await query.message.reply_text('Ошибка при получении информации о фильме.')
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await query.message.reply_text('Произошла ошибка. Попробуйте позже.')

# Главная функция
def main():
    # Создаём приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Запускаем бота
    logger.info("Бот запущен с поддержкой русского языка!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()