"""Bilingual Telegram anime recommendations with real covers and Persian summaries."""
import asyncio
import hashlib
import html
import json
import logging
import os
import random
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, ReplyKeyboardMarkup, Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / "run.env")
load_dotenv(BASE_DIR / ".env")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ANILIST_URL = "https://graphql.anilist.co"
TRANSLATION_URL = "https://api.mymemory.translated.net/get"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TEXT = {
    "fa": {
        "welcome": "سلام! 👋\nاز بین انیمه‌های برترِ ترند، یه پیشنهاد برات پیدا می‌کنم.\nاگه قبلاً دیدیش، «دیدم» رو بزن تا پیشنهاد بعدی بیاد.",
        "suggest": "🎲 چی ببینم؟", "language": "🌐 تغییر زبان", "seen": "✅ دیدم", "unseen": "🍿 بعداً می‌بینم",
        "watchlist": "📋 لیست تماشای من", "watchlist_empty": "هنوز چیزی برای بعداً ذخیره نکردی. زیر پیشنهادها «🍿 بعداً می‌بینم» رو بزن.",
        "watchlist_heading": "📋 لیست تماشای من — صفحهٔ {page} از {pages}",
        "remove": "🗑 حذف", "previous_page": "⬅️ قبلی", "next_page": "بعدی ➡️",
        "saved": "🍿 به لیست تماشات اضافه شد.", "missing_saved": "این مورد دیگر در لیست تماشات نیست.",
        "next": "🎲 پیشنهاد بعدی", "loading": "🎬 دارم پیشنهادت رو با عکس و خلاصهٔ فارسی آماده می‌کنم…",
        "related": "🔎 انیمه‌های مرتبط", "related_more": "🔎 موارد مرتبط بیشتر",
        "related_loading": "🔎 دارم انیمه‌های مرتبط رو با عکس و توضیحات آماده می‌کنم…",
        "related_heading": "🔎 انیمه‌های مرتبط با «{title}»",
        "related_none": "فعلاً انیمهٔ مرتبط تازه‌ای برای نمایش پیدا نشد.",
        "related_partial": "بعضی پیشنهادهای مرتبط آماده نشدن؛ برای ادامه یا تلاش دوباره دکمهٔ زیر رو بزن.",
        "same_series": "🧩 از همین مجموعه", "similar_anime": "✨ انیمهٔ مشابه",
        "busy": "یه لحظه؛ دارم پیشنهادت رو آماده می‌کنم…", "stale": "این پیشنهاد دیگه فعال نیست؛ یه پیشنهاد تازه بگیر.",
        "empty": "همهٔ انیمه‌های برترِ این فهرست رو دیدی! بعداً برای فهرست تازه برگرد.",
        "unavailable": "دریافت پیشنهاد فعلاً ممکن نشد. اتصال اینترنت و Xray رو بررسی کن و دوباره تلاش کن.",
        "translation_failed": "ترجمهٔ فارسی این خلاصه فعلاً آماده نشد. دوباره تلاش کن؛ متن انگلیسی جایگزین نمی‌شه.",
        "photo_failed": "عکس این انیمه دانلود نشد. دوباره تلاش کن تا پیشنهاد همراه عکس ارسال بشه.",
        "retry": "🔄 تلاش دوباره", "score": "امتیاز", "episodes": "قسمت‌های این فصل", "seasons": "فصل‌ها / بخش‌های تلویزیونی",
        "synopsis": "خلاصه داستان", "not_announced": "هنوز اعلام نشده", "unknown_value": "نامشخص",
        "at_least": "حداقل {count}؛ اطلاعات کامل نیست", "no_synopsis": "هنوز خلاصه‌ای برای این انیمه منتشر نشده است.",
        "title_unknown": "عنوان نامشخص",
        "season_synopsis_pending": "این انیمه ادامهٔ مجموعه است؛ خلاصهٔ کامل داستان این فصل هنوز منتشر نشده است.",
        "help": "🎲 پیشنهاد تصادفی از انیمه‌های برترِ ترند\n✅ دیدم: پیشنهاد بعدی\n🍿 بعداً می‌بینم: ذخیره در لیست تماشا\n/watchlist لیست تماشا؛ حذف یا ثبت به‌عنوان دیده‌شده\n/language تغییر زبان\n/start شروع دوباره\n\nتعداد قسمت مربوط به فصل پیشنهادی است؛ فصل‌ها از بخش‌های تلویزیونی مرتبط شمرده می‌شوند.",
    },
    "en": {
        "welcome": "Hi! 👋\nI'll pick a random anime from the highest-rated trending shows.\nAlready watched it? Tap ‘Seen’ for another suggestion.",
        "suggest": "🎲 What should I watch?", "language": "🌐 Change language", "seen": "✅ Seen", "unseen": "🍿 Watch later",
        "watchlist": "📋 My watchlist", "watchlist_empty": "Your watchlist is empty. Tap ‘🍿 Watch later’ below a recommendation to save it.",
        "watchlist_heading": "📋 My watchlist — page {page} of {pages}",
        "remove": "🗑 Remove", "previous_page": "⬅️ Previous", "next_page": "Next ➡️",
        "saved": "🍿 Added to your watchlist.", "missing_saved": "This item is no longer in your watchlist.",
        "next": "🎲 Next suggestion", "loading": "🎬 Finding your anime, cover and synopsis…",
        "related": "🔎 Related anime", "related_more": "🔎 More related anime",
        "related_loading": "🔎 Finding related anime, covers and synopses…",
        "related_heading": "🔎 Anime related to ‘{title}’",
        "related_none": "No new related anime are available to show right now.",
        "related_partial": "Some related picks couldn't be prepared. Tap below to continue or try again.",
        "same_series": "🧩 From the same series", "similar_anime": "✨ Similar anime",
        "busy": "One moment; your suggestion is on its way…", "stale": "This suggestion is no longer active. Get a new one.",
        "empty": "You've watched every top anime in this list! Come back later for a refreshed list.",
        "unavailable": "Couldn't load a suggestion. Check your internet connection and Xray, then try again.",
        "translation_failed": "The translated synopsis is temporarily unavailable. Please try again.",
        "photo_failed": "Couldn't download this anime's cover. Please try again.",
        "retry": "🔄 Try again", "score": "Rating", "episodes": "Episodes in this season", "seasons": "Seasons / TV parts",
        "synopsis": "Synopsis", "not_announced": "Not announced yet", "unknown_value": "Unknown",
        "at_least": "At least {count}; incomplete data", "no_synopsis": "No synopsis has been published for this anime yet.",
        "title_unknown": "Unknown title",
        "season_synopsis_pending": "This is a continuation of the series. A full plot synopsis for this season has not been published yet.",
        "help": "🎲 Random picks from the highest-rated trending anime\n✅ Seen: get another suggestion\n🍿 Watch later: save to your watchlist\n/watchlist view, remove or mark saved anime as watched\n/language change language\n/start start again\n\nEpisode counts apply to the suggested season. Seasons count related TV parts, including split seasons.",
    },
}


