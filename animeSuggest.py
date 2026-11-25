"""Bilingual Telegram anime recommendations with real covers and Persian summaries."""
import asyncio
import hashlib
import html
import logging
import os
import random
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, ReplyKeyboardMarkup, Update
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
        "suggest": "🎲 چی ببینم؟", "language": "🌐 تغییر زبان", "seen": "✅ دیدم", "unseen": "🍿 ندیدم",
        "next": "🎲 پیشنهاد بعدی", "loading": "🎬 دارم پیشنهادت رو با عکس و خلاصهٔ فارسی آماده می‌کنم…",
        "related": "🔎 انیمه‌های مرتبط", "related_more": "🔎 موارد مرتبط بیشتر",
        "related_loading": "🔎 دارم انیمه‌های مرتبط رو با عکس و توضیحات آماده می‌کنم…",
        "related_heading": "🔎 انیمه‌های مرتبط با «{title}»",
        "related_none": "فعلاً انیمهٔ مرتبط تازه‌ای برای نمایش پیدا نشد.",
        "related_partial": "بعضی پیشنهادهای مرتبط آماده نشدن؛ برای ادامه یا تلاش دوباره دکمهٔ زیر رو بزن.",
        "same_series": "🧩 از همین مجموعه", "similar_anime": "✨ انیمهٔ مشابه",
        "busy": "یه لحظه؛ دارم پیشنهادت رو آماده می‌کنم…", "stale": "این پیشنهاد دیگه فعال نیست؛ یه پیشنهاد تازه بگیر.",
        "picked": "🍿 پس این رو بذار برای تماشا!\nهر وقت خواستی، می‌تونی پیشنهاد بعدی رو بگیری.",
        "empty": "همهٔ انیمه‌های برترِ این فهرست رو دیدی! بعداً برای فهرست تازه برگرد.",
        "unavailable": "دریافت پیشنهاد فعلاً ممکن نشد. اتصال اینترنت و Xray رو بررسی کن و دوباره تلاش کن.",
        "translation_failed": "ترجمهٔ فارسی این خلاصه فعلاً آماده نشد. دوباره تلاش کن؛ متن انگلیسی جایگزین نمی‌شه.",
        "photo_failed": "عکس این انیمه دانلود نشد. دوباره تلاش کن تا پیشنهاد همراه عکس ارسال بشه.",
        "retry": "🔄 تلاش دوباره", "score": "امتیاز", "episodes": "قسمت‌های این فصل", "seasons": "فصل‌ها / بخش‌های تلویزیونی",
        "synopsis": "خلاصه داستان", "not_announced": "هنوز اعلام نشده", "unknown_value": "نامشخص",
        "at_least": "حداقل {count}؛ اطلاعات کامل نیست", "no_synopsis": "هنوز خلاصه‌ای برای این انیمه منتشر نشده است.",
        "title_unknown": "عنوان نامشخص",
        "season_synopsis_pending": "این انیمه ادامهٔ مجموعه است؛ خلاصهٔ کامل داستان این فصل هنوز منتشر نشده است.",
        "help": "🎲 پیشنهاد تصادفی از انیمه‌های برترِ ترند\n✅ دیدم: پیشنهاد بعدی\n🍿 ندیدم: انتخاب برای تماشا\n/language تغییر زبان\n/start شروع دوباره\n\nتعداد قسمت مربوط به فصل پیشنهادی است؛ فصل‌ها از بخش‌های تلویزیونی مرتبط شمرده می‌شوند.",
    },
    "en": {
        "welcome": "Hi! 👋\nI'll pick a random anime from the highest-rated trending shows.\nAlready watched it? Tap ‘Seen’ for another suggestion.",
        "suggest": "🎲 What should I watch?", "language": "🌐 Change language", "seen": "✅ Seen", "unseen": "🍿 Haven’t seen it",
        "next": "🎲 Next suggestion", "loading": "🎬 Finding your anime, cover and synopsis…",
        "related": "🔎 Related anime", "related_more": "🔎 More related anime",
        "related_loading": "🔎 Finding related anime, covers and synopses…",
        "related_heading": "🔎 Anime related to ‘{title}’",
        "related_none": "No new related anime are available to show right now.",
        "related_partial": "Some related picks couldn't be prepared. Tap below to continue or try again.",
        "same_series": "🧩 From the same series", "similar_anime": "✨ Similar anime",
        "busy": "One moment; your suggestion is on its way…", "stale": "This suggestion is no longer active. Get a new one.",
        "picked": "🍿 Save this one for your next watch!\nYou can ask for another suggestion whenever you like.",
        "empty": "You've watched every top anime in this list! Come back later for a refreshed list.",
        "unavailable": "Couldn't load a suggestion. Check your internet connection and Xray, then try again.",
        "translation_failed": "The translated synopsis is temporarily unavailable. Please try again.",
        "photo_failed": "Couldn't download this anime's cover. Please try again.",
        "retry": "🔄 Try again", "score": "Rating", "episodes": "Episodes in this season", "seasons": "Seasons / TV parts",
        "synopsis": "Synopsis", "not_announced": "Not announced yet", "unknown_value": "Unknown",
        "at_least": "At least {count}; incomplete data", "no_synopsis": "No synopsis has been published for this anime yet.",
        "title_unknown": "Unknown title",
        "season_synopsis_pending": "This is a continuation of the series. A full plot synopsis for this season has not been published yet.",
        "help": "🎲 Random picks from the highest-rated trending anime\n✅ Seen: get another suggestion\n🍿 Haven’t seen it: keep this pick\n/language change language\n/start start again\n\nEpisode counts apply to the suggested season. Seasons count related TV parts, including split seasons.",
    },
}


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

    def reset_shown(self, user_id):
        with self.db:
            self.db.execute("DELETE FROM history WHERE user_id=? AND status!='seen'", (user_id,))

    def translation(self, source_hash):
        row = self.db.execute("SELECT text FROM translations WHERE source_hash=?", (source_hash,)).fetchone()
        return row[0] if row else None

    def save_translation(self, source_hash, text):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO translations VALUES (?,?)", (source_hash, text))


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
    return ReplyKeyboardMarkup([[TEXT[language]["suggest"]], [TEXT[language]["language"]]], resize_keyboard=True)


