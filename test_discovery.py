"""Offline regression tests for discovery, personal filters and account data."""
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiohttp

import animeSuggest as bot
from test_animeSuggest import BotCase, anime, response


class DiscoveryTests(BotCase):
    async def test_genre_picker_overrides_saved_genre_for_pick_and_next_only(self):
        self.language("fa")
        self.store.set_preference(1, "genre", "Drama")
        self.store.set_preference(1, "min_score", 80)
        self.store.record(1, 3, "seen")
        self.message.text = bot.TEXT["fa"]["genre_pick"]
        await bot.handle_text(self.update, self.context)
        button = self.message.reply_text.call_args.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.text, "اکشن")
        self.update.callback_query = self.feedback(*button.callback_data.split(":"))
        with self.network(), patch.object(bot, "fetch_catalog", AsyncMock(return_value=([anime(1), anime(2), anime(3)], False))) as fetch:
            await bot.handle_genre(self.update, self.context)
            first = self.context.user_data["active_suggestion"][-1]
            self.feedback("next", first)
            await bot.handle_feedback(self.update, self.context)
        self.assertEqual({first, self.context.user_data["active_suggestion"][-1]}, {1, 2})
        for call in fetch.await_args_list:
            self.assertEqual(call.kwargs["preferences"]["genre"], "Action")
            self.assertEqual(call.kwargs["preferences"]["min_score"], 80)
        self.assertEqual(self.store.preferences(1)["genre"], "Drama")

    async def test_genre_retry_keeps_original_genre_and_title(self):
        self.language("en")
        self.feedback("genre", 0)
        with self.network(), patch.object(bot, "fetch_catalog", AsyncMock(return_value=([anime(1), anime(2)], False))) as fetch:
            with patch.object(bot, "translate_synopsis", AsyncMock(side_effect=bot.TranslationUnavailable())):
                await bot.handle_genre(self.update, self.context)
            button = self.progress.edit_text.call_args.kwargs["reply_markup"].inline_keyboard[0][0]
            pending = self.context.user_data["genre_retry"][2]
            query = self.feedback(*button.callback_data.split(":"))
            query.message.message_id = self.progress.message_id
            await bot.handle_genre(self.update, self.context)
        self.assertEqual(self.context.user_data["active_suggestion"][-1], pending)
        self.assertEqual(fetch.await_args.kwargs["preferences"]["genre"], "Action")

    async def test_transport_omits_null_filters_and_caches_list_variables(self):
        from unittest.mock import MagicMock
        session = SimpleNamespace(post=MagicMock(return_value=response({"data": {"Page": {"media": []}}})))
        await bot.anilist_query(session, "catalog", sort=["SCORE_DESC"], genre=None)
        self.assertEqual(session.post.call_args.kwargs["json"]["variables"], {"sort": ["SCORE_DESC"]})
        await bot.anilist_query(session, "catalog", sort=["SCORE_DESC"])
        self.assertEqual(session.post.call_count, 1)

    async def test_search_prompt_then_plain_title_returns_results(self):
        self.language("en")
        self.context.args = []
        await bot.search_command(self.update, self.context)
        self.assertTrue(self.context.user_data["awaiting_search"])
        self.message.text = "Cowboy Bebop"
        with patch.object(bot, "fetch_catalog", AsyncMock(return_value=([anime(1)], True))) as fetch:
            await bot.handle_text(self.update, self.context)
        self.assertEqual(fetch.await_args.args[1:4], ("search", "Cowboy Bebop", 1))
        self.assertNotIn("awaiting_search", self.context.user_data)
        catalog = next(iter(self.context.user_data["catalogs"].values()))
        self.assertEqual(catalog["items"][1]["title"], "Anime 1")
        buttons = self.progress.edit_text.call_args.kwargs["reply_markup"].inline_keyboard
        self.assertIn("English 1", buttons[0][0].text)
        self.assertIn("Next", buttons[-1][0].text)

    async def test_short_search_does_not_fetch(self):
        self.language()
        with patch.object(bot, "fetch_catalog", AsyncMock()) as fetch:
            await bot.show_catalog(self.update, self.context, "search", "a")
        fetch.assert_not_awaited()

    async def test_discovery_requires_language(self):
        with patch.object(bot, "fetch_catalog", AsyncMock()) as fetch:
            await bot.top_command(self.update, self.context)
        fetch.assert_not_awaited()

    async def test_page_controls_are_owned_and_allow_only_adjacent_pages(self):
        self.language("en")
        with patch.object(bot, "fetch_catalog", AsyncMock(return_value=([anime(1)], True))):
            await bot.top_command(self.update, self.context)
        token = next(iter(self.context.user_data["catalogs"]))
        query = self.feedback("disc:page", f"{token}:2")
        query.message.message_id = 30
        query.edit_message_text = AsyncMock()
        with patch.object(bot, "fetch_catalog", AsyncMock(return_value=([anime(2)], False))) as fetch:
            await bot.handle_catalog(self.update, self.context)
        self.assertEqual(fetch.await_args.args[3], 2)
        self.assertEqual(self.context.user_data["catalogs"][token]["page"], 2)
        query.data = f"disc:page:{token}:3"
        with patch.object(bot, "fetch_catalog", AsyncMock()) as fetch:
            await bot.handle_catalog(self.update, self.context)
        fetch.assert_not_awaited()
        self.context.user_data = {}
        with patch.object(bot, "fetch_catalog", AsyncMock()) as fetch:
            await bot.handle_catalog(self.update, self.context)
        fetch.assert_not_awaited()

    async def test_open_search_result_keeps_main_card_and_supports_watchlist(self):
        self.language()
        state = bot.state_for(self.update, self.context)
        state["active_suggestion"] = (100, 77, 9)
        with patch.object(bot, "fetch_catalog", AsyncMock(return_value=([anime(1)], False))):
            await bot.show_catalog(self.update, self.context, "search", "Anime")
        token = next(iter(state["catalogs"]))
        query = self.feedback("disc:open", f"{token}:1")
        query.message.message_id = 30
        with self.network():
            await bot.handle_catalog(self.update, self.context)
        self.assertEqual(state["active_suggestion"], (100, 77, 9))
        self.assertIn((100, 20, 1), state["related_cards"])
        self.feedback("unseen", 1)
        await bot.handle_feedback(self.update, self.context)
        self.assertEqual(self.store.saved_anime(1)[0][0], 1)

    async def test_old_page_item_cannot_be_opened_after_page_changes(self):
        self.language()
        state = bot.state_for(self.update, self.context)
        state["catalogs"] = {"12345678": {"message": (100, 20), "items": {2: anime(2)}}}
        self.feedback("disc:open", "12345678:1")
        with patch.object(bot, "deliver_anime", AsyncMock()) as deliver:
            await bot.handle_catalog(self.update, self.context)
        deliver.assert_not_awaited()

    async def test_busy_card_does_not_start_second_delivery(self):
        self.language()
        state = bot.state_for(self.update, self.context)
        state["catalogs"] = {"12345678": {"message": (100, 20), "items": {1: anime(1)}}}
        state["suggestion_busy"] = True
        self.feedback("disc:open", "12345678:1")
        with patch.object(bot, "deliver_anime", AsyncMock()) as deliver:
            await bot.handle_catalog(self.update, self.context)
        deliver.assert_not_awaited()

    async def test_failed_lookup_releases_busy_and_leaves_search_retryable(self):
        self.language()
        state = bot.state_for(self.update, self.context)
        state["awaiting_search"] = True
        with patch.object(bot, "fetch_catalog", AsyncMock(side_effect=aiohttp.ClientError())):
            await bot.show_catalog(self.update, self.context, "search", "Bebop")
        self.assertFalse(state["suggestion_busy"])
        self.assertTrue(state["awaiting_search"])

    async def test_filter_query_uses_inclusive_score_and_length(self):
        payload = {"Page": {"media": [], "pageInfo": {"hasNextPage": False}}}
        with patch.object(bot, "anilist_query", AsyncMock(return_value=payload)) as query:
            await bot.fetch_catalog(None, "airing", preferences={"genre": "Action", "min_score": 80, "max_episodes": 12})
        args = query.await_args.kwargs
        self.assertEqual((args["genre"], args["score"], args["episodes"], args["status"]), ("Action", 79, 13, "RELEASING"))
        self.assertIn("isAdult:false", query.await_args.args[1])

    async def test_search_ignores_preferences_and_includes_movies(self):
        payload = {"Page": {"media": [], "pageInfo": {"hasNextPage": False}}}
        with patch.object(bot, "anilist_query", AsyncMock(return_value=payload)) as query:
            await bot.fetch_catalog(None, "search", "Your Name", preferences={"genre": "Action", "min_score": 90, "max_episodes": 12})
        args = query.await_args.kwargs
        for field in ("genre", "score", "episodes", "formats", "status", "sort"):
            self.assertIsNone(args[field])

    async def test_random_recommendations_respect_saved_filters_and_seen_history(self):
        self.language()
        self.store.set_preference(1, "genre", "Drama")
        self.store.record(1, 1, "seen")
        with self.network(), patch.object(bot, "fetch_catalog", AsyncMock(return_value=([anime(1), anime(2)], False))) as fetch:
            await bot.suggest_anime(self.update, self.context)
        self.assertEqual(fetch.await_args.kwargs["preferences"]["genre"], "Drama")
        self.assertEqual(self.context.user_data["active_suggestion"][-1], 2)

    async def test_empty_filtered_pool_explains_no_results(self):
        self.language("en")
        self.store.set_preference(1, "min_score", 90)
        with patch.object(bot, "fetch_catalog", AsyncMock(return_value=([], False))):
            await bot.suggest_anime(self.update, self.context)
        self.assertEqual(self.progress.edit_text.call_args.args[0], bot.TEXT["en"]["no_results"])

    async def test_farsi_menu_with_joiners_routes_to_history(self):
        self.language()
        self.message.text = bot.TEXT["fa"]["history"]
        await bot.handle_text(self.update, self.context)
        self.assertIn("هنوز", self.message.reply_text.call_args.args[0])

    def test_movie_caption_and_long_metadata_fit_telegram(self):
        item = dict(anime(1), format="MOVIE", genres=list(bot.GENRES), year=2020)
        for language in bot.TEXT:
            caption = bot.format_suggestion(item, "🎬" * 2000, bot.SeasonCount(0), language)
            self.assertLessEqual(len(caption.encode("utf-16-le")) // 2, 1024)
            self.assertNotIn(bot.TEXT[language]["seasons"], caption)
            self.assertIn("2020", caption)


class PersonalDataTests(BotCase):
    async def test_preferences_persist_and_are_separate_for_each_user(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "store.sqlite3"
            store = bot.Store(path)
            store.set_preference(1, "genre", "Fantasy")
            store.set_preference(1, "min_score", 80)
            store.db.close()
            store = bot.Store(path)
            self.assertEqual(store.preferences(1), {"genre": "Fantasy", "min_score": 80, "max_episodes": 0})
            self.assertIsNone(store.preferences(2)["genre"])
            store.db.close()

    async def test_settings_validate_values_and_reset(self):
        self.language("en")
        await bot.settings_command(self.update, self.context)
        query = self.feedback("pref:min_score", "80")
        query.message.message_id = 30
        query.edit_message_text = AsyncMock()
        await bot.handle_preferences(self.update, self.context)
        self.assertEqual(self.store.preferences(1)["min_score"], 80)
        query.data = "pref:min_score:500"
        await bot.handle_preferences(self.update, self.context)
        self.assertEqual(self.store.preferences(1)["min_score"], 80)
        query.data = "pref:genre:0"
        await bot.handle_preferences(self.update, self.context)
        self.assertEqual(self.store.preferences(1)["genre"], "Action")
        query.data = "pref:reset:0"
        await bot.handle_preferences(self.update, self.context)
        self.assertEqual(self.store.preferences(1), {"genre": None, "min_score": 0, "max_episodes": 0})

    async def test_settings_callback_cannot_modify_another_users_preferences(self):
        self.language()
        self.feedback("pref:min_score", "80")
        await bot.handle_preferences(self.update, self.context)
        self.assertEqual(self.store.preferences(1)["min_score"], 0)

    async def test_history_undo_preserves_other_users_and_shown_record(self):
        self.language("en")
        self.store.remember_anime(anime(1))
        for user in (1, 2):
            self.store.record(user, 1, "seen")
        await bot.history_command(self.update, self.context)
        query = self.feedback("hist:undo", "1:0")
        query.message.message_id = 30
        query.edit_message_text = AsyncMock()
        await bot.handle_history(self.update, self.context)
        self.assertNotIn(1, bot.state_for(self.update, self.context)["seen_anime"])
        self.assertEqual(self.store.load_user(1)["shown_anime"], {1})
        self.assertEqual(self.store.load_user(2)["seen_anime"], {1})
        self.assertIn("No watched", query.edit_message_text.call_args.args[0])

    async def test_export_contains_only_requesting_users_lists(self):
        self.language("en")
        for number in (1, 2):
            self.store.remember_anime(anime(number))
        self.store.save_for_later(1, 1)
        self.store.save_for_later(2, 2)
        self.store.record(1, 1, "seen")
        self.message.reply_document = AsyncMock()
        await bot.export_command(self.update, self.context)
        document = self.message.reply_document.call_args.args[0]
        data = json.loads(document.input_file_content)
        self.assertEqual([item["id"] for item in data["watched"]], [1])
        self.assertEqual(data["watchlist"], [])
        self.assertNotIn("token", data)

    async def test_stats_reads_persisted_counts(self):
        self.language("en")
        self.store.remember_anime(anime(1))
        self.store.save_for_later(1, 1)
        self.store.record(1, 2, "seen")
        await bot.stats_command(self.update, self.context)
        text = self.message.reply_text.call_args.args[0]
        self.assertIn("Watched: 1", text)
        self.assertIn("Watchlist: 1", text)

    async def test_cancel_clears_search(self):
        self.language()
        state = bot.state_for(self.update, self.context)
        state["awaiting_search"] = True
        await bot.cancel_command(self.update, self.context)
        self.assertNotIn("awaiting_search", state)
