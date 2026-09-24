"""
Тестирование извлечения потока и создания аудиоисточника FFmpeg.
"""

import sys
import unittest

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

import discord
from music.source import YTDLSource
from tests.test_components import FakeMember


class TestYTDLAudioStream(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_track_and_create_source(self):
        member = FakeMember()
        # Извлекаем реальный трек по короткому поисковому запросу
        track = await YTDLSource.fetch_track("ytsearch1:Rick Astley Never Gonna Give You Up", requester=member)
        self.assertTrue(track.stream_url.startswith("http"))
        self.assertGreater(track.duration, 0)
        self.assertIn("Never Gonna Give You Up", track.title)

        # Создаем аудиоисточник FFmpeg
        source = track.create_audio_source(volume=0.5)
        self.assertIsInstance(source, discord.PCMVolumeTransformer)
        self.assertAlmostEqual(source.volume, 0.5)
        source.cleanup()
        print(f"\n[OK] Track fetched and FFmpeg source initialized: {track.title}")


if __name__ == "__main__":
    unittest.main()
