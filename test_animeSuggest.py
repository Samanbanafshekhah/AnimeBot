"""Offline tests: .venv/bin/python -m unittest test_animeSuggest.py"""
import asyncio
import hashlib
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from telegram.error import BadRequest
import animeSuggest as bot


FA = "یک قهرمان جوان به دنبال دوست گمشده‌اش می‌گردد و با ماجراهای تازه روبه‌رو می‌شود."


def anime(anime_id=1):
    return {"id": anime_id, "title": f"Anime {anime_id}", "english_title": f"English {anime_id}",
            "score": 8.5, "episodes": 12, "synopsis": "A young hero searches for his lost friend.",
            "cover": "https://example.test/cover.jpg", "relations": {"edges": []}}


def response(payload, status=200, content_type="application/json", chunks=None):
    result = SimpleNamespace(status=status, json=AsyncMock(return_value=payload),
                             raise_for_status=MagicMock(), headers={"Content-Type": content_type})
    async def stream(size):
        for chunk in chunks or []:
            yield chunk
    result.content = SimpleNamespace(iter_chunked=stream)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=result)
    manager.__aexit__ = AsyncMock(return_value=False)
    return manager


class BotCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = bot.Store(":memory:")
        self.store_patch = patch.object(bot, "_store", self.store)
        self.store_patch.start()
        bot._cache.clear()
        bot._photo_ids.clear()
        bot._translation_locks.clear()
        bot._translation_cooldowns.clear()
        bot._request_lock = asyncio.Lock()
        self.progress = SimpleNamespace(message_id=30, edit_text=AsyncMock(), delete=AsyncMock())
        self.sent = SimpleNamespace(message_id=20, photo=[SimpleNamespace(file_id="telegram-file-id")])
        self.message = SimpleNamespace(chat_id=100, message_id=10, text="چی ببینم؟",
            reply_text=AsyncMock(return_value=self.progress), reply_photo=AsyncMock(return_value=self.sent))
        self.update = SimpleNamespace(effective_user=SimpleNamespace(id=1), effective_message=self.message)
        self.context = SimpleNamespace(user_data={})

    def tearDown(self):
        self.store_patch.stop()
        self.store.db.close()

    def language(self, language="fa"):
        self.store.language(1, language)

    def network(self, pool=None, translation=FA):
        stack = ExitStack()
        stack.enter_context(patch.object(bot, "fetch_anime_data", AsyncMock(return_value=pool or [anime(1), anime(2)])))
        stack.enter_context(patch.object(bot, "translate_synopsis", AsyncMock(return_value=translation)))
        stack.enter_context(patch.object(bot, "count_seasons", AsyncMock(return_value=bot.SeasonCount(2))))
        stack.enter_context(patch.object(bot, "download_cover", AsyncMock(return_value=b"jpeg bytes")))
        return stack

    def feedback(self, action, anime_id):
        query = SimpleNamespace(data=f"{action}:{anime_id}", message=SimpleNamespace(
            chat_id=100, message_id=20, reply_text=self.message.reply_text),
            answer=AsyncMock(), edit_message_reply_markup=AsyncMock())
        self.update.callback_query = query
        return query