def language_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
        InlineKeyboardButton("🇮🇷 فارسی", callback_data="lang:fa"),
    ]])


async def choose_language(message):
    await message.reply_text("🌐 زبانت رو انتخاب کن:\nChoose your language:", reply_markup=language_keyboard())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state_for(update, context)
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
    state.pop("retry_anime", None)
    for key in ("related_cards", "related_origins", "related_controls", "related_shown"):
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
    key = (query, tuple(sorted(variables.items())))
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
    }


async def fetch_anime_data(session):
    payload = await anilist_query(session, """
        { Page(perPage:50) {
            media(type:ANIME, format:TV, sort:TRENDING_DESC, isAdult:false) {
                id title { romaji english } averageScore episodes description(asHtml:false)
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
            id type format isAdult title { romaji english } averageScore episodes description(asHtml:false)
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
    pending = [(anime["id"], "TV")]
    discovered = {anime["id"]: "TV"}
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
    if sent.photo:
        _photo_ids[anime["id"]] = sent.photo[-1].file_id
    logger.info("Suggestion delivered: anime=%s language=%s related=%s", anime["id"], language, related)
    return sent


async def suggest_anime(update, context):
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
    progress = None
    try:
        progress = await message.reply_text(words["loading"])
        async with aiohttp.ClientSession() as session:
            pool = await fetch_anime_data(session)
            choices = [item for item in pool if item["id"] not in state["seen_anime"] and item["id"] not in state["shown_anime"]]
            if not choices:
                choices = [item for item in pool if item["id"] not in state["seen_anime"]]
                if choices:
                    state["shown_anime"].clear()
                    get_store().reset_shown(update.effective_user.id)
            if not choices:
                await progress.edit_text(words["empty"] if pool else words["unavailable"])
                return
            pending = state.get("retry_anime")
            anime = next((item for item in choices if item["id"] == pending), None) or random.choice(choices)
            state["retry_anime"] = anime["id"]
            await deliver_anime(update, context, session, anime, language)
        try:
            await progress.delete()
        except TelegramError:
            pass
    except (TranslationUnavailable, CoverUnavailable, aiohttp.ClientError, asyncio.TimeoutError, TelegramError, ValueError, KeyError) as exc:
        key = "translation_failed" if isinstance(exc, TranslationUnavailable) else "photo_failed" if isinstance(exc, CoverUnavailable) else "unavailable"
        logger.warning("Suggestion failed (%s)", type(exc).__name__)
        if progress:
            await progress.edit_text(words[key], reply_markup=retry_keyboard(language))
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
    if state.get("active_suggestion") == active:
        state.pop("active_suggestion", None)
    state.get("related_cards", {}).pop(active, None)
    try:
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(words["related"], callback_data=f"related:{anime_id}")
        ]]))
        if action == "seen":
            state["seen_anime"].add(anime_id)
            get_store().record(update.effective_user.id, anime_id, "seen")
        if action in {"seen", "next"}:
            await suggest_anime(update, context)
        else:
            await query.message.reply_text(words["picked"], reply_markup=menu(language))
    finally:
        state["feedback_busy"] = False


async def help_command(update, context):
    state = state_for(update, context)
    if state.get("language") not in TEXT:
        await choose_language(update.effective_message)
    else:
        await update.effective_message.reply_text(TEXT[locale(state)]["help"], reply_markup=menu(locale(state)))


async def handle_text(update, context):
    state_for(update, context)
    text = re.sub(r"\s+", " ", update.effective_message.text.replace("\u200c", " ").strip())
    if text in {TEXT["fa"]["language"], TEXT["en"]["language"], "🌐 زبان / Language"}:
        await choose_language(update.effective_message)
    elif text in {TEXT["fa"]["suggest"], TEXT["en"]["suggest"], "چی ببینم", "چی ببینم؟", "چی ببینم?", "What should I watch?"}:
        await suggest_anime(update, context)
    else:
        await help_command(update, context)


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


def build_application():
    if not TOKEN:
        raise ValueError("Set TELEGRAM_BOT_TOKEN in AnimeBot/.env")
    builder = (Application.builder().token(TOKEN).concurrent_updates(16)
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