TEXT["en"].update({
    "search": "🔎 Search anime", "top": "🏆 Top rated", "airing": "📡 Airing now",
    "genre_pick": "🎭 Pick a genre", "genre_prompt": "Choose a genre for a random recommendation.",
    "genre_empty": "No more unwatched picks in {genre} match your filters. Try another genre or adjust /settings.",
    "settings": "⚙️ Preferences", "history": "✅ Watched history", "stats": "📊 My stats",
    "search_prompt": "Send an anime title (English or Japanese romanization). /cancel to exit search.",
    "search_short": "Please enter 2–100 characters.", "cancelled": "Search cancelled.",
    "results": "🔎 {title} · page {page}\nTap a title for its poster and details.",
    "no_results": "No titles found. Try a different title or loosen your preferences.",
    "discover_loading": "🔎 Looking up anime…", "open": "🎬 Details", "undo": "↩️ Undo watched",
    "history_empty": "No watched anime yet. Tap Seen on an anime card to add one.",
    "history_heading": "✅ Watched anime · page {page} of {pages}",
    "preferences": "⚙️ Recommendation preferences\n\nGenre: {genre}\nMinimum rating: {score}\nMaximum episodes: {episodes}\n\nApplies to random picks, top rated and airing lists. Search includes all formats and ignores these filters.",
    "any": "Any", "genre": "Genre", "rating": "Minimum rating", "length": "Maximum episodes",
    "reset": "Reset filters", "done": "Done", "genres": "Genres", "year": "Year",
    "profile": "📊 Your anime stats\n\n✅ Watched: {seen}\n🍿 Watchlist: {saved}\n🎬 Discovered: {shown}\n\n/export downloads your lists and preferences.",
    "export_caption": "Your anime lists and preferences. Keep this file as a personal backup.",
})
TEXT["fa"].update({
    "search": "🔎 جستجوی انیمه", "top": "🏆 برترین‌ها", "airing": "📡 در حال پخش",
    "genre_pick": "🎭 انتخاب ژانر", "genre_prompt": "یه ژانر انتخاب کن تا یه انیمهٔ تصادفی پیشنهاد بدم.",
    "genre_empty": "در ژانر {genre} پیشنهاد تازه‌ای با این فیلترها پیدا نشد. ژانر دیگری انتخاب کن یا /settings رو تغییر بده.",
    "settings": "⚙️ سلیقهٔ من", "history": "✅ انیمه‌های دیده‌شده", "stats": "📊 آمار من",
    "search_prompt": "اسم انیمه رو به انگلیسی یا ژاپنی با حروف لاتین بفرست. برای خروج /cancel رو بزن.",
    "search_short": "لطفاً بین ۲ تا ۱۰۰ حرف بنویس.", "cancelled": "جستجو لغو شد.",
    "results": "🔎 {title} · صفحهٔ {page}\nبرای دیدن پوستر و توضیحات، عنوان رو بزن.",
    "no_results": "چیزی پیدا نشد. اسم دیگری امتحان کن یا فیلترهای سلیقه رو کمتر کن.",
    "discover_loading": "🔎 دارم انیمه‌ها رو پیدا می‌کنم…", "open": "🎬 جزئیات", "undo": "↩️ لغو دیده‌شده",
    "history_empty": "هنوز انیمه‌ای رو دیده‌شده ثبت نکردی. زیر کارت انیمه «دیدم» رو بزن.",
    "history_heading": "✅ انیمه‌های دیده‌شده · صفحهٔ {page} از {pages}",
    "preferences": "⚙️ سلیقهٔ پیشنهادها\n\nژانر: {genre}\nحداقل امتیاز: {score}\nحداکثر قسمت: {episodes}\n\nاین فیلترها روی پیشنهاد تصادفی، برترین‌ها و در حال پخش اعمال می‌شن. جستجو همهٔ قالب‌ها رو شامل می‌شه و از این فیلترها استفاده نمی‌کنه.",
    "any": "همه", "genre": "ژانر", "rating": "حداقل امتیاز", "length": "حداکثر قسمت",
    "reset": "پاک‌کردن فیلترها", "done": "تمام", "genres": "ژانرها", "year": "سال",
    "profile": "📊 آمار انیمه‌های تو\n\n✅ دیده‌شده: {seen}\n🍿 لیست تماشا: {saved}\n🎬 کشف‌شده: {shown}\n\nبرای دانلود لیست‌ها و سلیقه‌ات /export رو بزن.",
    "export_caption": "لیست‌ها و سلیقهٔ انیمهٔ تو؛ این فایل رو برای پشتیبان نگه دار.",
})
for language in TEXT:
    TEXT[language]["help"] += ("\n\n/genre · /search Naruto · /top · /airing\n/settings · /history · /stats · /export · /cancel")

# AniList genre names are API values; Persian labels are only for display.
GENRES = {"Action": "اکشن", "Adventure": "ماجراجویی", "Comedy": "کمدی", "Drama": "درام",
          "Fantasy": "فانتزی", "Horror": "ترسناک", "Mystery": "معمایی", "Psychological": "روان‌شناختی",
          "Romance": "عاشقانه", "Sci-Fi": "علمی‌تخیلی", "Slice of Life": "روزمره", "Sports": "ورزشی",
          "Supernatural": "ماورایی", "Thriller": "هیجانی", "Music": "موسیقی", "Mecha": "مکا"}


class TranslationUnavailable(Exception):
    pass


class CoverUnavailable(Exception):
    pass


