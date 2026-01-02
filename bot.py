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
        response = requests.get(url, headers=headers, params=params, timeout=10)
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
        response = requests.get(url, headers=headers, timeout=10)
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
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        trailers = [item for item in data.get('items', []) if item.get('site') == 'YOUTUBE']
        if trailers:
            return trailers[0].get('url')
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении трейлеров: {e}")
        return None

# ============================================
# РЕАЛЬНЫЕ ПЛАГИНЫ ДЛЯ ПОИСКА ИСТОЧНИКОВ
# ============================================

class VideoSource:
    """Базовый класс для источников видео"""
    def __init__(self, name: str):
        self.name = name
    
    async def search(self, movie: Dict) -> Optional[Dict]:
        """Метод поиска - должен быть переопределен"""
        raise NotImplementedError

class VideoCDNBalancer(VideoSource):
    """
    Реальный балансер VideoCDN
    Один из самых популярных балансеров для русскоязычного контента
    """
    def __init__(self, api_token: str = None):
        super().__init__('VideoCDN')
        self.api_token = api_token or os.environ.get('VIDEOCDN_TOKEN', '')
        self.base_url = 'https://videocdn.tv/api'
    
    async def search(self, movie: Dict) -> Optional[Dict]:
        try:
            kinopoisk_id = movie.get('kinopoiskId')
            if not kinopoisk_id:
                return None
            
            logger.info(f"[{self.name}] Поиск для Kinopoisk ID: {kinopoisk_id}")
            
            async with aiohttp.ClientSession() as session:
                # Запрос к VideoCDN API
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
                        logger.warning(f"[{self.name}] Статус {response.status}")
                        return None
                    
                    data = await response.json()
                    
                    if not data.get('data') or len(data['data']) == 0:
                        return None
                    
                    result_data = data['data'][0]
                    
                    # Парсим доступные озвучки и качества
                    translations = []
                    
                    if result_data.get('translations'):
                        for trans in result_data['translations']:
                            translations.append({
                                'name': trans.get('title', 'Неизвестно'),
                                'quality': result_data.get('quality', 'HD'),
                                'iframe_url': result_data.get('iframe_src'),
                                'type': 'iframe'
                            })
                    
                    return {
                        'source': self.name,
                        'found': True,
                        'translations': translations if translations else [{
                            'name': 'По умолчанию',
                            'quality': 'HD',
                            'iframe_url': result_data.get('iframe_src'),
                            'type': 'iframe'
                        }]
                    }
        
        except asyncio.TimeoutError:
            logger.error(f"[{self.name}] Таймаут запроса")
            return None
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка: {e}")
            return None

class CollapsBalancer(VideoSource):
    """
    Реальный балансер Collaps
    Агрегирует множество источников
    """
    def __init__(self):
        super().__init__('Collaps')
        self.base_url = 'https://api.bhcesh.me/list'
    
    async def search(self, movie: Dict) -> Optional[Dict]:
        try:
            kinopoisk_id = movie.get('kinopoiskId')
            if not kinopoisk_id:
                return None
            
            logger.info(f"[{self.name}] Поиск для Kinopoisk ID: {kinopoisk_id}")
            
            async with aiohttp.ClientSession() as session:
                params = {
                    'kinopoisk_id': kinopoisk_id
                }
                
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
                    for result in data['results']:
                        translations.append({
                            'name': result.get('translation', 'Озвучка'),
                            'quality': result.get('quality', 'HD'),
                            'url': result.get('iframe_url'),
                            'type': 'iframe'
                        })
                    
                    return {
                        'source': self.name,
                        'found': True,
                        'translations': translations
                    }
        
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка: {e}")
            return None

