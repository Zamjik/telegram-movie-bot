import logging
import os
import asyncio
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import requests
from typing import List, Dict, Optional

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# API ключи
TELEGRAM_TOKEN = '8305087339:AAGHOIGKPC9DjAkxfEQEIsXblXOE0xG0IDU'
KINOPOISK_API_KEY = '3efe014f-4341-40be-961a-043dadad865e'
KINOPOISK_API_URL = 'https://kinopoiskapiunofficial.tech/api'
VIDEOCDN_TOKEN = os.environ.get('VIDEOCDN_TOKEN', '')

# ============================================
# KINOPOISK API
# ============================================

def search_movies_list(query: str) -> List[Dict]:
    """Поиск фильмов по названию"""
    url = f'{KINOPOISK_API_URL}/v2.1/films/search-by-keyword'
    headers = {
        'X-API-KEY': KINOPOISK_API_KEY,
        'Content-Type': 'application/json',
    }
    params = {'keyword': query, 'page': 1}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get('films', [])
    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")
        return []

def get_movie_by_id(film_id: int) -> Optional[Dict]:
    """Получение информации о фильме"""
    url = f'{KINOPOISK_API_URL}/v2.2/films/{film_id}'
    headers = {
        'X-API-KEY': KINOPOISK_API_KEY,
        'Content-Type': 'application/json',
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка получения фильма: {e}")
        return None

def get_movie_videos(film_id: int) -> Optional[str]:
    """Получение трейлеров"""
    url = f'{KINOPOISK_API_URL}/v2.2/films/{film_id}/videos'
    headers = {
        'X-API-KEY': KINOPOISK_API_KEY,
        'Content-Type': 'application/json',
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        trailers = [item for item in data.get('items', []) if item.get('site') == 'YOUTUBE']
        return trailers[0].get('url') if trailers else None
    except Exception as e:
        logger.error(f"Ошибка получения трейлера: {e}")
        return None

# ============================================
# ИСТОЧНИКИ ВИДЕО (балансеры)
# ============================================

class VideoSource:
    """Базовый класс для источников"""
    def __init__(self, name: str):
        self.name = name
    
    async def search(self, movie: Dict) -> Optional[Dict]:
        raise NotImplementedError

class CollapsBalancer(VideoSource):
    """Balancer Collaps - работает без токена"""
    def __init__(self):
        super().__init__('Collaps')
        self.base_url = 'https://api.bhcesh.me/list'
    
    async def search(self, movie: Dict) -> Optional[Dict]:
        try:
            kinopoisk_id = movie.get('kinopoiskId')
            if not kinopoisk_id:
                return None
            
            async with aiohttp.ClientSession() as session:
                params = {'kinopoisk_id': kinopoisk_id}
                async with session.get(
                    self.base_url, 
                    params=params, 
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    if not data.get('results'):
                        return None
                    
                    translations = []
                    for result in data['results'][:5]:
                        translations.append({
                            'name': result.get('translation', 'Озвучка'),
                            'quality': result.get('quality', 'HD'),
                            'url': result.get('iframe_url', '')
                        })
                    
                    return {
                        'source': self.name,
                        'found': True,
                        'translations': translations
                    }
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка: {e}")
            return None

class VideoCDNBalancer(VideoSource):
    """VideoCDN - работает если есть токен"""
    def __init__(self, api_token: str):
        super().__init__('VideoCDN')
        self.api_token = api_token
        self.base_url = 'https://videocdn.tv/api'
    
    async def search(self, movie: Dict) -> Optional[Dict]:
        if not self.api_token:
            return None
        
        try:
            kinopoisk_id = movie.get('kinopoiskId')
            if not kinopoisk_id:
                return None
            
            async with aiohttp.ClientSession() as session:
                params = {
                    'api_token': self.api_token,
                    'kinopoisk_id': kinopoisk_id
                }
                async with session.get(
                    f'{self.base_url}/short', 
                    params=params, 
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    if not data.get('data'):
                        return None
                    
                    result_data = data['data'][0]
                    
                    return {
                        'source': self.name,
                        'found': True,
                        'translations': [{
                            'name': 'VideoCDN',
                            'quality': result_data.get('quality', 'HD'),
                            'url': result_data.get('iframe_src', '')
                        }]
                    }
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка: {e}")
            return None

class KinoboxBalancer(VideoSource):
    """Kinobox - популярный балансер без токена"""
    def __init__(self):
        super().__init__('Kinobox')
        self.base_url = 'https://kinobox.tv/api'
    
    async def search(self, movie: Dict) -> Optional[Dict]:
        try:
            kinopoisk_id = movie.get('kinopoiskId')
            if not kinopoisk_id:
                return None
            
            async with aiohttp.ClientSession() as session:
                params = {'kinopoisk': kinopoisk_id}
                async with session.get(
                    f'{self.base_url}/videos', 
                    params=params, 
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    if not data:
                        return None
                    
                    return {
                        'source': self.name,
                        'found': True,
                        'translations': [{
                            'name': 'Kinobox',
                            'quality': 'HD',
                            'url': ''
                        }]
                    }
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка: {e}")
            return None

class SourceManager:
    """Менеджер источников"""
    def __init__(self):
        self.sources: List[VideoSource] = []
    
    def register_source(self, source: VideoSource):
        self.sources.append(source)
        logger.info(f"✅ Плагин '{source.name}' зарегистрирован")
    
    async def find_sources(self, movie: Dict) -> List[Dict]:
        logger.info(f"🔍 Поиск источников для: {movie.get('nameRu')}")
        
        tasks = [source.search(movie) for source in self.sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"❌ {self.sources[i].name} ошибка: {result}")
            elif result and result.get('found'):
                logger.info(f"✅ {self.sources[i].name} - источники найдены")
                valid_results.append(result)
            else:
                logger.info(f"ℹ️ {self.sources[i].name} - ничего не найдено")
        
        return valid_results

# Создаем менеджер и регистрируем источники
source_manager = SourceManager()
source_manager.register_source(CollapsBalancer())
source_manager.register_source(VideoCDNBalancer(VIDEOCDN_TOKEN))
source_manager.register_source(KinoboxBalancer())

# ============================================
# ФОРМАТИРОВАНИЕ
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
    
    # Описание
    description = movie.get('description')
    if description:
        desc_short = description[:250] + '...' if len(description) > 250 else description
        info += f"📝 {desc_short}\n\n"
    
    # Рейтинги
    rating_kp = movie.get('ratingKinopoisk')
    rating_imdb = movie.get('ratingImdb')
    if rating_kp:
        info += f"⭐ Кинопоиск: {rating_kp}/10\n"
    if rating_imdb:
        info += f"⭐ IMDb: {rating_imdb}/10\n"
    
    # Жанры
    genres = movie.get('genres', [])
    if genres:
        genre_names = ', '.join([g.get('genre', '') for g in genres if g.get('genre')])
        if genre_names:
            info += f"🎭 Жанр: {genre_names}\n"
    
    # Страны
    countries = movie.get('countries', [])
    if countries:
        country_names = ', '.join([c.get('country', '') for c in countries if c.get('country')])
        if country_names:
            info += f"🌍 Страна: {country_names}\n"
    
    # Длительность
    film_length = movie.get('filmLength')
    if film_length:
        info += f"⏱ Длительность: {film_length} мин\n"
    
    # Возраст
    age_limit = movie.get('ratingAgeLimits')
    if age_limit:
        age = age_limit.replace('age', '')
        info += f"🔞 Возраст: {age}+\n"
    
    # ID (перемещены вниз, перед источниками)
    kinopoisk_id = movie.get('kinopoiskId')
    imdb_id = movie.get('imdbId')
    
    if kinopoisk_id or imdb_id:
        info += "\n🆔 <b>ID:</b>\n"
        if kinopoisk_id:
            info += f"  • Kinopoisk: <code>{kinopoisk_id}</code>\n"
        if imdb_id:
            info += f"  • IMDb: <code>{imdb_id}</code>\n"
    
    # Ссылка на Кинопоиск
    web_url = movie.get('webUrl')
    if web_url:
        info += f"\n🔗 <a href='{web_url}'>Кинопоиск</a>"
    
    return info

def format_sources_info(sources: List[Dict]) -> str:
    """Форматирование источников"""
    if not sources:
        return "\n\n❌ <b>Источники не найдены</b>\n" \
               "💡 <i>Попробуйте другой фильм</i>"
    
    info = "\n\n📺 <b>Доступные источники:</b>\n"
    
    for source_data in sources:
        source_name = source_data.get('source', 'Unknown')
        info += f"\n🎯 <b>{source_name}:</b>\n"
        
        if 'translations' in source_data:
            for trans in source_data['translations'][:5]:
                name = trans.get('name', 'Unknown')
                quality = trans.get('quality', '')
                info += f"  • {name}"
                if quality:
                    info += f" ({quality})"
                info += "\n"
    
    info += "\n💡 <i>Используй Kinopoisk ID в Lampa для просмотра</i>"
    return info

# ============================================
# TELEGRAM ОБРАБОТЧИКИ
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '🎬 <b>Привет! Я бот для поиска фильмов!</b>\n\n'
        '✨ <b>Что я умею:</b>\n'
        '• 🔍 Поиск информации из Кинопоиска\n'
        '• 📺 Автоматический поиск источников\n'
        '• 🎥 Ссылки на трейлеры\n'
        '• 🆔 Показ Kinopoisk ID и IMDb ID\n\n'
        '📝 <b>Просто отправь название фильма!</b>\n\n'
        '💡 <b>Примеры:</b> Матрица, Начало, Интерстеллар\n\n'
        'Команды: /start, /help',
        parse_mode='HTML'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '📖 <b>Как пользоваться:</b>\n\n'
        '1️⃣ Отправь название фильма (русское или английское)\n'
        '2️⃣ Выбери нужный из списка\n'
        '3️⃣ Получи:\n'
        '   • Полную информацию с Кинопоиска\n'
        '   • Список доступных источников\n'
        '   • Ссылку на трейлер\n'
        '   • ID для использования в Lampa\n\n'
        '🎯 <b>Примеры запросов:</b>\n'
        '• Матрица\n'
        '• Inception\n'
        '• Интерстеллар\n'
        '• Брат\n'
        '• Игра престолов\n\n'
        '🔌 <b>Источники поиска:</b>\n'
        '• <b>Collaps</b> - балансер источников\n'
        '• <b>Kinobox</b> - онлайн-кинотеатр\n'
        '• <b>VideoCDN</b> - дополнительный балансер\n\n'
        '💡 <b>Как смотреть:</b>\n'
        'Используй Kinopoisk ID в приложениях:\n'
        '• Lampa (lampa.mx)\n'
        '• Kodi\n'
        '• Stremio\n'
        '• Plex/Jellyfin',
        parse_mode='HTML'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    search_msg = await update.message.reply_text('🔍 Ищу на Кинопоиске...')
    
    movies = search_movies_list(query)
    
    if not movies:
        await search_msg.edit_text(
            '😔 Ничего не найдено.\n'
            'Попробуй изменить запрос или проверить правильность названия.'
        )
    elif len(movies) == 1:
        await show_movie_details(update, search_msg, movies[0].get('filmId'))
    else:
        keyboard = []
        for movie in movies[:10]:
            name_ru = movie.get('nameRu') or movie.get('nameEn') or 'Неизвестно'
            year = movie.get('year', '')
            film_id = movie.get('filmId')
            
            button_text = f"{name_ru} ({year})" if year else name_ru
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"movie_{film_id}")])
        
        await search_msg.edit_text(
            '🎬 Найдено несколько фильмов. Выбери нужный:',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_movie_details(update: Update, message, film_id: str):
    await message.edit_text('📊 Получаю информацию...')
    
    movie = get_movie_by_id(film_id)
    if not movie:
        await message.edit_text('❌ Ошибка получения данных.')
        return
    
    await message.edit_text('🔎 Ищу источники для просмотра...')
    sources = await source_manager.find_sources(movie)
    
    trailer_url = get_movie_videos(film_id)
    
    poster_url = movie.get('posterUrl')
    info = format_movie_info(movie)
    info += format_sources_info(sources)
    
    # Создаем кнопки - только трейлер и IMDb
    keyboard = []
    
    # Кнопка трейлера
    if trailer_url:
        keyboard.append([InlineKeyboardButton("🎬 Трейлер на YouTube", url=trailer_url)])
    
    # Кнопка IMDb
    imdb_id = movie.get('imdbId')
    if imdb_id:
        keyboard.append([
            InlineKeyboardButton("🎬 IMDb", url=f"https://www.imdb.com/title/{imdb_id}/")
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    await message.delete()
    
    # Отправляем результат
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
    except Exception as e:
        logger.error(f"Ошибка отправки с фото: {e}")
        # Если не удалось отправить фото
        if hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text(
                info, 
                parse_mode='HTML', 
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                info, 
                parse_mode='HTML', 
                reply_markup=reply_markup
            )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('movie_'):
        film_id = query.data.replace('movie_', '')
        await show_movie_details(update, query.message, film_id)

# ============================================
# ЗАПУСК
# ============================================

def main():
    logger.info("="*60)
    logger.info("🚀 ЗАПУСК БОТА...")
    logger.info("="*60)
    logger.info(f"📡 Telegram Token: {'✅ Установлен' if TELEGRAM_TOKEN else '❌ Не найден'}")
    logger.info(f"🔑 Kinopoisk API Key: {'✅ Установлен' if KINOPOISK_API_KEY else '❌ Не найден'}")
    logger.info(f"🎬 VideoCDN Token: {'✅ Установлен' if VIDEOCDN_TOKEN else '⚠️ Опционально'}")
    logger.info("="*60)
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("📡 Активные источники:")
    for source in source_manager.sources:
        logger.info(f"   ✅ {source.name}")
    logger.info("="*60)
    logger.info("✨ БОТ ГОТОВ К РАБОТЕ!")
    logger.info("="*60)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()