class Store:
    """Keep preferences, watched history and translations across restarts."""
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, language TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS history (
                user_id INTEGER NOT NULL, anime_id INTEGER NOT NULL, status TEXT NOT NULL,
                PRIMARY KEY (user_id, anime_id));
            CREATE TABLE IF NOT EXISTS translations (source_hash TEXT PRIMARY KEY, text TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS anime_titles (
                anime_id INTEGER PRIMARY KEY, title TEXT NOT NULL, english_title TEXT);
            CREATE TABLE IF NOT EXISTS watchlist (
                user_id INTEGER NOT NULL, anime_id INTEGER NOT NULL,
                saved_at INTEGER NOT NULL DEFAULT (unixepoch()), PRIMARY KEY (user_id, anime_id));
            CREATE TABLE IF NOT EXISTS preferences (
                user_id INTEGER PRIMARY KEY, genre TEXT, min_score INTEGER NOT NULL DEFAULT 0,
                max_episodes INTEGER NOT NULL DEFAULT 0);
        """)

    def load_user(self, user_id):
        row = self.db.execute("SELECT language FROM users WHERE id=?", (user_id,)).fetchone()
        history = self.db.execute("SELECT anime_id,status FROM history WHERE user_id=?", (user_id,)).fetchall()
        return {"language": row[0] if row else None,
                "shown_anime": {anime_id for anime_id, _ in history},
                "seen_anime": {anime_id for anime_id, status in history if status == "seen"}}

    def language(self, user_id, language):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO users VALUES (?,?)", (user_id, language))

    def record(self, user_id, anime_id, status):
        with self.db:
            self.db.execute("INSERT INTO history VALUES (?,?,?) ON CONFLICT(user_id,anime_id) "
                            "DO UPDATE SET status=CASE WHEN history.status='seen' THEN 'seen' ELSE excluded.status END",
                            (user_id, anime_id, status))
            if status == "seen":
                self.db.execute("DELETE FROM watchlist WHERE user_id=? AND anime_id=?", (user_id, anime_id))

    def remember_anime(self, anime):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO anime_titles VALUES (?,?,?)",
                            (anime["id"], anime.get("title") or str(anime["id"]), anime.get("english_title")))

    def save_for_later(self, user_id, anime_id):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO watchlist (user_id,anime_id) "
                            "SELECT ?,anime_id FROM anime_titles WHERE anime_id=? "
                            "AND NOT EXISTS (SELECT 1 FROM history WHERE user_id=? AND anime_id=? AND status='seen')",
                            (user_id, anime_id, user_id, anime_id))
        return self.db.execute("SELECT 1 FROM watchlist WHERE user_id=? AND anime_id=?", (user_id, anime_id)).fetchone() is not None

    def saved_anime(self, user_id):
        return self.db.execute("SELECT w.anime_id,a.title,a.english_title FROM watchlist w "
                               "JOIN anime_titles a ON a.anime_id=w.anime_id WHERE w.user_id=? "
                               "ORDER BY w.saved_at DESC,w.rowid DESC", (user_id,)).fetchall()

    def remove_saved(self, user_id, anime_id, seen=False):
        with self.db:
            removed = self.db.execute("DELETE FROM watchlist WHERE user_id=? AND anime_id=?", (user_id, anime_id)).rowcount
            if removed and seen:
                self.record(user_id, anime_id, "seen")
        return bool(removed)

    def reset_shown(self, user_id):
        with self.db:
            self.db.execute("DELETE FROM history WHERE user_id=? AND status!='seen'", (user_id,))

    def translation(self, source_hash):
        row = self.db.execute("SELECT text FROM translations WHERE source_hash=?", (source_hash,)).fetchone()
        return row[0] if row else None

    def save_translation(self, source_hash, text):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO translations VALUES (?,?)", (source_hash, text))

    def preferences(self, user_id):
        row = self.db.execute("SELECT genre,min_score,max_episodes FROM preferences WHERE user_id=?", (user_id,)).fetchone()
        return dict(zip(("genre", "min_score", "max_episodes"), row or (None, 0, 0)))

    def set_preference(self, user_id, field, value):
        if field not in {"genre", "min_score", "max_episodes"}:
            raise ValueError("Unknown preference")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO preferences(user_id) VALUES (?)", (user_id,))
            self.db.execute(f"UPDATE preferences SET {field}=? WHERE user_id=?", (value, user_id))

    def watched(self, user_id):
        return self.db.execute("SELECT h.anime_id,a.title,a.english_title FROM history h "
                               "LEFT JOIN anime_titles a ON a.anime_id=h.anime_id "
                               "WHERE h.user_id=? AND h.status='seen' ORDER BY h.anime_id DESC", (user_id,)).fetchall()

    def undo_seen(self, user_id, anime_id):
        with self.db:
            return bool(self.db.execute("UPDATE history SET status='shown' WHERE user_id=? AND anime_id=? AND status='seen'",
                                        (user_id, anime_id)).rowcount)


_store = None
_cache = {}
_request_lock = asyncio.Lock()
_last_request = 0.0
_photo_ids = {}
_translation_locks = {}
_translation_cooldowns = {}


def get_store():
    global _store
    if _store is None:
        _store = Store(BASE_DIR / "animebot.sqlite3")
    return _store


def state_for(update, context):
    state = context.user_data
    if not state.get("loaded"):
        state.update(get_store().load_user(update.effective_user.id))
        state["loaded"] = True
    return state


def locale(state):
    return state.get("language") if state.get("language") in TEXT else "fa"


def menu(language):
    w = TEXT[language]
    return ReplyKeyboardMarkup([[w["suggest"], w["search"]], [w["top"], w["airing"]],
                                [w["watchlist"], w["history"]], [w["settings"], w["stats"]],
                                [w["genre_pick"], w["language"]]], resize_keyboard=True)


def language_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
        InlineKeyboardButton("🇮🇷 فارسی", callback_data="lang:fa"),
    ]])


async def choose_language(message):
    await message.reply_text("🌐 زبانت رو انتخاب کن:\nChoose your language:", reply_markup=language_keyboard())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state_for(update, context).pop("awaiting_search", None)
    await choose_language(update.effective_message)


async def set_language(update, context):
    query = update.callback_query
    language = query.data.split(":", 1)[1]
    if language not in TEXT:
        await query.answer()
        return
    state = state_for(update, context)
    if state.get("suggestion_busy"):
        await query.answer(TEXT[locale(state)]["busy"])
        return
    state["language"] = language
    state.pop("active_suggestion", None)
    state.pop("active_genre", None)
    state.pop("genre_retry", None)
    state.pop("retry_anime", None)
    for key in ("related_cards", "related_origins", "related_controls", "related_shown"):
        state.pop(key, None)
    for key in ("catalogs", "awaiting_search", "settings_controls", "history_controls"):
        state.pop(key, None)
    get_store().language(update.effective_user.id, language)
    await query.answer()
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except BadRequest:
        pass
    await query.message.reply_text(TEXT[language]["welcome"], reply_markup=menu(language))


def proxy_url():
    return os.getenv("ANIME_PROXY_URL") or os.getenv("TELEGRAM_PROXY_URL") or None


async def anilist_query(session, query, **variables):
    global _last_request
    # AniList treats explicit null filters differently from omitted filters; some return HTTP 500.
    variables = {name: value for name, value in variables.items() if value is not None}
    key = (query, json.dumps(variables, sort_keys=True))
    async with _request_lock:
        cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < 900:
            return cached[1]
        for attempt in range(2):
            await asyncio.sleep(max(0, 0.65 - (time.monotonic() - _last_request)))
            _last_request = time.monotonic()
            try:
                async with session.post(ANILIST_URL, json={"query": query, "variables": variables},
                                        proxy=proxy_url(), timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status in {429, 500, 502, 503, 504} and attempt == 0:
                        await asyncio.sleep(1)
                        continue
                    response.raise_for_status()
                    payload = await response.json()
                    if payload.get("errors") or not payload.get("data"):
                        raise ValueError("AniList returned no usable data")
                    if len(_cache) >= 512:
                        for old_key in list(_cache)[:128]:
                            _cache.pop(old_key, None)
                    _cache[key] = (time.monotonic(), payload["data"])
                    return payload["data"]
            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt:
                    raise


def clean_text(text):
    text = BeautifulSoup(html.unescape(text or ""), "html.parser").get_text(" ")
    text = re.split(r"\(?Source\s*:|\bNote\s*:", text, maxsplit=1, flags=re.I)[0]
    return re.sub(r"\s+", " ", re.sub(r"https?://\S+", "", text)).strip()


def normalize_anime(item):
    cover = item.get("coverImage") or {}
    image = cover.get("extraLarge") or cover.get("large")
    if not item.get("id") or not image:
        return None
    title = item.get("title") or {}
    return {
        "id": item["id"], "title": title.get("romaji") or title.get("english"),
        "english_title": title.get("english"), "score": item["averageScore"] / 10 if item.get("averageScore") else None,
        "episodes": item.get("episodes"), "synopsis": clean_text(item.get("description")),
        "cover": image, "relations": item.get("relations") or {},
        "genres": item.get("genres") or [], "year": item.get("seasonYear"), "format": item.get("format"),
    }


async def fetch_anime_data(session):
    payload = await anilist_query(session, """
        { Page(perPage:50) {
            media(type:ANIME, format:TV, sort:TRENDING_DESC, isAdult:false) {
                id title { romaji english } averageScore episodes genres seasonYear format description(asHtml:false)
                coverImage { extraLarge large }
                relations { edges { relationType node { id type format } } }
            }
        } }
    """)
    candidates = {}
    for item in payload["Page"]["media"]:
        normalized = normalize_anime(item)
        if normalized and normalized["score"] is not None:
            candidates[item["id"]] = normalized
    return sorted(candidates.values(), key=lambda item: item["score"], reverse=True)[:25]


async def fetch_catalog(session, mode="top", search=None, page=1, preferences=None, per_page=6):
    preferences = preferences or {}
    payload = await anilist_query(session, """
        query ($search:String,$page:Int!,$size:Int!,$sort:[MediaSort],$status:MediaStatus,
               $genre:String,$score:Int,$episodes:Int,$formats:[MediaFormat]) {
            Page(page:$page,perPage:$size) {
                pageInfo { hasNextPage }
                media(type:ANIME,isAdult:false,search:$search,sort:$sort,status:$status,
                      genre:$genre,averageScore_greater:$score,episodes_lesser:$episodes,format_in:$formats) {
                    id title { romaji english } averageScore episodes genres seasonYear format
                    description(asHtml:false) coverImage { extraLarge large }
                    relations { edges { relationType node { id type format } } }
                }
            }
        }
    """, search=search, page=page, size=per_page,
        sort=None if search else ["SCORE_DESC" if mode == "top" else "TRENDING_DESC"],
        status="RELEASING" if mode == "airing" else None,
        genre=preferences.get("genre") if not search else None,
        score=preferences["min_score"] - 1 if not search and preferences.get("min_score") else None,
        episodes=preferences["max_episodes"] + 1 if not search and preferences.get("max_episodes") else None,
        formats=None if search else ["TV", "TV_SHORT"])
    data = payload["Page"]
    items = [anime for item in data["media"] if (anime := normalize_anime(item))]
    return items, bool(data["pageInfo"]["hasNextPage"])


async def fetch_related_anime(session, anime_id):
    """Combine explicit TV franchise relations with community-ranked similar shows."""
    payload = await anilist_query(session, """
        query ($id:Int!) {
            Media(id:$id,type:ANIME) {
                title { romaji english }
                relations { edges { relationType node { ...RelatedCard } } }
                recommendations(perPage:20,sort:RATING_DESC) {
                    nodes { mediaRecommendation { ...RelatedCard } }
                }
            }
        }
        fragment RelatedCard on Media {
            id type format isAdult title { romaji english } averageScore episodes genres seasonYear description(asHtml:false)
            coverImage { extraLarge large }
            relations { edges { relationType node { id type format } } }
        }
    """, id=anime_id)
    media = payload.get("Media") or {}
    candidates = {}

    def add(item, kind):
        if (not item or item.get("id") == anime_id or item.get("type") != "ANIME"
                or item.get("format") not in {"TV", "TV_SHORT"} or item.get("isAdult") is not False):
            return
        normalized = normalize_anime(item)
        if normalized and normalized["id"] not in candidates:
            normalized["related_kind"] = kind
            candidates[normalized["id"]] = normalized

    for edge in (media.get("relations") or {}).get("edges", []):
        if edge.get("relationType") in {"PREQUEL", "SEQUEL", "SIDE_STORY", "PARENT", "SPIN_OFF", "ALTERNATIVE"}:
            add(edge.get("node"), "same_series")
    for recommendation in (media.get("recommendations") or {}).get("nodes", []):
        if recommendation:
            add(recommendation.get("mediaRecommendation"), "similar_anime")
    return media.get("title") or {}, list(candidates.values())


@dataclass(frozen=True)
class SeasonCount:
    count: int
    complete: bool = True


async def count_seasons(session, anime):
    """Walk TV sequels/prequels through movie bridges, with a bounded total wait."""
    cache_key = ("seasons", anime["id"])
    cached = _cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < (3600 if cached[1].complete else 120):
        return cached[1]
    pending = [(anime["id"], anime.get("format") or "TV")]
    discovered = {anime["id"]: anime.get("format") or "TV"}
    visited = set()
    complete = True
    deadline = time.monotonic() + 8
    while pending and len(visited) < 20:
        anime_id, _ = pending.pop()
        if anime_id in visited:
            continue
        if time.monotonic() >= deadline:
            complete = False
            break
        visited.add(anime_id)
        try:
            if anime_id == anime["id"]:
                details = anime
            else:
                details = (await asyncio.wait_for(anilist_query(session, """
                    query ($id:Int!) { Media(id:$id,type:ANIME) {
                        relations { edges { relationType node { id type format } } }
                    } }
                """, id=anime_id), timeout=max(0.1, deadline - time.monotonic())))["Media"]
                if not details:
                    complete = False
                    continue
            for edge in details.get("relations", {}).get("edges", []):
                node = edge.get("node") or {}
                if edge.get("relationType") not in {"PREQUEL", "SEQUEL"} or node.get("type") != "ANIME":
                    continue
                related_id = node["id"]
                discovered[related_id] = node.get("format")
                if related_id not in visited:
                    pending.append((related_id, node.get("format")))
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError):
            complete = False
    if pending:
        complete = False
    result = SeasonCount(sum(fmt in {"TV", "TV_SHORT"} for fmt in discovered.values()), complete)
    _cache[cache_key] = (time.monotonic(), result)
    return result


def truncate(text, max_units):
    """Telegram counts UTF-16 units: emoji may take two units."""
    if len(text.encode("utf-16-le")) // 2 <= max_units:
        return text
    return text.encode("utf-16-le")[:max(0, max_units - 1) * 2].decode("utf-16-le", errors="ignore").rstrip() + "…"


def translation_segment(text):
    """A short plot summary within MyMemory's 500-byte request limit."""
    text = clean_text(text)
    if len(text.encode("utf-8")) <= 450:
        return text
    clipped = text.encode("utf-8")[:450].decode("utf-8", errors="ignore")
    sentences = re.findall(r".*?[.!?](?:\s|$)", clipped)
    if sentences and len("".join(sentences)) >= 120:
        return "".join(sentences).strip()
    return clipped.rsplit(" ", 1)[0].rstrip(".,;:") + "…"


def is_persian(text):
    letters = sum(ch.isalpha() for ch in text)
    persian = sum("\u0621" <= ch <= "\u06cc" for ch in text if ch.isalpha())
    return letters >= 5 and persian / max(letters, 1) >= 0.45


async def translate_synopsis(session, synopsis, language):
    source = clean_text(synopsis)
    if not source:
        return TEXT[language]["no_synopsis"]
    if language == "en":
        return source
    if is_persian(source):
        return source
    # Some AniList entries only say "The third season of ...", rather than providing a plot.
    if len(source) < 180 and re.match(
        r"^(?:The\s+)?(?:\d+(?:st|nd|rd|th)|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+(?:season|part|cour)\b",
        source, re.I,
    ):
        return TEXT[language]["season_synopsis_pending"]
    segment = translation_segment(source)
    key = hashlib.sha256(segment.encode("utf-8")).hexdigest()
    lock = _translation_locks.setdefault(key, asyncio.Lock())
    async with lock:
        cached = get_store().translation(key)
        if cached and is_persian(cached):
            return cached
        # MyMemory is reachable directly; the local proxy supplies a second route if needed.
        routes = list(dict.fromkeys([None, proxy_url()]))
        for route in routes:
            if _translation_cooldowns.get(route, 0) > time.monotonic():
                continue
            try:
                async with session.get(TRANSLATION_URL, params={"q": segment, "langpair": "en|fa"},
                                       proxy=route, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    response.raise_for_status()
                    payload = await response.json()
                if str(payload.get("responseStatus")) != "200" or payload.get("quotaFinished"):
                    _translation_cooldowns[route] = time.monotonic() + 300
                    continue
                translated = clean_text(payload.get("responseData", {}).get("translatedText"))
                translated = translated.replace("ي", "ی").replace("ك", "ک")
                if not is_persian(translated):
                    continue
                get_store().save_translation(key, translated)
                return translated
            except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, TypeError, ValueError):
                continue
        raise TranslationUnavailable()


async def download_cover(session, anime):
    try:
        async with session.get(anime["cover"], proxy=proxy_url(), timeout=aiohttp.ClientTimeout(total=10)) as response:
            response.raise_for_status()
            if not response.headers.get("Content-Type", "").lower().startswith("image/"):
                raise CoverUnavailable()
            chunks, size = [], 0
            async for chunk in response.content.iter_chunked(65536):
                size += len(chunk)
                if size > 8 * 1024 * 1024:
                    raise CoverUnavailable()
                chunks.append(chunk)
            data = b"".join(chunks)
            if not data:
                raise CoverUnavailable()
            return data
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError) as exc:
        raise CoverUnavailable() from exc


