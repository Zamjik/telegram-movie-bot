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
KINOPOISK_API_KEY = os.environ.get('KINOPOISK_API_KEY', '3efe014f-4341-40be-961a-043dadad865e')
KINOPOISK_API_URL = 'https://kinopoiskapiunofficial.tech/api'

# Функция для поиска фильмов по названию
def search_movies_list(query):
    url = f'{KINOPOISK_API_URL}/v2.1/films/search-by-keyword'
    headers = {
        'X-API-KEY': KINOPOISK_API_KEY,
        'Content-Type': 'application/json',
    }
    params = {
        'keyword': query,
        'page': 1
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        if data.get('films'):
            return data['films']
        return []
    except Exception as e:
        logger.error(f"Ошибка при запросе к API: {e}")
        return []

# Функция для получения полной информации о фильме
def get_movie_by_id(film_id):
    url = f'{KINOPOISK_API_URL}/v2.2/films/{film_id}'
    headers = {
        'X-API-KEY': KINOPOISK_API_KEY,
        'Content-Type': 'application/json',
    }
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        return data
    except Exception as e:
        logger.error(f"Ошибка при запросе к API: {e}")
        return None

# Функция для получения трейлеров
def get_movie_videos(film_id):
    url = f'{KINOPOISK_API_URL}/v2.2/films/{film_id}/videos'
    headers = {
        'X-API-KEY': KINOPOISK_API_KEY,
        'Content-Type': 'application/json',
    }
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        # Ищем трейлер
        trailers = [item for item in data.get('items', []) if item.get('site') == 'YOUTUBE']
        if trailers:
            return trailers[0].get('url')
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении трейлеров: {e}")
        return None

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '🎬 Привет! Я бот для поиска информации о фильмах и сериалах.\n\n'
        'Просто отправь мне название фильма на русском или английском, и я найду информацию о нём с Кинопоиска!\n\n'
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
        '3. Получите полную информацию с Кинопоиска\n\n'
        'Примеры:\n'
        '• Матрица\n'
        '• Начало\n'
        '• Интерстеллар\n'
        '• Брат\n'
        '• Во все тяжкие\n'
        '• Игра престолов'
    )