class HDRezkaBalancer(VideoSource):
    """
    Балансер для HDRezka через API
    """
    def __init__(self):
        super().__init__('HDRezka')
        self.base_url = 'https://rezka.ag/api'
    
    async def search(self, movie: Dict) -> Optional[Dict]:
        try:
            # HDRezka использует поиск по названию
            title = movie.get('nameRu') or movie.get('nameOriginal')
            if not title:
                return None
            
            logger.info(f"[{self.name}] Поиск: {title}")
            
            async with aiohttp.ClientSession() as session:
                # Сначала ищем фильм
                async with session.post(
                    f'{self.base_url}/search',
                    json={'q': title},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    
                    if not data.get('results'):
                        return None
                    
                    # Берем первый результат
                    first_result = data['results'][0]
                    
                    return {
                        'source': self.name,
                        'found': True,
                        'translations': [{
                            'name': 'HDRezka',
                            'quality': 'HD',
                            'url': first_result.get('url'),
                            'type': 'web'
                        }]
                    }
        
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка: {e}")
            return None

class RuTrackerPlugin(VideoSource):
    """
    Поиск торрентов через RuTracker API
    """
    def __init__(self):
        super().__init__('RuTracker')
        self.base_url = 'https://rutracker.org/forum/api'
    
    async def search(self, movie: Dict) -> Optional[Dict]:
        try:
            title = movie.get('nameRu') or movie.get('nameOriginal')
            year = movie.get('year')
            
            if not title:
                return None
            
            search_query = f"{title} {year}" if year else title
            logger.info(f"[{self.name}] Поиск: {search_query}")
            
            async with aiohttp.ClientSession() as session:
                params = {
                    'nm': search_query,
                    'o': 10,  # сортировка по сидам
                    'c': 1,   # категория: видео
                }
                
                async with session.get(
                    f'{self.base_url}/search',
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    
                    if not data.get('result'):
                        return None
                    
                    torrents = []
                    for torrent in data['result'][:5]:  # первые 5
                        # Определяем качество из названия
                        name = torrent.get('name', '')
                        quality = 'Unknown'
                        if '2160p' in name or '4K' in name:
                            quality = '2160p'
                        elif '1080p' in name:
                            quality = '1080p'
                        elif '720p' in name:
                            quality = '720p'
                        
                        size_bytes = torrent.get('size', 0)
                        size_gb = round(size_bytes / (1024**3), 2)
                        
                        torrents.append({
                            'quality': quality,
                            'size': f'{size_gb} GB',
                            'seeders': torrent.get('seeders', 0),
                            'title': name[:60] + '...' if len(name) > 60 else name,
                            'magnet': torrent.get('magnet'),
                            'type': 'torrent'
                        })
                    
                    return {
                        'source': self.name,
                        'found': True,
                        'torrents': torrents
                    }
        
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка: {e}")
            return None

class JackettTorrentPlugin(VideoSource):
    """
    Универсальный поиск через Jackett
    Jackett - это прокси для множества торрент-трекеров
    Требует установки Jackett на локальном сервере
    """
    def __init__(self, jackett_url: str = None, api_key: str = None):
        super().__init__('Jackett')
        self.jackett_url = jackett_url or os.environ.get('JACKETT_URL', 'http://localhost:9117')
        self.api_key = api_key or os.environ.get('JACKETT_API_KEY', '')
    
    async def search(self, movie: Dict) -> Optional[Dict]:
        try:
            title = movie.get('nameRu') or movie.get('nameOriginal')
            year = movie.get('year')
            imdb_id = movie.get('imdbId')
            
            if not title:
                return None
            
            logger.info(f"[{self.name}] Поиск через Jackett: {title}")
            
            async with aiohttp.ClientSession() as session:
                params = {
                    'apikey': self.api_key,
                    'Query': f"{title} {year}" if year else title,
                }
                
                # Добавляем IMDb ID если есть
                if imdb_id:
                    params['IMDbId'] = imdb_id
                
                async with session.get(
                    f'{self.jackett_url}/api/v2.0/indexers/all/results',
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status != 200:
                        logger.warning(f"[{self.name}] Jackett недоступен (возможно не установлен)")
                        return None
                    
                    data = await response.json()
                    
                    if not data.get('Results'):
                        return None
                    
                    torrents = []
                    seen_titles = set()
                    
                    for result in data['Results'][:10]:
                        title = result.get('Title', '')
                        
                        # Дедупликация
                        if title in seen_titles:
                            continue
                        seen_titles.add(title)
                        
                        # Парсим качество
                        quality = 'Unknown'
                        if '2160p' in title or '4K' in title:
                            quality = '2160p'
                        elif '1080p' in title:
                            quality = '1080p'
                        elif '720p' in title:
                            quality = '720p'
                        
                        size_bytes = result.get('Size', 0)
                        size_gb = round(size_bytes / (1024**3), 2)
                        
                        torrents.append({
                            'quality': quality,
                            'size': f'{size_gb} GB',
                            'seeders': result.get('Seeders', 0),
                            'tracker': result.get('Tracker', 'Unknown'),
                            'title': title[:60] + '...' if len(title) > 60 else title,
                            'magnet': result.get('MagnetUri'),
                            'type': 'torrent'
                        })
                    
                    # Сортируем по сидам
                    torrents.sort(key=lambda x: x['seeders'], reverse=True)
                    
                    return {
                        'source': self.name,
                        'found': True,
                        'torrents': torrents
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
        logger.info(f"✅ Плагин '{source.name}' зарегистрирован")
    
    async def find_sources(self, movie: Dict) -> List[Dict]:
        """Поиск по всем источникам параллельно"""
        logger.info(f"🔍 Запуск поиска источников для: {movie.get('nameRu')}")
        
        # Запускаем поиск по всем плагинам одновременно
        tasks = [source.search(movie) for source in self.sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Фильтруем успешные результаты
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"❌ Плагин {self.sources[i].name} упал: {result}")
            elif result and result.get('found'):
                logger.info(f"✅ {self.sources[i].name} нашел источники")
                valid_results.append(result)
            else:
                logger.info(f"ℹ️ {self.sources[i].name} ничего не нашел")
        
        return valid_results

# Глобальный менеджер источников
source_manager = SourceManager()

# Регистрируем реальные плагины
# Балансеры
source_manager.register_source(VideoCDNBalancer())
source_manager.register_source(CollapsBalancer())
source_manager.register_source(HDRezkaBalancer())

# Торренты
source_manager.register_source(JackettTorrentPlugin())  # Требует Jackett
source_manager.register_source(RuTrackerPlugin())

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
        desc_short = description[:250] + '...' if len(description) > 250 else description
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
        return "\n\n❌ <b>Источники для просмотра не найдены</b>\n" \
               "💡 <i>Попробуйте настроить API ключи для балансеров</i>"
    
    info = "\n\n📺 <b>Доступные источники:</b>\n"
    
    for source_data in sources:
        source_name = source_data.get('source', 'Unknown')
        info += f"\n🎯 <b>{source_name}:</b>\n"
        
        # Балансеры с озвучками
        if 'translations' in source_data:
            for trans in source_data['translations'][:5]:  # Показываем первые 5
                name = trans.get('name', 'Unknown')
                quality = trans.get('quality', '')
                info += f"  • {name}"
                if quality:
                    info += f" ({quality})"
                info += "\n"
        
        # Торренты
        elif 'torrents' in source_data:
            for torrent in source_data['torrents'][:3]:  # Показываем первые 3
                quality = torrent.get('quality', 'Unknown')
                size = torrent.get('size', 'Unknown')
                seeders = torrent.get('seeders', 0)
                info += f"  • {quality} - {size} (👥 {seeders} сидов)\n"
    
    info += "\n💡 <i>Источники найдены автоматически через API</i>"
    return info

# ============================================
# TELEGRAM ОБРАБОТЧИКИ
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    await update.message.reply_text(
        '🎬 <b>Привет! Я продвинутый бот для поиска фильмов!</b>\n\n'
        '✨ <b>Возможности:</b>\n'
        '• Поиск информации из Кинопоиска\n'
        '• Автоматический поиск источников:\n'
        '  - VideoCDN, Collaps, HDRezka балансеры\n'
        '  - Торренты через RuTracker и Jackett\n'
        '• Информация о озвучках и качестве\n'
        '• Ссылки на трейлеры\n\n'
        '📝 <b>Просто отправь название фильма!</b>\n\n'
        '⚙️ <b>Настройка:</b>\n'
        'Для работы некоторых источников нужны API ключи:\n'
        '• VIDEOCDN_TOKEN для VideoCDN\n'
        '• JACKETT_URL и JACKETT_API_KEY для Jackett\n\n'
        'Команды: /start /help',
        parse_mode='HTML'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    await update.message.reply_text(
        '📖 <b>Подробная инструкция:</b>\n\n'
        '1️⃣ Отправьте название фильма или сериала\n'
        '2️⃣ Выберите из списка (если найдено несколько)\n'
        '3️⃣ Получите полную информацию + источники\n\n'
        '🎯 <b>Примеры:</b>\n'
        '• Матрица\n'
        '• Начало\n'
        '• Интерстеллар\n'
        '• Игра престолов\n\n'
        '🔌 <b>Источники:</b>\n'
        '• <b>VideoCDN</b> - популярный балансер\n'
        '• <b>Collaps</b> - агрегатор источников\n'
        '• <b>HDRezka</b> - онлайн-кинотеатр\n'
        '• <b>RuTracker</b> - торрент-трекер\n'
        '• <b>Jackett</b> - мета-поиск по торрентам\n\n'
        '⚙️ <b>API ключи:</b>\n'
        'Некоторые источники требуют регистрации:\n'
        '• VideoCDN: videocdn.tv\n'
        '• Jackett: требует установки\n\n'
        '💡 Бот автоматически пропускает недоступные источники',
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
        await show_movie_details(update, search_msg, movies[0].get('filmId'))
    else:
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
    await message.edit_text('📊 Получаю информацию...')
    
    movie = get_movie_by_id(film_id)
    
    if not movie:
        await message.edit_text('❌ Ошибка при получении информации о фильме.')
        return
    
    # Ищем источники
    await message.edit_text('🔎 Ищу источники для просмотра...\n⏳ Это может занять несколько секунд')
    sources = await source_manager.find_sources(movie)
    
    # Получаем трейлер
    trailer_url = get_movie_videos(film_id)
    
    # Форматируем
    poster_url = movie.get('posterUrl')
    info = format_movie_info(movie)
    info += format_sources_info(sources)
    
    # Кнопки
    keyboard = []
    if trailer_url:
        keyboard.append([InlineKeyboardButton("🎬 Трейлер", url=trailer_url)])
    
    kinopoisk_id = movie.get('kinopoiskId')
    if kinopoisk_id:
        keyboard.append([
            InlineKeyboardButton("🔍 Ссылки", callback_data=f"links_{film_id}")
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
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
        except Exception as e:
            logger.error(f"Ошибка отправки фото: {e}")
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
    
    elif query.data.startswith('links_'):
        film_id = query.data.replace('links_', '')
        movie = get_movie_by_id(film_id)
        
        if movie:
            kinopoisk_id = movie.get('kinopoiskId')
            imdb_id = movie.get('imdbId')
            name = movie.get('nameRu') or movie.get('nameOriginal')
            
            links_text = f"🔗 <b>Ссылки для '{name}':</b>\n\n"
            
            links_text += "📱 <b>Онлайн-кинотеатры:</b>\n"
            if kinopoisk_id:
                links_text += f"• <a href='https://www.kinopoisk.ru/film/{kinopoisk_id}/'>Кинопоиск</a>\n"
                links_text += f"• <a href='https://hd.kinopoisk.ru/film/{kinopoisk_id}/'>Кинопоиск HD</a>\n"
            if imdb_id:
                links_text += f"• <a href='https://www.imdb.com/title/{imdb_id}/'>IMDb</a>\n"
            
            links_text += "\n🎬 <b>Для медиацентров:</b>\n"
            if kinopoisk_id:
                links_text += f"• Kinopoisk ID: <code>{kinopoisk_id}</code>\n"
            if imdb_id:
                links_text += f"• IMDb ID: <code>{imdb_id}</code>\n"
            
            links_text += "\n💡 <b>Используйте эти ID в:</b>\n"
            links_text += "• Lampa (lampa.mx)\n"
            links_text += "• Kodi + плагины\n"
            links_text += "• Plex / Jellyfin\n"
            links_text += "• Stremio\n"
            
            # Добавляем прямую ссылку для Lampa
            if kinopoisk_id:
                links_text += f"\n🚀 <b>Быстрый запуск:</b>\n"
                links_text += f"<code>lampa://search?kinopoisk_id={kinopoisk_id}</code>"
            
            await query.message.reply_text(links_text, parse_mode='HTML')

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
    logger.info("="*50)
    logger.info("🚀 Бот запущен с реальными API!")
    logger.info("="*50)
    logger.info("📡 Активные источники:")
    for source in source_manager.sources:
        logger.info(f"   ✅ {source.name}")
    logger.info("="*50)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()


# ============================================
# ИНСТРУКЦИЯ ПО НАСТРОЙКЕ API
# ============================================

"""
🔧 НАСТРОЙКА API КЛЮЧЕЙ:

1. VideoCDN:
   - Регистрация: https://videocdn.tv
   - После регистрации получите API токен
   - Установите переменную окружения: VIDEOCDN_TOKEN=ваш_токен

2. Jackett (опционально, для расширенного поиска торрентов):
   - Скачайте: https://github.com/Jackett/Jackett
   - Установите и запустите (по умолчанию на порту 9117)
   - Получите API ключ в настройках
   - Установите: JACKETT_URL=http://localhost:9117
   - Установите: JACKETT_API_KEY=ваш_ключ

3. Collaps и HDRezka:
   - Работают без API ключей
   - Могут быть нестабильны из-за частых изменений API

4. RuTracker:
   - Работает через публичное API
   - Может требовать VPN в некоторых странах

📝 ПРИМЕР ЗАПУСКА С ПЕРЕМЕННЫМИ ОКРУЖЕНИЯ:

Linux/Mac:
export TELEGRAM_TOKEN="ваш_токен"
export KINOPOISK_API_KEY="ваш_ключ"
export VIDEOCDN_TOKEN="ваш_токен_videocdn"
export JACKETT_URL="http://localhost:9117"
export JACKETT_API_KEY="ваш_ключ_jackett"
python bot.py

Windows:
set TELEGRAM_TOKEN=ваш_токен
set KINOPOISK_API_KEY=ваш_ключ
set VIDEOCDN_TOKEN=ваш_токен_videocdn
set JACKETT_URL=http://localhost:9117
set JACKETT_API_KEY=ваш_ключ_jackett
python bot.py

🐳 DOCKER (рекомендуется):
Создайте файл .env:
TELEGRAM_TOKEN=ваш_токен
KINOPOISK_API_KEY=ваш_ключ
VIDEOCDN_TOKEN=ваш_токен_videocdn
JACKETT_URL=http://jackett:9117
JACKETT_API_KEY=ваш_ключ_jackett

Создайте docker-compose.yml:
version: '3.8'
services:
  bot:
    build: .
    env_file: .env
    restart: unless-stopped
  
  jackett:
    image: linuxserver/jackett
    ports:
      - "9117:9117"
    volumes:
      - ./jackett:/config
    restart: unless-stopped

Запуск: docker-compose up -d

⚠️ ВАЖНО:
- Бот работает и без API ключей, но с ограниченным функционалом
- Некоторые источники могут быть заблокированы в вашей стране
- Используйте VPN если необходимо
- API балансеров могут меняться - следите за обновлениями

💡 АЛЬТЕРНАТИВНЫЕ ИСТОЧНИКИ:
Вы можете легко добавить свои плагины, наследуясь от класса VideoSource:

class MyCustomPlugin(VideoSource):
    def __init__(self):
        super().__init__('MyPlugin')
    
    async def search(self, movie: Dict) -> Optional[Dict]:
        # Ваша логика поиска
        return {
            'source': self.name,
            'found': True,
            'translations': [...]
        }

# Регистрация
source_manager.register_source(MyCustomPlugin())

📚 ПОЛЕЗНЫЕ ССЫЛКИ:
- Lampa: https://lampa.mx
- VideoCDN API: https://videocdn.tv/api-documentation
- Jackett: https://github.com/Jackett/Jackett
- Kinopoisk API: https://kinopoiskapiunofficial.tech

🤝 ПОДДЕРЖКА:
Если источник не работает - это нормально, API часто меняются.
Бот автоматически пропускает недоступные источники.
"""