def format_suggestion(anime, synopsis, seasons, language):
    words = TEXT[language]
    title = (anime.get("english_title") if language == "en" else None) or anime.get("title") or words["title_unknown"]
    score = f"{anime['score']:.1f}/10" if anime.get("score") is not None else words["unknown_value"]
    episodes = anime.get("episodes") if anime.get("episodes") is not None else words["not_announced"]
    season_text = str(seasons.count) if seasons.complete else words["at_least"].format(count=seasons.count)
    header = (f"🎬 {truncate(clean_text(title), 140)}\n\n"
              f"⭐ {words['score']}: {score}\n📺 {words['episodes']}: {episodes}\n"
              f"🗂 {words['seasons']}: {season_text}\n\n📖 {words['synopsis']}\n")
    details = []
    if anime.get("year"):
        details.append(f"{words['year']}: {anime['year']}")
    if anime.get("genres"):
        genres = [GENRES.get(g, g) if language == "fa" else g for g in anime["genres"][:3]]
        details.append(f"{words['genres']}: {', '.join(genres)}")
    if details:
        header = header.replace(f"\n\n📖 {words['synopsis']}", "\n" + " · ".join(details) + f"\n\n📖 {words['synopsis']}")
    if anime.get("format") not in {None, "TV", "TV_SHORT"}:
        formats = {"MOVIE": "فیلم", "OVA": "اُوی‌اِی", "ONA": "اینترنتی", "SPECIAL": "ویژه", "MUSIC": "موزیک‌ویدیو"}
        label = formats.get(anime["format"], anime["format"]) if language == "fa" else anime["format"].replace("_", " ").title()
        header = header.replace(f"🗂 {words['seasons']}: {season_text}", f"🎞 {label}")
    if anime.get("related_kind") in {"same_series", "similar_anime"}:
        header = words[anime["related_kind"]] + "\n" + header
    remaining = 1024 - len(header.encode("utf-16-le")) // 2
    return header + truncate(clean_text(synopsis), remaining)


