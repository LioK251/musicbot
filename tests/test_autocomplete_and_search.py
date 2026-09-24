"""
Тестирование автодополнения слэш-команды /play, фильтрации поиска и интерактивного меню /search.
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

sys.path.insert(0, os.path.abspath("."))

import discord
from discord import app_commands
from cogs.music import MusicCog
from music.source import YTDLSource
from music.views import SongSelectDropdown, SongSelectView
from tests.test_components import FakeMember


class TestAutocompleteAndSearch(unittest.IsolatedAsyncioTestCase):
    async def test_search_top5_sanitization(self):
        """Проверяет корректность очистки названий и метаданных в search_top5."""
        results = await YTDLSource.search_top5("queen")
        self.assertIsInstance(results, list)
        self.assertGreaterEqual(len(results), 1)
        self.assertLessEqual(len(results), 5)

        for item in results:
            self.assertIn("title", item)
            self.assertIn("url", item)
            self.assertIn("uploader", item)
            self.assertIn("duration_str", item)
            # Убеждаемся, что нет переносов строк
            self.assertNotIn("\n", item["title"])
            self.assertNotIn("\r", item["title"])
            self.assertNotIn("\n", item["uploader"])
            self.assertTrue(item["url"].startswith("http"))

    async def test_song_select_dropdown_options(self):
        """Проверяет, что SongSelectDropdown корректно создает SelectOptions без превышения лимитов Discord."""
        fake_tracks = [
            {
                "id": "123",
                "title": "A" * 150 + "\nNew line track",
                "url": "https://www.youtube.com/watch?v=123",
                "uploader": "Uploader\nName " + "X" * 120,
                "duration_str": "03:45",
            },
            {
                "id": "456",
                "title": "Normal Title",
                "url": "https://www.youtube.com/watch?v=456",
                "uploader": "Normal Artist",
                "duration_str": "04:20",
            },
        ]
        cb = AsyncMock()
        dropdown = SongSelectDropdown(fake_tracks, cb)
        self.assertEqual(len(dropdown.options), 2)

        for opt in dropdown.options:
            self.assertLessEqual(len(opt.label), 100)
            self.assertLessEqual(len(opt.description), 100)
            self.assertNotIn("\n", opt.label)
            self.assertNotIn("\n", opt.description)

    async def test_play_autocomplete_function(self):
        """Проверяет функцию play_autocomplete."""
        bot = MagicMock()
        cog = MusicCog(bot)

        fake_interaction = MagicMock(spec=discord.Interaction)

        # 1. Пустой ввод -> возвращает подсказки по умолчанию
        choices_empty = await cog.play_autocomplete(fake_interaction, "")
        self.assertGreaterEqual(len(choices_empty), 1)
        for c in choices_empty:
            self.assertIsInstance(c, app_commands.Choice)
            self.assertLessEqual(len(c.name), 100)

        # 2. Прямая ссылка
        choices_url = await cog.play_autocomplete(fake_interaction, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(len(choices_url), 1)
        self.assertEqual(choices_url[0].value, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        # 3. Реальный запрос
        choices_query = await cog.play_autocomplete(fake_interaction, "Never Gonna Give You Up")
        self.assertGreaterEqual(len(choices_query), 1)
        self.assertLessEqual(len(choices_query), 5)
        for c in choices_query:
            self.assertIsInstance(c, app_commands.Choice)
            self.assertTrue(c.value.startswith("http"))
            self.assertLessEqual(len(c.name), 100)


if __name__ == "__main__":
    unittest.main()
