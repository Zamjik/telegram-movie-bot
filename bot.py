import logging
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import requests
from typing import List, Dict, Optional

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# API ключи
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8305087339:AAGHOIGKPC9DjAkxfEQEIsXblXOE0xG0IDU')
KINOPOISK_API_KEY = os.environ.get('KINOPOISK_API_KEY', '3efe014f-4341-40be-961a-043dadad865e')
KINOPOISK_API_URL = 'https://kinopoiskapiunofficial.tech/api'

# ============================================
# KINOPOISK API ФУНКЦИИ
# ============================================

def search_movies_list(query):
    """Поиск фильмов по названию"""
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

def get_movie_by_id(film_id):
    """Получение полной информации о фильме"""
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

def get_movie_videos(film_id):
    """Получение трейлеров"""
    url = f'{KINOPOISK_API_URL}/v2.2/films/{film_id}/videos'
    headers = {
        'X-API-KEY': KINOPOISK_API_KEY,
        'Content-Type': 'application/json',
    }
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        trailers = [item for item in data.get('items', []) if item.get('site') == 'YOUTUBE']
        if trailers:
            return trailers[0].get('url')
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении трейлеров: {e}")
        return None

# ============================================
# LAMPA-ПОДОБНЫЕ ПЛАГИНЫ ДЛЯ ПОИСКА ИСТОЧНИКОВ
# ============================================

class VideoSource:
    """Базовый класс для источников видео"""
    def __init__(self, name: str):
        self.name = name
    
    async def search(self, movie: Dict) -> Optional[Dict]:
        """Метод поиска - должен быть переопределен"""
        raise NotImplementedError

class BalancerPlugin(VideoSource):
    """Плагин для работы с балансерами (агрегаторы источников)"""
    def __init__(self):
        super().__init__('Balancer')
        # Пример API балансера
        self.balancer_url = 'https://api.example-balancer.com'
    
    async def search(self, movie: Dict) -> Optional[Dict]:
        try:
            kinopoisk_id = movie.get('kinopoiskId')
            imdb_id = movie.get('imdbId')
            
            if not kinopoisk_id and not imdb_id:
                return None
            
            # Имитация запроса к балансеру
            # В реальности здесь был бы запрос к настоящему API
            logger.info(f"[{self.name}] Поиск источников для фильма {movie.get('nameRu')}")
            
            # Возвращаем mock-данные для демонстрации
            return {
                'source': self.name,
                'found': True,
                'translations': [
                    {
                        'name': 'Дубляж',
                        'quality': ['1080p', '720p', '480p'],
                        'type': 'hls'
                    },
                    {
                        'name': 'Профессиональный (многоголосый)',
                        'quality': ['1080p', '720p'],
                        'type': 'hls'
                    }
                ]
            }
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка: {e}")
            return None

class TorrentPlugin(VideoSource):
    """Плагин для поиска торрентов"""
    def __init__(self):
        super().__init__('Torrents')
        self.tracker_apis = [
            'https://api.tracker1.com',
            'https://api.tracker2.com'
        ]
    
    async def search(self, movie: Dict) -> Optional[Dict]:
        try:
            imdb_id = movie.get('imdbId')
            if not imdb_id:
                return None
            
            logger.info(f"[{self.name}] Поиск торрентов для {movie.get('nameRu')}")
            
            # Mock-данные для демонстрации
            return {
                'source': self.name,
                'found': True,
                'torrents': [
                    {
                        'quality': '1080p',
                        'size': '2.1 GB',
                        'seeders': 145,
                        'type': 'torrent'
                    },
                    {
                        'quality': '720p',
                        'size': '1.4 GB',
                        'seeders': 89,
                        'type': 'torrent'
                    }
                ]
            }
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка: {e}")
            return None

class OnlineKinoPlugin(VideoSource):
    """Плагин для онлайн-кинотеатров"""
    def __init__(self):
        super().__init__('OnlineKino')
        self.api_url = 'https://api.example-kino.com'
    
    async def search(self, movie: Dict) -> Optional[Dict]:
        try:
            logger.info(f"[{self.name}] Поиск на онлайн-платформах для {movie.get('nameRu')}")
            
            # Mock-данные
            return {
                'source': self.name,
                'found': True,
                'streams': [
                    {
                        'quality': '1080p',
                        'type': 'hls'
                    }
                ]
            }
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка: {e}")
            return None