def feedback_keyboard(anime_id, language):
    words = TEXT[language]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(words["seen"], callback_data=f"seen:{anime_id}"),
         InlineKeyboardButton(words["unseen"], callback_data=f"unseen:{anime_id}")],
        [InlineKeyboardButton(words["next"], callback_data=f"next:{anime_id}")],
        [InlineKeyboardButton(words["related"], callback_data=f"related:{anime_id}")],
    ])


def retry_keyboard(language):
    return InlineKeyboardMarkup([[InlineKeyboardButton(TEXT[language]["retry"], callback_data="retry")]])


def remember_message(state, name, key, value, limit=80):
    messages = state.setdefault(name, {})
    messages[key] = value
    while len(messages) > limit:
        messages.pop(next(iter(messages)))


async def deliver_anime(update, context, session, anime, language, related=False):
    """Use the same photo, translation and feedback behavior for every recommendation."""
    state = state_for(update, context)
    message = update.effective_message
    file_id = _photo_ids.get(anime["id"])
    tasks = [translate_synopsis(session, anime.get("synopsis"), language), count_seasons(session, anime)]
    if not file_id:
        tasks.append(download_cover(session, anime))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException):
            raise result
    synopsis, seasons = results[:2]
    caption = format_suggestion(anime, synopsis, seasons, language)
    photo = file_id or InputFile(results[2], filename=f"anime-{anime['id']}.jpg")
    try:
        sent = await message.reply_photo(photo, caption=caption, reply_markup=feedback_keyboard(anime["id"], language),
                                        show_caption_above_media=False, write_timeout=40, read_timeout=40)
    except BadRequest:
        if not file_id:
            raise
        _photo_ids.pop(anime["id"], None)
        data = await download_cover(session, anime)
        sent = await message.reply_photo(InputFile(data, filename=f"anime-{anime['id']}.jpg"), caption=caption,
                                        reply_markup=feedback_keyboard(anime["id"], language),
                                        show_caption_above_media=False, write_timeout=40, read_timeout=40)
    state["shown_anime"].add(anime["id"])
    card = (message.chat_id, sent.message_id, anime["id"])
    remember_message(state, "related_origins", card, True)
    if related:
        remember_message(state, "related_cards", card, True)
    else:
        state["active_suggestion"] = card
        state.pop("retry_anime", None)
    get_store().record(update.effective_user.id, anime["id"], "shown")
    get_store().remember_anime(anime)
    if sent.photo:
        _photo_ids[anime["id"]] = sent.photo[-1].file_id
    logger.info("Suggestion delivered: anime=%s language=%s related=%s", anime["id"], language, related)
    return sent


async def genre_command(update, context):
    state = state_for(update, context)
    message = update.effective_message
    if state.get("language") not in TEXT:
        await choose_language(message)
        return
    state.pop("awaiting_search", None)
    language = locale(state)
    buttons = [
        InlineKeyboardButton(GENRES[genre] if language == "fa" else genre, callback_data=f"genre:{index}")
        for index, genre in enumerate(GENRES)
    ]
    await message.reply_text(TEXT[language]["genre_prompt"], reply_markup=InlineKeyboardMarkup(
        [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
    ))


async def handle_genre(update, context):
    query = update.callback_query
    state = state_for(update, context)
    words = TEXT[locale(state)]
    choice = query.data.split(":", 1)[1]
    if choice == "retry":
        retry = state.get("genre_retry")
        if not retry or retry[0] != (query.message.chat_id, query.message.message_id):
            await query.answer(words["stale"])
            return
        _, genre, pending, previous = retry
    else:
        index = int(choice)
        if index >= len(GENRES):
            await query.answer(words["stale"])
            return
        genre, pending, previous = list(GENRES)[index], None, None
    await query.answer()
    await suggest_anime(update, context, genre=genre, pending=pending, previous=previous)


async def suggest_anime(update, context, genre=None, pending=None, previous=None):
    state = state_for(update, context)
    message = update.effective_message
    if state.get("language") not in TEXT:
        await choose_language(message)
        return
    language = locale(state)
    words = TEXT[language]
    if state.get("suggestion_busy"):
        await message.reply_text(words["busy"])
        return
    state["suggestion_busy"] = True
    state.pop("genre_retry", None)
    progress = None
    try:
        progress = await message.reply_text(words["loading"])
        async with aiohttp.ClientSession() as session:
            preferences = get_store().preferences(update.effective_user.id)
            if genre:
                preferences["genre"] = genre
            if any(preferences.values()):
                pool, _ = await fetch_catalog(session, mode="trending", preferences=preferences, per_page=50)
            else:
                pool = await fetch_anime_data(session)
            eligible = [item for item in pool if item["id"] not in state["seen_anime"] and item["id"] != previous]
            choices = [item for item in eligible if item["id"] not in state["shown_anime"]]
            if not choices:
                choices = eligible
                if choices and not genre:
                    state["shown_anime"].clear()
                    get_store().reset_shown(update.effective_user.id)
            if not choices:
                if genre:
                    label = GENRES[genre] if language == "fa" else genre
                    await progress.edit_text(words["genre_empty"].format(genre=label))
                else:
                    await progress.edit_text(words["empty"] if pool else words["no_results"])
                return
            if not genre:
                pending = state.get("retry_anime")
            anime = next((item for item in choices if item["id"] == pending), None) or random.choice(choices)
            pending = anime["id"]
            if not genre:
                state["retry_anime"] = pending
            await deliver_anime(update, context, session, anime, language)
            state["active_genre"] = genre
        try:
            await progress.delete()
        except TelegramError:
            pass
    except (TranslationUnavailable, CoverUnavailable, aiohttp.ClientError, asyncio.TimeoutError, TelegramError, ValueError, KeyError) as exc:
        key = "translation_failed" if isinstance(exc, TranslationUnavailable) else "photo_failed" if isinstance(exc, CoverUnavailable) else "unavailable"
        logger.warning("Suggestion failed (%s)", type(exc).__name__)
        if progress:
            markup = retry_keyboard(language)
            if genre:
                state["genre_retry"] = ((message.chat_id, progress.message_id), genre, pending, previous)
                markup = InlineKeyboardMarkup([[InlineKeyboardButton(words["retry"], callback_data="genre:retry")]])
            await progress.edit_text(words[key], reply_markup=markup)
        else:
            await message.reply_text(words[key], reply_markup=menu(language))
    finally:
        state["suggestion_busy"] = False


async def show_related(update, context):
    query = update.callback_query
    state = state_for(update, context)
    if state.get("language") not in TEXT:
        await query.answer()
        await choose_language(update.effective_message)
        return
    language = locale(state)
    words = TEXT[language]
    action, value = query.data.split(":", 1)
    anime_id = int(value)
    source_card = (query.message.chat_id, query.message.message_id, anime_id)
    if action == "relatedmore":
        valid = state.get("related_controls", {}).get(source_card[:2]) == anime_id
    else:
        valid = (state.get("active_suggestion") == source_card
                 or source_card in state.get("related_cards", {})
                 or source_card in state.get("related_origins", {}))
    if not valid:
        await query.answer(words["stale"])
        return
    if state.get("suggestion_busy") or state.get("feedback_busy"):
        await query.answer(words["busy"])
        return
    state["suggestion_busy"] = True
    progress = None
    more = InlineKeyboardMarkup([[
        InlineKeyboardButton(words["related_more"], callback_data=f"relatedmore:{anime_id}")
    ]])
    try:
        await query.answer()
        progress = await update.effective_message.reply_text(words["related_loading"])
        remember_message(state, "related_controls", (query.message.chat_id, progress.message_id), anime_id)
        async with aiohttp.ClientSession() as session:
            titles, items = await fetch_related_anime(session, anime_id)
            history_key = (query.message.chat_id, anime_id)
            # Bound per-user navigation history just like the remembered message controls.
            if history_key not in state.get("related_shown", {}):
                remember_message(state, "related_shown", history_key, set())
            shown = state["related_shown"][history_key]
            choices = [item for item in items if item["id"] not in state["seen_anime"] and item["id"] not in shown]
            if not choices:
                await progress.edit_text(words["related_none"])
                return
            batch = choices[:3]
            results = await asyncio.gather(*(
                deliver_anime(update, context, session, item, language, related=True) for item in batch
            ), return_exceptions=True)
            failures = []
            for item, result in zip(batch, results):
                if isinstance(result, BaseException):
                    failures.append(result)
                    logger.warning("Related suggestion failed: anime=%s (%s)", item["id"], type(result).__name__)
                else:
                    shown.add(item["id"])
            title = (titles.get("english") if language == "en" else None) or titles.get("romaji") or words["title_unknown"]
            text = words["related_heading"].format(title=truncate(clean_text(title), 140))
            if failures:
                text += "\n\n" + words["related_partial"]
            remaining = any(item["id"] not in shown for item in choices)
            await progress.edit_text(text, reply_markup=more if remaining else None)
    except (aiohttp.ClientError, asyncio.TimeoutError, TelegramError, ValueError, KeyError) as exc:
        logger.warning("Related lookup failed (%s)", type(exc).__name__)
        if progress:
            await progress.edit_text(words["unavailable"], reply_markup=more)
        else:
            await update.effective_message.reply_text(words["unavailable"])
    finally:
        state["suggestion_busy"] = False


async def handle_feedback(update, context):
    query = update.callback_query
    state = state_for(update, context)
    language = locale(state)
    words = TEXT[language]
    if query.data == "retry":
        await query.answer()
        await suggest_anime(update, context)
        return
    action, value = query.data.split(":", 1)
    anime_id = int(value)
    active = (query.message.chat_id, query.message.message_id, anime_id)
    if state.get("active_suggestion") != active and active not in state.get("related_cards", {}):
        await query.answer(words["stale"])
        return
    if state.get("suggestion_busy") or state.get("feedback_busy"):
        await query.answer(words["busy"])
        return
    state["feedback_busy"] = True
    genre = None
    if state.get("active_suggestion") == active:
        state.pop("active_suggestion", None)
        genre = state.pop("active_genre", None)
    state.get("related_cards", {}).pop(active, None)
    try:
        if action == "unseen" and not get_store().save_for_later(update.effective_user.id, anime_id):
            await query.answer(words["stale"])
            return
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(words["related"], callback_data=f"related:{anime_id}")
        ]]))
        if action == "seen":
            state["seen_anime"].add(anime_id)
            get_store().record(update.effective_user.id, anime_id, "seen")
        if action in {"seen", "next"}:
            if genre:
                await suggest_anime(update, context, genre=genre, previous=anime_id)
            else:
                await suggest_anime(update, context)
        else:
            await query.message.reply_text(words["saved"], reply_markup=menu(language))
    finally:
        state["feedback_busy"] = False