# Форматирование информации о фильме
def format_movie_info(movie):
    # Название
    name_ru = movie.get('nameRu') or movie.get('nameOriginal') or 'N/A'
    name_en = movie.get('nameOriginal') or movie.get('nameEn')
    year = movie.get('year', 'N/A')
    
    info = f"🎬 <b>{name_ru}</b> ({year})\n"
    
    # Оригинальное название
    if name_en and name_en != name_ru:
        info += f"🔤 <i>{name_en}</i>\n"
    
    info += "\n"
    
    # ID фильмов
    kinopoisk_id = movie.get('kinopoiskId')
    imdb_id = movie.get('imdbId')
    
    if kinopoisk_id or imdb_id:
        info += "🆔 <b>Идентификаторы:</b>\n"
        if kinopoisk_id:
            info += f"  • Kinopoisk ID: <code>{kinopoisk_id}</code>\n"
        if imdb_id:
            info += f"  • IMDb ID: <code>{imdb_id}</code>\n"
        info += "\n"
    
    # Описание
    description = movie.get('description')
    if description:
        info += f"📝 <b>Описание:</b>\n{description}\n\n"
    
    # Рейтинги
    rating_kp = movie.get('ratingKinopoisk')
    rating_imdb = movie.get('ratingImdb')
    if rating_kp:
        info += f"⭐ <b>Кинопоиск:</b> {rating_kp}/10\n"
    if rating_imdb:
        info += f"⭐ <b>IMDb:</b> {rating_imdb}/10\n"
    
    # Жанры
    genres = movie.get('genres', [])
    if genres:
        genre_names = ', '.join([g.get('genre', '') for g in genres if g.get('genre')])
        if genre_names:
            info += f"🎭 <b>Жанр:</b> {genre_names}\n"
    
    # Страны
    countries = movie.get('countries', [])
    if countries:
        country_names = ', '.join([c.get('country', '') for c in countries if c.get('country')])
        if country_names:
            info += f"🌍 <b>Страна:</b> {country_names}\n"
    
    # Длительность
    film_length = movie.get('filmLength')
    if film_length:
        info += f"⏱ <b>Длительность:</b> {film_length} мин\n"
    
    # Возрастной рейтинг
    age_limit = movie.get('ratingAgeLimits')
    if age_limit:
        age = age_limit.replace('age', '')
        info += f"🔞 <b>Возраст:</b> {age}+\n"
    
    # Слоган
    slogan = movie.get('slogan')
    if slogan:
        info += f"\n💬 <i>«{slogan}»</i>\n"
    
    # Ссылка на Кинопоиск
    web_url = movie.get('webUrl')
    if web_url:
        info += f"\n🔗 <a href='{web_url}'>Смотреть на Кинопоиске</a>"
    
    return info

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    search_msg = await update.message.reply_text('🔍 Ищу на Кинопоиске...')
    
    # Ищем список фильмов
    movies = search_movies_list(query)
    
    if len(movies) == 0:
        await search_msg.edit_text(
            '😔 К сожалению, ничего не найдено.\n'
            'Попробуйте изменить запрос или проверить правильность названия.'
        )
    elif len(movies) == 1:
        # Нашли один фильм - показываем сразу полную информацию
        film_id = movies[0].get('filmId')
        movie = get_movie_by_id(film_id)
        
        if movie:
            poster_url = movie.get('posterUrl')
            info = format_movie_info(movie)
            
            # Получаем трейлер
            trailer_url = get_movie_videos(film_id)
            
            # Создаем кнопку трейлера если есть
            reply_markup = None
            if trailer_url:
                keyboard = [[InlineKeyboardButton("🎬 Смотреть трейлер", url=trailer_url)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Удаляем сообщение о поиске
            await search_msg.delete()
            
            if poster_url:
                try:
                    await update.message.reply_photo(
                        photo=poster_url,
                        caption=info,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
                except:
                    await update.message.reply_text(info, parse_mode='HTML', reply_markup=reply_markup)
            else:
                await update.message.reply_text(info, parse_mode='HTML', reply_markup=reply_markup)
    else:
        # Нашли несколько - показываем список
        keyboard = []
        for movie in movies[:10]:
            name_ru = movie.get('nameRu') or movie.get('nameEn') or 'Неизвестно'
            year = movie.get('year', '')
            film_id = movie.get('filmId')
            
            button_text = f"{name_ru} ({year})" if year else name_ru
            callback_data = f"movie_{film_id}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await search_msg.edit_text(
            '🎬 Найдено несколько фильмов. Выберите нужный:',
            reply_markup=reply_markup
        )

# Обработка нажатий на кнопки
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    film_id = query.data.replace('movie_', '')
    
    # Получаем полную информацию о фильме
    movie = get_movie_by_id(film_id)
    
    if movie:
        poster_url = movie.get('posterUrl')
        info = format_movie_info(movie)
        
        # Получаем трейлер
        trailer_url = get_movie_videos(film_id)
        
        # Создаем кнопку трейлера если есть
        reply_markup = None
        if trailer_url:
            keyboard = [[InlineKeyboardButton("🎬 Смотреть трейлер", url=trailer_url)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Удаляем сообщение со списком фильмов
        try:
            await query.message.delete()
        except Exception as e:
            logger.error(f"Не удалось удалить сообщение: {e}")
        
        if poster_url:
            try:
                await query.message.reply_photo(
                    photo=poster_url,
                    caption=info,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
            except:
                await query.message.reply_text(info, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await query.message.reply_text(info, parse_mode='HTML', reply_markup=reply_markup)
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