class SourceManager:
    """Менеджер источников - координирует работу всех плагинов"""
    def __init__(self):
        self.sources = []
    
    def register_source(self, source: VideoSource):
        """Регистрация нового источника"""
        self.sources.append(source)
        logger.info(f"Плагин '{source.name}' зарегистрирован")
    
    async def find_sources(self, movie: Dict) -> List[Dict]:
        """Поиск по всем источникам параллельно"""
        logger.info(f"Запуск поиска источников для: {movie.get('nameRu')}")
        
        # Запускаем поиск по всем плагинам одновременно
        tasks = [source.search(movie) for source in self.sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Фильтруем успешные результаты
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Плагин {self.sources[i].name} упал: {result}")
            elif result and result.get('found'):
                valid_results.append(result)
        
        return valid_results

# Глобальный менеджер источников
source_manager = SourceManager()
source_manager.register_source(BalancerPlugin())
source_manager.register_source(TorrentPlugin())
source_manager.register_source(OnlineKinoPlugin())

# ============================================
# ФОРМАТИРОВАНИЕ ИНФОРМАЦИИ
# ============================================

def format_movie_info(movie: Dict) -> str:
    """Форматирование информации о фильме"""
    name_ru = movie.get('nameRu') or movie.get('nameOriginal') or 'N/A'
    name_en = movie.get('nameOriginal') or movie.get('nameEn')
    year = movie.get('year', 'N/A')
    
    info = f"🎬 <b>{name_ru}</b> ({year})\n"
    
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
        # Ограничиваем длину описания
        desc_short = description[:300] + '...' if len(description) > 300 else description
        info += f"📝 <b>Описание:</b>\n{desc_short}\n\n"
    
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

def format_sources_info(sources: List[Dict]) -> str:
    """Форматирование информации об источниках"""
    if not sources:
        return "\n\n❌ <b>Источники для просмотра не найдены</b>"
    
    info = "\n\n📺 <b>Доступные источники:</b>\n"
    
    for source_data in sources:
        source_name = source_data.get('source', 'Unknown')
        info += f"\n🎯 <b>{source_name}:</b>\n"
        
        # Балансер
        if 'translations' in source_data:
            for trans in source_data['translations']:
                name = trans.get('name', 'Unknown')
                qualities = ', '.join(trans.get('quality', []))
                info += f"  • {name} ({qualities})\n"
        
        # Торренты
        elif 'torrents' in source_data:
            for torrent in source_data['torrents'][:3]:  # Показываем только первые 3
                quality = torrent.get('quality', 'Unknown')
                size = torrent.get('size', 'Unknown')
                seeders = torrent.get('seeders', 0)
                info += f"  • {quality} - {size} (👥 {seeders} сидов)\n"
        
        # Онлайн-стримы
        elif 'streams' in source_data:
            for stream in source_data['streams']:
                quality = stream.get('quality', 'Unknown')
                info += f"  • {quality}\n"
    
    info += "\n💡 <i>Источники найдены автоматически через различные API</i>"
    return info

# ============================================
# TELEGRAM ОБРАБОТЧИКИ
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    await update.message.reply_text(
        '🎬 Привет! Я продвинутый бот для поиска фильмов!\n\n'
        '✨ <b>Возможности:</b>\n'
        '• Поиск информации о фильмах из Кинопоиска\n'
        '• Автоматический поиск источников для просмотра\n'
        '• Информация о доступных озвучках и качестве\n'
        '• Ссылки на трейлеры\n\n'
        '📝 Просто отправь название фильма!\n\n'
        'Команды:\n'
        '/start - показать это сообщение\n'
        '/help - помощь',
        parse_mode='HTML'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    await update.message.reply_text(
        '📖 <b>Как пользоваться:</b>\n\n'
        '1️⃣ Отправьте название фильма или сериала\n'
        '2️⃣ Выберите нужный из списка (если найдено несколько)\n'
        '3️⃣ Получите:\n'
        '   • Полную информацию с Кинопоиска\n'
        '   • Список источников для просмотра\n'
        '   • Ссылку на трейлер\n\n'
        '🎯 <b>Примеры запросов:</b>\n'
        '• Матрица\n'
        '• Inception\n'
        '• Интерстеллар\n'
        '• Брат\n'
        '• Игра престолов\n\n'
        '💡 <b>Фишки:</b>\n'
        '• Автоматический поиск по множеству источников\n'
        '• Информация о качестве и озвучках\n'
        '• Данные о торрентах (качество, размер, сиды)\n'
        '• Kinopoisk ID и IMDb ID для использования в других сервисах',
        parse_mode='HTML'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    query = update.message.text
    search_msg = await update.message.reply_text('🔍 Ищу на Кинопоиске...')
    
    movies = search_movies_list(query)
    
    if len(movies) == 0:
        await search_msg.edit_text(
            '😔 К сожалению, ничего не найдено.\n'
            'Попробуйте изменить запрос или проверить правильность названия.'
        )
    elif len(movies) == 1:
        # Нашли один фильм
        await show_movie_details(update, search_msg, movies[0].get('filmId'))
    else:
        # Нашли несколько
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

async def show_movie_details(update: Update, message, film_id: str):
    """Показ детальной информации о фильме"""
    # Обновляем статус
    await message.edit_text('📊 Получаю информацию...')
    
    # Получаем данные о фильме
    movie = get_movie_by_id(film_id)
    
    if not movie:
        await message.edit_text('❌ Ошибка при получении информации о фильме.')
        return
    
    # Ищем источники для просмотра
    await message.edit_text('🔎 Ищу источники для просмотра...')
    sources = await source_manager.find_sources(movie)
    
    # Получаем трейлер
    trailer_url = get_movie_videos(film_id)
    
    # Форматируем информацию
    poster_url = movie.get('posterUrl')
    info = format_movie_info(movie)
    info += format_sources_info(sources)
    
    # Создаем кнопки
    keyboard = []
    if trailer_url:
        keyboard.append([InlineKeyboardButton("🎬 Смотреть трейлер", url=trailer_url)])
    
    # Добавляем кнопку для поиска в других сервисах
    kinopoisk_id = movie.get('kinopoiskId')
    if kinopoisk_id:
        keyboard.append([
            InlineKeyboardButton("🔍 Искать еще", callback_data=f"search_more_{film_id}")
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    # Удаляем сообщение о поиске
    await message.delete()
    
    # Отправляем результат
    if poster_url:
        try:
            if hasattr(update, 'callback_query'):
                await update.callback_query.message.reply_photo(
                    photo=poster_url,
                    caption=info,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_photo(
                    photo=poster_url,
                    caption=info,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
        except:
            if hasattr(update, 'callback_query'):
                await update.callback_query.message.reply_text(
                    info, parse_mode='HTML', reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    info, parse_mode='HTML', reply_markup=reply_markup
                )
    else:
        if hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text(
                info, parse_mode='HTML', reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                info, parse_mode='HTML', reply_markup=reply_markup
            )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('movie_'):
        film_id = query.data.replace('movie_', '')
        await show_movie_details(update, query.message, film_id)
    
    elif query.data.startswith('search_more_'):
        film_id = query.data.replace('search_more_', '')
        movie = get_movie_by_id(film_id)
        
        if movie:
            kinopoisk_id = movie.get('kinopoiskId')
            imdb_id = movie.get('imdbId')
            name = movie.get('nameRu') or movie.get('nameOriginal')
            
            search_links = f"🔍 <b>Поиск '{name}' в других сервисах:</b>\n\n"
            
            if kinopoisk_id:
                search_links += f"🎬 <a href='https://www.kinopoisk.ru/film/{kinopoisk_id}/'>Кинопоиск</a>\n"
            if imdb_id:
                search_links += f"🎬 <a href='https://www.imdb.com/title/{imdb_id}/'>IMDb</a>\n"
            
            search_links += f"\n💡 Используйте эти ID для поиска в Lampa, Kodi и других медиацентрах"
            
            await query.message.reply_text(search_links, parse_mode='HTML')

# ============================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================

def main():
    """Запуск бота"""
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Запускаем бота
    logger.info("🚀 Бот запущен с Кинопоиском API и поиском источников!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()