def watchlist_page(user_id, language, page=0):
    words = TEXT[language]
    items = get_store().saved_anime(user_id)
    if not items:
        return words["watchlist_empty"], InlineKeyboardMarkup([])
    pages = (len(items) + 7) // 8
    page = max(0, min(page, pages - 1))
    lines = [words["watchlist_heading"].format(page=page + 1, pages=pages)]
    buttons = []
    for number, (anime_id, title, english_title) in enumerate(items[page * 8:page * 8 + 8], start=page * 8 + 1):
        title = (english_title if language == "en" else None) or title
        lines.append(f"{number}. {truncate(clean_text(title), 140)}")
        buttons.append([
            InlineKeyboardButton(f"{number} · {words['seen']}", callback_data=f"wl:seen:{anime_id}:{page}"),
            InlineKeyboardButton(f"{number} · {words['remove']}", callback_data=f"wl:remove:{anime_id}:{page}"),
        ])
    navigation = []
    if page:
        navigation.append(InlineKeyboardButton(words["previous_page"], callback_data=f"wl:page:{page - 1}"))
    if page + 1 < pages:
        navigation.append(InlineKeyboardButton(words["next_page"], callback_data=f"wl:page:{page + 1}"))
    if navigation:
        buttons.append(navigation)
    return "\n\n".join(lines), InlineKeyboardMarkup(buttons)


async def show_watchlist(update, context):
    state = state_for(update, context)
    if state.get("language") not in TEXT:
        await choose_language(update.effective_message)
        return
    text, markup = watchlist_page(update.effective_user.id, locale(state))
    await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=None)


async def handle_watchlist(update, context):
    state = state_for(update, context)
    query = update.callback_query
    parts = query.data.split(":")
    page = int(parts[-1])
    removed = True
    if parts[1] in {"seen", "remove"}:
        anime_id = int(parts[2])
        removed = get_store().remove_saved(update.effective_user.id, anime_id, seen=parts[1] == "seen")
        if removed and parts[1] == "seen":
            state["seen_anime"].add(anime_id)
    await query.answer(None if removed else TEXT[locale(state)]["missing_saved"])
    text, markup = watchlist_page(update.effective_user.id, locale(state), page)
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode=None)
    except BadRequest as error:
        if "message is not modified" not in str(error).lower():
            raise


async def help_command(update, context):
    state = state_for(update, context)
    if state.get("language") not in TEXT:
        await choose_language(update.effective_message)
    else:
        await update.effective_message.reply_text(TEXT[locale(state)]["help"], reply_markup=menu(locale(state)))


def title_for(item, language):
    return clean_text((item.get("english_title") if language == "en" else None) or item.get("title") or str(item["id"]))


async def edit_text(query, text, markup):
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode=None)
    except BadRequest as error:
        if "message is not modified" not in str(error).lower():
            raise


async def search_command(update, context):
    state = state_for(update, context)
    if state.get("language") not in TEXT:
        await choose_language(update.effective_message)
        return
    search = " ".join(getattr(context, "args", []) or [])
    if search:
        await show_catalog(update, context, "search", search)
    else:
        state["awaiting_search"] = True
        await update.effective_message.reply_text(TEXT[locale(state)]["search_prompt"])


async def cancel_command(update, context):
    state = state_for(update, context)
    state.pop("awaiting_search", None)
    await update.effective_message.reply_text(TEXT[locale(state)]["cancelled"], reply_markup=menu(locale(state)))


async def top_command(update, context):
    await show_catalog(update, context, "top")


async def airing_command(update, context):
    await show_catalog(update, context, "airing")


