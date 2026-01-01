import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import requests

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# API ключи
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8305087339:AAGHOIGKPC9DjAkxfEQEIsXblXOE0xG0IDU')
KINOPOISK_API_URL = 'https://api.kinopoisk.dev/v1.4'

# Функция для поиска фильма по названию
def search_movie(title):
    url = f'{KINOPOISK_API_URL}/movie/search'
    params = {
        'page': 1,
        'limit': 1,
        'query': title
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data.get('docs') and len(data['docs']) > 0:
            return data['docs'][0]
        return None
    except Exception as e:
        logger.error(f"Ошибка при запросе к API: {e}")
        return None

# Функция для поиска списка фильмов
def search_movies_list(query):
    url = f'{KINOPOISK_API_URL}/movie/search'
    params = {
        'page': 1,
        'limit': 10,
        'query': query
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data.get('docs'):
            return data['docs']
        return []
    except Exception as e:
        logger.error(f"Ошибка при запросе к API: {e}")
        return []

# Функция для получения фильма по ID
def get_movie_by_id(movie_id):
    url = f'{KINOPOISK_API_URL}/movie/{movie_id}'
    try:
        response = requests.get(url)
        data = response.json()
        return data
    except Exception as e:
        logger.error(f"Ошибка при запросе к API: {e}")
        return None

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '🎬 Привет! Я бот для поиска информации о фильмах и сериалах.\n\n'
        'Просто отправь мне название фильма на русском или английском, и я найду информацию о нём!\n\n'
        'Команды:\n'
        '/start - показать это сообщение\n'
        '/help - помощь'
    )

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '📖 Как пользоваться:\n\n'
        '1. Отправьте название фильма или сериала на русском или английском\n'
        '2. Если найдено несколько фильмов, выберите нужный из списка\n'
        '3. Получите полную информацию о фильме\n\n'
        'Примеры:\n'
        '• Матрица\n'
        '• Начало\n'
        '• Интерстеллар\n'
        '• Во все тяжкие\n'
        '• Игра престолов'
    )

# Форматирование информации о фильме
def format_movie_info(movie):
    # Название
    name = movie.get('name') or movie.get('alternativeName') or 'N/A'
    year = movie.get('year', 'N/A')
    
    info = f"🎬 <b>{name}</b> ({year})\n\n"
    
    # Альтернативное название
    alt_name = movie.get('alternativeName')
    if alt_name and alt_name != name:
        info += f"🔤 <b>Оригинальное название:</b> {alt_name}\n\n"
    
    # Описание
    description = movie.get('description') or movie.get('shortDescription')
    if description:
        info += f"📝 <b>Описание:</b>\n{description}\n\n"
    
    # Рейтинги
    rating_kp = movie.get('rating', {}).get('kp')
    rating_imdb = movie.get('rating', {}).get('imdb')
    if rating_kp:
        info += f"⭐ <b>Рейтинг Кинопоиск:</b> {rating_kp}/10\n"
    if rating_imdb:
        info += f"⭐ <b>Рейтинг IMDb:</b> {rating_imdb}/10\n"
    
    # Жанры
    genres = movie.get('genres', [])
    if genres:
        genre_names = ', '.join([g.get('name', '') for g in genres if g.get('name')])
        if genre_names:
            info += f"🎭 <b>Жанр:</b> {genre_names}\n"
    
    # Страны
    countries = movie.get('countries', [])
    if countries:
        country_names = ', '.join([c.get('name', '') for c in countries if c.get('name')])
        if country_names:
            info += f"🌍 <b>Страна:</b> {country_names}\n"
    
    # Длительность
    movie_length = movie.get('movieLength')
    if movie_length:
        info += f"⏱ <b>Длительность:</b> {movie_length} мин\n"
    
    # Возрастной рейтинг
    age_rating = movie.get('ageRating')
    if age_rating:
        info += f"🔞 <b>Возраст:</b> {age_rating}+\n"
    
    # Премьера
    premiere = movie.get('premiere', {}).get('world')
    if premiere:
        info += f"📅 <b>Премьера:</b> {premiere}\n"
    
    return info

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    await update.message.reply_text('🔍 Ищу фильм на Кинопоиске...')
    
    # Ищем список фильмов
    movies = search_movies_list(query)
    
    if len(movies) == 1:
        # Нашли один фильм - показываем сразу
        movie = movies[0]
        poster_url = movie.get('poster', {}).get('url')
        info = format_movie_info(movie)
        
        if poster_url:
            try:
                await update.message.reply_photo(
                    photo=poster_url,
                    caption=info,
                    parse_mode='HTML'
                )
            except:
                await update.message.reply_text(info, parse_mode='HTML')
        else:
            await update.message.reply_text(info, parse_mode='HTML')
    elif len(movies) > 1:
        # Нашли несколько - показываем список
        keyboard = []
        for movie in movies[:10]:
            name = movie.get('name') or movie.get('alternativeName') or 'Неизвестно'
            year = movie.get('year', '')
            movie_id = movie.get('id')
            
            button_text = f"{name} ({year})" if year else name
            callback_data = f"movie_{movie_id}"
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
    
    movie_id = query.data.replace('movie_', '')
    
    # Получаем полную информацию о фильме
    movie = get_movie_by_id(movie_id)
    
    if movie:
        poster_url = movie.get('poster', {}).get('url')
        info = format_movie_info(movie)
        
        if poster_url:
            try:
                await query.message.reply_photo(
                    photo=poster_url,
                    caption=info,
                    parse_mode='HTML'
                )
            except:
                await query.message.reply_text(info, parse_mode='HTML')
        else:
            await query.message.reply_text(info, parse_mode='HTML')
    else:
        await query.message.reply_text('Ошибка при получении информации о фильме.')

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
    logger.info("Бот запущен с Кинопоиском API!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()