class BotTests(BotCase):
    async def test_start_asks_for_both_flagged_languages(self):
        await bot.start(self.update, self.context)
        buttons = self.message.reply_text.call_args.kwargs["reply_markup"].inline_keyboard[0]
        self.assertEqual([b.text for b in buttons], ["🇬🇧 English", "🇮🇷 فارسی"])
        self.message.reply_photo.assert_not_awaited()

    async def test_no_recommendation_before_language_choice(self):
        with patch.object(bot, "fetch_anime_data", AsyncMock()) as fetch:
            await bot.suggest_anime(self.update, self.context)
        fetch.assert_not_awaited()
        self.message.reply_photo.assert_not_awaited()
        self.assertIn("Choose your language", self.message.reply_text.call_args.args[0])

    async def test_language_choice_is_saved_and_localizes_menu(self):
        query = self.feedback("lang", "en")
        await bot.set_language(self.update, self.context)
        self.assertEqual(self.store.load_user(1)["language"], "en")
        markup = query.message.reply_text.call_args.kwargs["reply_markup"]
        self.assertEqual(markup.keyboard[0][0].text, "🎲 What should I watch?")

    async def test_farsi_sends_photo_with_caption_and_no_website_link(self):
        self.language()
        with self.network():
            await bot.suggest_anime(self.update, self.context)
        kwargs = self.message.reply_photo.call_args.kwargs
        self.assertIn(FA, kwargs["caption"])
        self.assertIn("8.5/10", kwargs["caption"])
        self.assertNotIn("http", kwargs["caption"])
        self.assertFalse(kwargs["show_caption_above_media"])
        self.assertIn("دیدم", kwargs["reply_markup"].inline_keyboard[0][0].text)
        self.progress.delete.assert_awaited_once()
        self.assertEqual(len(self.store.load_user(1)["shown_anime"]), 1)

    async def test_english_card_and_buttons_are_english(self):
        self.language("en")
        with self.network(translation="An English synopsis."):
            await bot.suggest_anime(self.update, self.context)
        kwargs = self.message.reply_photo.call_args.kwargs
        self.assertIn("Synopsis", kwargs["caption"])
        self.assertIn("English", kwargs["caption"])
        self.assertEqual(kwargs["reply_markup"].inline_keyboard[0][0].text, "✅ Seen")

    async def test_seen_suggests_another_and_unseen_keeps_pick(self):
        self.language()
        with self.network():
            await bot.suggest_anime(self.update, self.context)
            first = self.context.user_data["active_suggestion"][2]
            self.feedback("seen", first)
            await bot.handle_feedback(self.update, self.context)
            second = self.context.user_data["active_suggestion"][2]
            self.assertNotEqual(first, second)
            self.assertIn(first, self.store.load_user(1)["seen_anime"])
            self.feedback("unseen", second)
            before = self.message.reply_photo.await_count
            await bot.handle_feedback(self.update, self.context)
            self.assertEqual(self.message.reply_photo.await_count, before)
            self.assertNotIn("active_suggestion", self.context.user_data)

    async def test_stale_button_does_not_change_history(self):
        self.language()
        query = self.feedback("seen", 100)
        await bot.handle_feedback(self.update, self.context)
        query.edit_message_reply_markup.assert_not_awaited()
        self.assertEqual(self.store.load_user(1)["seen_anime"], set())

    async def test_busy_feedback_keeps_active_card(self):
        self.language()
        state = bot.state_for(self.update, self.context)
        state.update(active_suggestion=(100, 20, 1), suggestion_busy=True)
        query = self.feedback("seen", 1)
        await bot.handle_feedback(self.update, self.context)
        self.assertEqual(state["active_suggestion"], (100, 20, 1))
        query.edit_message_reply_markup.assert_not_awaited()

    async def test_translation_failure_never_sends_english_card_and_can_retry(self):
        self.language()
        with self.network():
            with patch.object(bot, "translate_synopsis", AsyncMock(side_effect=bot.TranslationUnavailable())):
                await bot.suggest_anime(self.update, self.context)
            self.message.reply_photo.assert_not_awaited()
            self.assertIn("ترجمهٔ فارسی", self.progress.edit_text.call_args.args[0])
            self.assertFalse(self.context.user_data["suggestion_busy"])
            pending = self.context.user_data["retry_anime"]
            self.assertEqual(self.store.load_user(1)["shown_anime"], set())
            await bot.suggest_anime(self.update, self.context)
            self.assertEqual(self.context.user_data["active_suggestion"][2], pending)

    async def test_photo_failure_does_not_mark_suggestion_as_delivered(self):
        self.language()
        with self.network(), patch.object(bot, "download_cover", AsyncMock(side_effect=bot.CoverUnavailable())):
            await bot.suggest_anime(self.update, self.context)
        self.message.reply_photo.assert_not_awaited()
        self.assertEqual(self.store.load_user(1)["shown_anime"], set())
        self.assertIn("عکس", self.progress.edit_text.call_args.args[0])

    async def test_expired_telegram_photo_id_downloads_and_resends_cover(self):
        self.language()
        bot._photo_ids[1] = "old-file-id"
        self.message.reply_photo.side_effect = [BadRequest("Invalid file id"), self.sent]
        with self.network(pool=[anime(1)]), patch.object(bot, "download_cover", AsyncMock(return_value=b"image")) as download:
            await bot.suggest_anime(self.update, self.context)
        download.assert_awaited_once()
        self.assertEqual(self.message.reply_photo.await_count, 2)
        self.assertEqual(bot._photo_ids[1], "telegram-file-id")

    async def test_seen_history_is_excluded_after_restart(self):
        self.language()
        self.store.record(1, 1, "seen")
        with self.network():
            await bot.suggest_anime(self.update, self.context)
        self.assertEqual(self.context.user_data["active_suggestion"][2], 2)

    async def test_exhausted_shown_cycle_preserves_seen_history(self):
        self.language()
        self.store.record(1, 1, "seen")
        self.store.record(1, 2, "shown")
        with self.network():
            await bot.suggest_anime(self.update, self.context)
        self.assertEqual(self.context.user_data["active_suggestion"][2], 2)
        self.assertIn(1, self.store.load_user(1)["seen_anime"])

    async def test_all_seen_shows_localized_exhaustion(self):
        self.language("en")
        self.store.record(1, 1, "seen")
        with self.network(pool=[anime(1)]):
            await bot.suggest_anime(self.update, self.context)
        self.message.reply_photo.assert_not_awaited()
        self.assertIn("watched every", self.progress.edit_text.call_args.args[0])

    async def test_english_summary_needs_no_translation_service(self):
        session = SimpleNamespace(get=MagicMock())
        self.assertEqual(await bot.translate_synopsis(session, "An English plot.", "en"), "An English plot.")
        session.get.assert_not_called()

    async def test_season_placeholder_is_explained_in_persian_without_fake_plot(self):
        session = SimpleNamespace(get=MagicMock())
        text = await bot.translate_synopsis(session, "The third season of Mushoku Tensei.", "fa")
        self.assertTrue(bot.is_persian(text))
        self.assertIn("منتشر نشده", text)
        self.assertNotIn("The third", text)
        session.get.assert_not_called()

    async def test_language_cannot_change_halfway_through_a_suggestion(self):
        self.language()
        state = bot.state_for(self.update, self.context)
        state["suggestion_busy"] = True
        query = self.feedback("lang", "en")
        await bot.set_language(self.update, self.context)
        self.assertEqual(self.store.load_user(1)["language"], "fa")
        query.edit_message_reply_markup.assert_not_awaited()

    async def test_translation_uses_other_route_after_quota_error(self):
        session = SimpleNamespace(get=MagicMock(side_effect=[
            response({"responseStatus": 429, "quotaFinished": True}),
            response({"responseStatus": 200, "responseData": {"translatedText": FA}}),
        ]))
        with patch.object(bot, "proxy_url", return_value="http://127.0.0.1:10808"):
            self.assertEqual(await bot.translate_synopsis(session, "A story about two friends.", "fa"), FA)
        self.assertEqual(session.get.call_count, 2)

    async def test_anilist_transient_failure_retries_and_then_caches(self):
        session = SimpleNamespace(post=MagicMock(side_effect=[
            response({}, status=503), response({"data": {"Page": {"media": []}}}),
        ]))
        with patch.object(bot.asyncio, "sleep", AsyncMock()):
            first = await bot.anilist_query(session, "test-query")
            second = await bot.anilist_query(session, "test-query")
        self.assertEqual(first, second)
        self.assertEqual(session.post.call_count, 2)

    async def test_persian_translation_validated_and_cached(self):
        session = SimpleNamespace(get=MagicMock(return_value=response({
            "responseStatus": 200, "responseData": {"translatedText": FA}})))
        first = await bot.translate_synopsis(session, "An English story.", "fa")
        second = await bot.translate_synopsis(session, "An English story.", "fa")
        self.assertEqual(first, FA)
        self.assertEqual(second, FA)
        session.get.assert_called_once()

    async def test_quota_and_untranslated_responses_are_not_displayed(self):
        for payload in [
            {"responseStatus": 200, "quotaFinished": True, "responseData": {"translatedText": FA}},
            {"responseStatus": 200, "responseData": {"translatedText": "No translation available"}},
            {"responseStatus": 429},
        ]:
            session = SimpleNamespace(get=MagicMock(return_value=response(payload)))
            with self.assertRaises(bot.TranslationUnavailable):
                await bot.translate_synopsis(session, "A different story.", "fa")

    async def test_translation_network_failure_raises_instead_of_english_fallback(self):
        session = SimpleNamespace(get=MagicMock(side_effect=asyncio.TimeoutError()))
        with self.assertRaises(bot.TranslationUnavailable):
            await bot.translate_synopsis(session, "An English plot.", "fa")

    async def test_pool_sorts_deduplicates_and_requires_cover_and_score(self):
        def item(anime_id, score=80, cover=True):
            return {"id": anime_id, "title": {"romaji": "Title"}, "averageScore": score,
                    "coverImage": {"large": "https://example.test/image.jpg"} if cover else {},
                    "description": "A <b>story</b> (Source: Test)"}
        payload = {"Page": {"media": [item(1), item(2, 90), item(1), item(3, 0), item(4, cover=False)]}}
        with patch.object(bot, "anilist_query", AsyncMock(return_value=payload)):
            pool = await bot.fetch_anime_data(None)
        self.assertEqual([item["id"] for item in pool], [2, 1])
        self.assertEqual(pool[0]["score"], 9)
        self.assertEqual(pool[0]["synopsis"], "A story")

    async def test_season_count_follows_movie_bridge_and_ignores_cycles(self):
        def edge(kind, anime_id, fmt):
            return {"relationType": kind, "node": {"id": anime_id, "type": "ANIME", "format": fmt}}
        first = anime(1)
        first["relations"] = {"edges": [edge("SEQUEL", 2, "MOVIE")]}
        details = {
            2: {"relations": {"edges": [edge("PREQUEL", 1, "TV"), edge("SEQUEL", 3, "TV")]}},
            3: {"relations": {"edges": [edge("PREQUEL", 2, "MOVIE")]}},
        }
        async def query(session, query, **variables):
            return {"Media": details[variables["id"]]}
        with patch.object(bot, "anilist_query", query):
            self.assertEqual(await bot.count_seasons(None, first), bot.SeasonCount(2))

    async def test_missing_season_details_returns_honest_lower_bound(self):
        first = anime(1)
        first["relations"] = {"edges": [{"relationType": "SEQUEL", "node": {"id": 2, "type": "ANIME", "format": "TV"}}]}
        with patch.object(bot, "anilist_query", AsyncMock(side_effect=aiohttp.ClientError())):
            self.assertEqual(await bot.count_seasons(None, first), bot.SeasonCount(2, False))

    async def test_non_image_cover_response_is_rejected(self):
        session = SimpleNamespace(get=MagicMock(return_value=response({}, content_type="text/html")))
        with self.assertRaises(bot.CoverUnavailable):
            await bot.download_cover(session, anime(1))

    async def test_image_cover_bytes_downloaded(self):
        session = SimpleNamespace(get=MagicMock(return_value=response({}, content_type="image/jpeg", chunks=[b"abc", b"def"])))
        self.assertEqual(await bot.download_cover(session, anime(1)), b"abcdef")

    def test_caption_limits_emoji_utf16_and_removes_links(self):
        for language in ("fa", "en"):
            item = anime(1)
            item["title"] = "🎬" * 150
            item["english_title"] = "🎬" * 150
            caption = bot.format_suggestion(item, (FA + " 🎬 ") * 200 + " https://example.test/site", bot.SeasonCount(2, False), language)
            self.assertLessEqual(len(caption.encode("utf-16-le")) // 2, 1024)
            self.assertNotIn("https://", caption)
            self.assertNotIn("http://", caption)

    def test_translation_segment_stays_below_500_utf8_bytes(self):
        for text in ("A long sentence about a mysterious world. " * 100, "こんにちは世界 " * 100):
            self.assertLessEqual(len(bot.translation_segment(text).encode("utf-8")), 500)

    def test_unknown_fields_localized(self):
        item = anime(1)
        item.update(episodes=None, score=None)
        caption = bot.format_suggestion(item, FA, bot.SeasonCount(1), "fa")
        self.assertNotIn("None", caption)
        self.assertIn("هنوز اعلام نشده", caption)


class RelatedTests(BotCase):
    def prepare(self, language="fa"):
        self.language(language)
        state = bot.state_for(self.update, self.context)
        state["active_suggestion"] = (100, 20, 1)
        state["shown_anime"].add(1)
        self.feedback("related", 1)
        self.message.reply_photo.side_effect = [
            SimpleNamespace(message_id=i, photo=[SimpleNamespace(file_id=f"file-{i}")]) for i in range(21, 40)
        ]
        return state

    def related_pool(self):
        return [dict(anime(i), related_kind="similar_anime") for i in range(2, 7)]

    def fetch(self, items=None):
        return patch.object(bot, "fetch_related_anime", AsyncMock(return_value=(
            {"romaji": "Source Anime", "english": "Source English"}, items if items is not None else self.related_pool())))

    def test_each_language_has_related_button(self):
        for language, label in (("fa", "🔎 انیمه‌های مرتبط"), ("en", "🔎 Related anime")):
            buttons = [button for row in bot.feedback_keyboard(123, language).inline_keyboard for button in row]
            self.assertIn((label, "related:123"), [(b.text, b.callback_data) for b in buttons])

    async def test_fetch_combines_franchise_and_similar_without_duplicates_or_unsafe_entries(self):
        def item(item_id, **extra):
            result = {"id": item_id, "type": "ANIME", "format": "TV", "isAdult": False,
                      "title": {"romaji": f"Anime {item_id}"}, "averageScore": 80,
                      "coverImage": {"large": "https://example.test/image.jpg"}}
            result.update(extra)
            return result
        payload = {"Media": {"title": {"romaji": "Source"},
            "relations": {"edges": [
                {"relationType": "SEQUEL", "node": item(2)},
                {"relationType": "ADAPTATION", "node": item(10, type="MANGA")},
            ]},
            "recommendations": {"nodes": [
                {"mediaRecommendation": item(3)}, {"mediaRecommendation": item(2)},
                {"mediaRecommendation": item(1)}, {"mediaRecommendation": item(4, isAdult=True)},
                {"mediaRecommendation": item(5, format="MOVIE")},
                {"mediaRecommendation": item(6, type="MANGA")},
                {"mediaRecommendation": item(7, coverImage={})},
                {"mediaRecommendation": None}, None,
            ]}}}
        with patch.object(bot, "anilist_query", AsyncMock(return_value=payload)):
            titles, items = await bot.fetch_related_anime(None, 1)
        self.assertEqual(titles["romaji"], "Source")
        self.assertEqual([item["id"] for item in items], [2, 3])
        self.assertEqual([item["related_kind"] for item in items], ["same_series", "similar_anime"])

    async def test_empty_source_returns_empty_results(self):
        with patch.object(bot, "anilist_query", AsyncMock(return_value={"Media": None})):
            self.assertEqual(await bot.fetch_related_anime(None, 1), ({}, []))

    async def test_related_shows_three_photos_and_keeps_parent_card_active(self):
        state = self.prepare()
        with self.network(), self.fetch():
            await bot.show_related(self.update, self.context)
        self.assertEqual(self.message.reply_photo.await_count, 3)
        self.assertEqual(state["active_suggestion"], (100, 20, 1))
        self.assertEqual({key[2] for key in state["related_cards"]}, {2, 3, 4})
        self.assertEqual(state["related_shown"][(100, 1)], {2, 3, 4})
        for call in self.message.reply_photo.await_args_list:
            self.assertIn(FA, call.kwargs["caption"])
            self.assertNotIn("http", call.kwargs["caption"])
        self.assertEqual(self.progress.edit_text.call_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data,
                         "relatedmore:1")
        self.assertFalse(state["suggestion_busy"])

    async def test_more_related_keeps_source_and_does_not_repeat_delivered_titles(self):
        state = self.prepare()
        with self.network(), self.fetch() as fetch:
            await bot.show_related(self.update, self.context)
            query = self.feedback("relatedmore", 1)
            query.message.message_id = 30
            await bot.show_related(self.update, self.context)
            self.assertEqual(self.message.reply_photo.await_count, 5)
            self.assertEqual(state["related_shown"][(100, 1)], {2, 3, 4, 5, 6})
            self.assertIsNone(self.progress.edit_text.call_args.kwargs["reply_markup"])
            await bot.show_related(self.update, self.context)
        self.assertEqual(self.message.reply_photo.await_count, 5)
        self.assertEqual([call.args[1] for call in fetch.await_args_list], [1, 1, 1])

    async def test_seen_related_titles_are_filtered_out(self):
        self.store.record(1, 3, "seen")
        state = self.prepare()
        with self.network(), self.fetch():
            await bot.show_related(self.update, self.context)
        self.assertEqual(state["related_shown"][(100, 1)], {2, 4, 5})

    async def test_each_related_card_has_independent_feedback(self):
        state = self.prepare()
        with self.network(), self.fetch():
            await bot.show_related(self.update, self.context)
        card = next(card for card in state["related_cards"] if card[2] == 2)
        query = self.feedback("unseen", 2)
        query.message.message_id = card[1]
        await bot.handle_feedback(self.update, self.context)
        self.assertNotIn(card, state["related_cards"])
        self.assertEqual({key[2] for key in state["related_cards"]}, {3, 4})
        self.assertEqual(state["active_suggestion"], (100, 20, 1))

    async def test_related_remains_available_after_finishing_main_card(self):
        self.language()
        with self.network(pool=[anime(1)]):
            await bot.suggest_anime(self.update, self.context)
            query = self.feedback("unseen", 1)
            await bot.handle_feedback(self.update, self.context)
            self.assertNotIn("active_suggestion", self.context.user_data)
            retained = query.edit_message_reply_markup.call_args.kwargs["reply_markup"]
            self.assertEqual(retained.inline_keyboard[0][0].callback_data, "related:1")
            query.data = "related:1"
            with self.fetch():
                await bot.show_related(self.update, self.context)
        self.assertEqual(self.message.reply_photo.await_count, 4)
        self.assertEqual(self.context.user_data["related_shown"][(100, 1)], {2, 3, 4})

    def test_related_caption_stays_within_telegram_limit(self):
        for kind in ("same_series", "similar_anime"):
            item = dict(anime(1), related_kind=kind)
            caption = bot.format_suggestion(item, FA * 100, bot.SeasonCount(2, False), "fa")
            self.assertIn(bot.TEXT["fa"][kind], caption)
            self.assertLessEqual(len(caption.encode("utf-16-le")) // 2, 1024)

    async def test_seen_on_related_card_records_it_and_gets_next_suggestion(self):
        state = self.prepare()
        with self.network(pool=[anime(9)]), self.fetch():
            await bot.show_related(self.update, self.context)
            card = next(card for card in state["related_cards"] if card[2] == 2)
            query = self.feedback("seen", 2)
            query.message.message_id = card[1]
            await bot.handle_feedback(self.update, self.context)
        self.assertIn(2, self.store.load_user(1)["seen_anime"])
        self.assertEqual(state["active_suggestion"][2], 9)
        self.assertEqual({key[2] for key in state["related_cards"]}, {3, 4})

    async def test_partial_failure_keeps_successes_and_retries_only_missing_items(self):
        state = self.prepare()
        async def cover(session, item):
            if item["id"] == 3:
                raise bot.CoverUnavailable()
            return b"jpeg bytes"
        with self.network(), self.fetch(), patch.object(bot, "download_cover", AsyncMock(side_effect=cover)):
            await bot.show_related(self.update, self.context)
        self.assertEqual(state["related_shown"][(100, 1)], {2, 4})
        self.assertNotIn(3, self.store.load_user(1)["shown_anime"])
        self.assertIn(bot.TEXT["fa"]["related_partial"], self.progress.edit_text.call_args.args[0])
        self.assertEqual(self.message.reply_photo.await_count, 2)

    async def test_related_network_failure_offers_related_retry_and_releases_busy_flag(self):
        state = self.prepare()
        with patch.object(bot, "fetch_related_anime", AsyncMock(side_effect=asyncio.TimeoutError())):
            await bot.show_related(self.update, self.context)
        self.assertFalse(state["suggestion_busy"])
        self.assertEqual(state["active_suggestion"], (100, 20, 1))
        self.assertEqual(self.progress.edit_text.call_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data,
                         "relatedmore:1")

    async def test_related_empty_state_and_english_heading_are_localized(self):
        self.prepare("en")
        with self.network(translation="An English plot."), self.fetch():
            await bot.show_related(self.update, self.context)
        self.assertIn("Source English", self.progress.edit_text.call_args.args[0])
        for call in self.message.reply_photo.await_args_list:
            self.assertIn("Synopsis", call.kwargs["caption"])
        with self.fetch(items=[]):
            await bot.show_related(self.update, self.context)
        self.assertIn("No new related", self.progress.edit_text.call_args.args[0])

    async def test_stale_related_and_fake_more_callbacks_do_not_fetch(self):
        self.prepare()
        with self.fetch() as fetch:
            self.feedback("related", 999)
            await bot.show_related(self.update, self.context)
            self.feedback("relatedmore", 1)
            await bot.show_related(self.update, self.context)
        fetch.assert_not_awaited()

    async def test_related_busy_guard_does_not_start_duplicate_requests(self):
        state = self.prepare()
        state["suggestion_busy"] = True
        with self.fetch() as fetch:
            await bot.show_related(self.update, self.context)
        fetch.assert_not_awaited()
        self.assertEqual(self.update.callback_query.answer.call_args.args[0], bot.TEXT["fa"]["busy"])

    async def test_related_button_on_child_explores_that_child(self):
        state = self.prepare()
        with self.network(), self.fetch():
            await bot.show_related(self.update, self.context)
        card = next(card for card in state["related_cards"] if card[2] == 2)
        query = self.feedback("related", 2)
        query.message.message_id = card[1]
        with self.network(), self.fetch(items=[anime(7)]) as fetch:
            await bot.show_related(self.update, self.context)
        self.assertEqual(fetch.await_args.args[1], 2)
        self.assertEqual(state["related_shown"][(100, 2)], {7})


class PersistenceTests(unittest.TestCase):
    def test_store_survives_reopen_and_separates_users(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            store = bot.Store(path)
            store.language(1, "fa")
            store.language(2, "en")
            store.record(1, 99, "seen")
            store.record(1, 99, "shown")
            store.save_translation("hash", FA)
            store.db.close()
            store = bot.Store(path)
            self.assertEqual(store.load_user(1)["seen_anime"], {99})
            self.assertEqual(store.load_user(2)["seen_anime"], set())
            self.assertEqual(store.load_user(2)["language"], "en")
            self.assertEqual(store.translation("hash"), FA)
            store.db.close()


if __name__ == "__main__":
    unittest.main()