async def show_catalog(update, context, mode, search=None, page=1, token=None):
    state = state_for(update, context)
    words = TEXT[locale(state)]
    query = getattr(update, "callback_query", None) if token else None
    if state.get("language") not in TEXT:
        await choose_language(update.effective_message)
        return
    if search is not None and not 2 <= len(search.strip()) <= 100:
        await update.effective_message.reply_text(words["search_short"])
        return
    if state.get("suggestion_busy"):
        if query:
            await query.answer(words["busy"])
        else:
            await update.effective_message.reply_text(words["busy"])
        return
    state["suggestion_busy"] = True
    progress = None
    try:
        if query:
            await query.answer()
        else:
            progress = await update.effective_message.reply_text(words["discover_loading"])
        async with aiohttp.ClientSession() as session:
            items, has_next = await fetch_catalog(session, mode, search, page,
                                                  get_store().preferences(update.effective_user.id))
        token = token or secrets.token_hex(4)
        label = search if mode == "search" else words[mode]
        text = words["results"].format(title=label, page=page) if items else words["no_results"]
        buttons = []
        for item in items:
            badge = "✅ " if item["id"] in state["seen_anime"] else ""
            score = f" · ⭐ {item['score']:.1f}" if item.get("score") is not None else ""
            buttons.append([InlineKeyboardButton(badge + truncate(title_for(item, locale(state)), 65) + score,
                                                callback_data=f"disc:open:{token}:{item['id']}")])
        navigation = []
        if page > 1:
            navigation.append(InlineKeyboardButton(words["previous_page"], callback_data=f"disc:page:{token}:{page - 1}"))
        if has_next and page < 100:
            navigation.append(InlineKeyboardButton(words["next_page"], callback_data=f"disc:page:{token}:{page + 1}"))
        if navigation:
            buttons.append(navigation)
        markup = InlineKeyboardMarkup(buttons)
        if query:
            await edit_text(query, text, markup)
            message = query.message
        else:
            await progress.edit_text(text, reply_markup=markup, parse_mode=None)
            message = progress
        remember_message(state, "catalogs", token, {"mode": mode, "search": search, "page": page,
                         "has_next": has_next, "items": {item["id"]: item for item in items},
                         "message": (update.effective_message.chat_id, message.message_id)}, limit=20)
        state.pop("awaiting_search", None)
    except (aiohttp.ClientError, asyncio.TimeoutError, TelegramError, ValueError, KeyError) as exc:
        logger.warning("Catalog failed (%s)", type(exc).__name__)
        if progress:
            await progress.edit_text(words["unavailable"])
        else:
            await update.effective_message.reply_text(words["unavailable"])
    finally:
        state["suggestion_busy"] = False


async def handle_catalog(update, context):
    state = state_for(update, context)
    query = update.callback_query
    _, action, token, raw_value = query.data.split(":")
    value = int(raw_value)
    catalog = state.get("catalogs", {}).get(token)
    words = TEXT[locale(state)]
    if not catalog or catalog["message"] != (query.message.chat_id, query.message.message_id):
        await query.answer(words["stale"])
        return
    if action == "page":
        valid = value == catalog["page"] - 1 or (value == catalog["page"] + 1 and catalog["has_next"])
        if not valid or not 1 <= value <= 100:
            await query.answer(words["stale"])
            return
        await show_catalog(update, context, catalog["mode"], catalog["search"], value, token)
        return
    anime = catalog["items"].get(value)
    if not anime:
        await query.answer(words["stale"])
        return
    if state.get("suggestion_busy"):
        await query.answer(words["busy"])
        return
    state["suggestion_busy"] = True
    try:
        await query.answer()
        async with aiohttp.ClientSession() as session:
            # Independent cards keep earlier search results and recommendation buttons usable.
            await deliver_anime(update, context, session, anime, locale(state), related=True)
    except (TranslationUnavailable, CoverUnavailable, aiohttp.ClientError, asyncio.TimeoutError, TelegramError, ValueError, KeyError) as exc:
        key = "translation_failed" if isinstance(exc, TranslationUnavailable) else "photo_failed" if isinstance(exc, CoverUnavailable) else "unavailable"
        logger.warning("Catalog card failed (%s)", type(exc).__name__)
        await query.message.reply_text(words[key])
    finally:
        state["suggestion_busy"] = False


def preferences_view(user_id, language):
    words = TEXT[language]
    prefs = get_store().preferences(user_id)
    genre = prefs["genre"]
    text = words["preferences"].format(genre=(GENRES.get(genre, genre) if language == "fa" else genre) or words["any"],
        score=f"{prefs['min_score'] / 10:g}/10" if prefs["min_score"] else words["any"],
        episodes=prefs["max_episodes"] or words["any"])
    buttons = [[InlineKeyboardButton(words["genre"], callback_data="pref:genre:choose")]]
    for field, label, values in (("min_score", "rating", (0, 70, 80, 90)), ("max_episodes", "length", (0, 12, 24, 50))):
        buttons.append([InlineKeyboardButton(("✓ " if prefs[field] == value else "") +
            (words["any"] if not value else (f"{value / 10:g}⭐" if field == "min_score" else f"{value} 📺")),
            callback_data=f"pref:{field}:{value}") for value in values])
    buttons.append([InlineKeyboardButton(words["reset"], callback_data="pref:reset:0"),
                    InlineKeyboardButton(words["done"], callback_data="pref:done:0")])
    return text, InlineKeyboardMarkup(buttons)


async def settings_command(update, context):
    state = state_for(update, context)
    if state.get("language") not in TEXT:
        await choose_language(update.effective_message)
        return
    state.pop("awaiting_search", None)
    text, markup = preferences_view(update.effective_user.id, locale(state))
    sent = await update.effective_message.reply_text(text, reply_markup=markup)
    remember_message(state, "settings_controls", (update.effective_message.chat_id, sent.message_id), True, limit=10)


async def handle_preferences(update, context):
    state = state_for(update, context)
    query = update.callback_query
    words = TEXT[locale(state)]
    if (query.message.chat_id, query.message.message_id) not in state.get("settings_controls", {}):
        await query.answer(words["stale"])
        return
    if state.get("suggestion_busy"):
        await query.answer(words["busy"])
        return
    _, field, value = query.data.split(":")
    await query.answer()
    if field == "genre" and value == "choose":
        choices = [(words["any"], "any")] + [(GENRES[g] if locale(state) == "fa" else g, str(i)) for i, g in enumerate(GENRES)]
        buttons = [[InlineKeyboardButton(label, callback_data=f"pref:genre:{key}") for label, key in choices[i:i + 2]]
                   for i in range(0, len(choices), 2)]
        await edit_text(query, words["genre"], InlineKeyboardMarkup(buttons))
        return
    user_id = update.effective_user.id
    if field == "reset":
        for name, default in (("genre", None), ("min_score", 0), ("max_episodes", 0)):
            get_store().set_preference(user_id, name, default)
    elif field == "genre" and (value == "any" or (value.isdigit() and int(value) < len(GENRES))):
        get_store().set_preference(user_id, field, None if value == "any" else list(GENRES)[int(value)])
    elif field in {"min_score", "max_episodes"} and value.isdigit():
        allowed = {0, 70, 80, 90} if field == "min_score" else {0, 12, 24, 50}
        if int(value) not in allowed:
            return
        get_store().set_preference(user_id, field, int(value))
    elif field == "done":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(words["done"], reply_markup=menu(locale(state)))
        return
    else:
        return
    state.pop("retry_anime", None)
    text, markup = preferences_view(user_id, locale(state))
    await edit_text(query, text, markup)


def history_page(user_id, language, page=0):
    words = TEXT[language]
    items = get_store().watched(user_id)
    if not items:
        return words["history_empty"], InlineKeyboardMarkup([])
    pages = (len(items) + 7) // 8
    page = max(0, min(page, pages - 1))
    lines = [words["history_heading"].format(page=page + 1, pages=pages)]
    buttons = []
    for number, (anime_id, title, english) in enumerate(items[page * 8:page * 8 + 8], start=page * 8 + 1):
        lines.append(f"{number}. {truncate(clean_text((english if language == 'en' else None) or title or str(anime_id)), 140)}")
        buttons.append([InlineKeyboardButton(f"{number} · {words['undo']}", callback_data=f"hist:undo:{anime_id}:{page}")])
    nav = []
    if page:
        nav.append(InlineKeyboardButton(words["previous_page"], callback_data=f"hist:page:{page - 1}"))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton(words["next_page"], callback_data=f"hist:page:{page + 1}"))
    if nav:
        buttons.append(nav)
    return "\n\n".join(lines), InlineKeyboardMarkup(buttons)


async def history_command(update, context):
    state = state_for(update, context)
    if state.get("language") not in TEXT:
        await choose_language(update.effective_message)
        return
    text, markup = history_page(update.effective_user.id, locale(state))
    sent = await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=None)
    remember_message(state, "history_controls", (update.effective_message.chat_id, sent.message_id), True, limit=10)


async def handle_history(update, context):
    state = state_for(update, context)
    query = update.callback_query
    if (query.message.chat_id, query.message.message_id) not in state.get("history_controls", {}):
        await query.answer(TEXT[locale(state)]["stale"])
        return
    parts = query.data.split(":")
    if parts[1] == "undo":
        anime_id = int(parts[2])
        if get_store().undo_seen(update.effective_user.id, anime_id):
            state["seen_anime"].discard(anime_id)
    await query.answer()
    text, markup = history_page(update.effective_user.id, locale(state), int(parts[-1]))
    await edit_text(query, text, markup)


async def stats_command(update, context):
    state = state_for(update, context)
    if state.get("language") not in TEXT:
        await choose_language(update.effective_message)
        return
    words = TEXT[locale(state)]
    data = get_store().load_user(update.effective_user.id)
    text = words["profile"].format(seen=len(data["seen_anime"]), shown=len(data["shown_anime"]),
                                   saved=len(get_store().saved_anime(update.effective_user.id)))
    await update.effective_message.reply_text(text, reply_markup=menu(locale(state)))


async def export_command(update, context):
    state = state_for(update, context)
    if state.get("language") not in TEXT:
        await choose_language(update.effective_message)
        return
    user_id = update.effective_user.id
    store = get_store()
    def entries(rows):
        return [dict(zip(("id", "title", "english_title"), row)) for row in rows]
    data = {"version": 1, "language": locale(state), "preferences": store.preferences(user_id),
            "watchlist": entries(store.saved_anime(user_id)), "watched": entries(store.watched(user_id))}
    document = InputFile(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"), filename="my-anime-lists.json")
    await update.effective_message.reply_document(document, caption=TEXT[locale(state)]["export_caption"])


async def handle_text(update, context):
    state = state_for(update, context)
    text = re.sub(r"\s+", " ", update.effective_message.text.replace("\u200c", " ").strip())
    actions = {"search": search_command, "genre_pick": genre_command, "top": top_command, "airing": airing_command,
               "settings": settings_command, "history": history_command, "stats": stats_command}
    for key, handler in actions.items():
        if text in {re.sub(r"\s+", " ", TEXT[lang][key].replace("\u200c", " ")) for lang in TEXT}:
            state.pop("awaiting_search", None)
            if key == "search":
                state["awaiting_search"] = True
                await update.effective_message.reply_text(TEXT[locale(state)]["search_prompt"])
            else:
                await handler(update, context)
            return
    if text in {TEXT["fa"]["language"], TEXT["en"]["language"], "🌐 زبان / Language"}:
        state.pop("awaiting_search", None)
        await choose_language(update.effective_message)
    elif text in {TEXT["fa"]["suggest"], TEXT["en"]["suggest"], "چی ببینم", "چی ببینم؟", "چی ببینم?", "What should I watch?"}:
        state.pop("awaiting_search", None)
        await suggest_anime(update, context)
    elif text in {TEXT["fa"]["watchlist"], TEXT["en"]["watchlist"]}:
        state.pop("awaiting_search", None)
        await show_watchlist(update, context)
    else:
        await show_catalog(update, context, "search", text)


async def language_command(update, context):
    state_for(update, context)
    await choose_language(update.effective_message)


async def on_error(update, context):
    # Exception strings may contain Telegram URLs; log only the type.
    logger.error("Update failed (%s)", type(context.error).__name__)
    if update and update.effective_message:
        state = state_for(update, context)
        try:
            await update.effective_message.reply_text(TEXT[locale(state)]["unavailable"])
        except TelegramError:
            pass


async def register_commands(app):
    descriptions = {
        "en": {"start": "Start and choose language", "suggest": "Get a recommendation", "search": "Search by anime title",
               "genre": "Pick a genre for a random anime", "top": "Browse top-rated anime", "airing": "Browse anime airing now", "settings": "Set genre, rating and length",
               "watchlist": "Your watch-later list", "history": "Watched anime and undo", "stats": "Your anime stats",
               "export": "Download your anime lists", "language": "Change language", "cancel": "Cancel search", "help": "Show help"},
        "fa": {"start": "شروع و انتخاب زبان", "suggest": "پیشنهاد انیمه", "search": "جستجوی اسم انیمه", "top": "انیمه‌های برتر",
               "genre": "پیشنهاد تصادفی بر اساس ژانر", "airing": "انیمه‌های در حال پخش", "settings": "تنظیم ژانر، امتیاز و تعداد قسمت", "watchlist": "لیست تماشای من",
               "history": "دیده‌شده‌ها و لغو ثبت", "stats": "آمار من", "export": "دانلود لیست‌ها", "language": "تغییر زبان",
               "cancel": "خروج از جستجو", "help": "راهنما"},
    }
    for language_code in (None, "fa", "en"):
        values = descriptions[language_code or "en"]
        try:
            await app.bot.set_my_commands([BotCommand(command, label) for command, label in values.items()], language_code=language_code)
        except TelegramError as exc:
            logger.warning("Command menu registration failed (%s)", type(exc).__name__)


def build_application():
    if not TOKEN:
        raise ValueError("Set TELEGRAM_BOT_TOKEN in AnimeBot/.env")
    builder = (Application.builder().token(TOKEN).concurrent_updates(16).post_init(register_commands)
               .connect_timeout(20).read_timeout(40).write_timeout(40)
               .get_updates_connect_timeout(20).get_updates_read_timeout(40))
    proxy = os.getenv("TELEGRAM_PROXY_URL", "").strip()
    if proxy:
        builder = builder.proxy(proxy).get_updates_proxy(proxy)
        logger.info("Telegram proxy enabled")
    app = builder.build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("suggest", suggest_anime))
    app.add_handler(CommandHandler("watchlist", show_watchlist))
    for command, handler in {"search": search_command, "genre": genre_command, "top": top_command, "airing": airing_command,
                             "settings": settings_command, "history": history_command, "stats": stats_command,
                             "export": export_command, "cancel": cancel_command}.items():
        app.add_handler(CommandHandler(command, handler))
    app.add_handler(CallbackQueryHandler(handle_genre, pattern=r"^genre:(?:[0-9]{1,2}|retry)$"))
    app.add_handler(CallbackQueryHandler(handle_catalog, pattern=r"^disc:(?:open|page):[0-9a-f]{8}:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_preferences, pattern=r"^pref:(?:genre|min_score|max_episodes|reset|done):[a-z0-9]+$"))
    app.add_handler(CallbackQueryHandler(handle_history, pattern=r"^hist:(?:page:\d+|undo:\d+:\d+)$"))
    app.add_handler(CallbackQueryHandler(handle_watchlist, pattern=r"^wl:(?:page:\d+|(?:seen|remove):\d+:\d+)$"))
    app.add_handler(CallbackQueryHandler(set_language, pattern=r"^lang:(fa|en)$"))
    app.add_handler(CallbackQueryHandler(show_related, pattern=r"^related(?:more)?:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_feedback, pattern=r"^(?:(seen|unseen|next):\d+|retry)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(on_error)
    return app


def main():
    get_store()
    app = build_application()
    logger.info("Anime bot starting")
    app.run_polling(allowed_updates=["message", "callback_query"], bootstrap_retries=3)


if __name__ == "__main__":
    main()
