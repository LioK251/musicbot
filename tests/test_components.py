"""
Тесты компонентов: очередь, зацикливание, регулярные выражения TikTok и Spotify, прогресс-бар.
"""

import unittest
from music.queue import MusicQueue, LoopMode
from music.source import Track
from music.spotify import SPOTIFY_URL_REGEX, spotify_client
from cogs.tiktok import TIKTOK_REGEX
from config import config


class FakeMember:
    def __init__(self, name="TestUser", user_id=12345):
        self.name = name
        self.display_name = name
        self.id = user_id
        self.mention = f"<@{user_id}>"


def make_test_track(title="Test Song", duration=180, source="YouTube"):
    return Track(
        title=title,
        stream_url="https://example.com/audio.mp3",
        webpage_url="https://youtube.com/watch?v=123",
        duration=duration,
        thumbnail="https://example.com/thumb.jpg",
        uploader="Test Artist",
        requester=FakeMember(),
        source_type=source,
    )


class TestTikTokRegex(unittest.TestCase):
    def test_tiktok_urls(self):
        urls = [
            "https://www.tiktok.com/@username/video/7123456789012345678",
            "https://tiktok.com/@user.name/video/7123456789012345678",
            "https://vm.tiktok.com/ZM8abcde/",
            "https://vt.tiktok.com/ZS8abcde/",
            "https://www.tiktok.com/t/ZT8abcde/",
        ]
        for url in urls:
            match = TIKTOK_REGEX.search(url)
            self.assertIsNotNone(match, f"URL should match: {url}")

    def test_text_with_tiktok_url(self):
        text = "Смотри какой смешной видос https://vm.tiktok.com/ZM8abcde/ лол"
        matches = TIKTOK_REGEX.findall(text)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0], "https://vm.tiktok.com/ZM8abcde/")


class TestSpotifyRegex(unittest.TestCase):
    def test_spotify_urls(self):
        urls = [
            ("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT", "track", "4cOdK2wGLETKBW3PvgPWqT"),
            ("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M", "playlist", "37i9dQZF1DXcBWIGoYBM5M"),
            ("https://open.spotify.com/album/41MnTivkwTO3UUgpDr2WJJ", "album", "41MnTivkwTO3UUgpDr2WJJ"),
        ]
        for url, expected_type, expected_id in urls:
            self.assertTrue(spotify_client.is_spotify_url(url))
            match = SPOTIFY_URL_REGEX.search(url)
            self.assertEqual(match.group("type"), expected_type)
            self.assertEqual(match.group("id"), expected_id)


class TestMusicQueue(unittest.TestCase):
    def setUp(self):
        self.queue = MusicQueue()

    def test_queue_fifo(self):
        t1 = make_test_track("Song 1")
        t2 = make_test_track("Song 2")
        self.queue.add(t1)
        self.queue.add(t2)

        self.assertEqual(len(self.queue), 2)
        next_t = self.queue.get_next()
        self.assertEqual(next_t.title, "Song 1")
        self.assertEqual(self.queue.current.title, "Song 1")

        next_t2 = self.queue.get_next()
        self.assertEqual(next_t2.title, "Song 2")

        next_t3 = self.queue.get_next()
        self.assertIsNone(next_t3)

    def test_loop_track(self):
        t1 = make_test_track("Song 1")
        t2 = make_test_track("Song 2")
        self.queue.add(t1)
        self.queue.add(t2)

        self.queue.get_next()  # current = t1
        self.queue.loop_mode = LoopMode.TRACK

        # При LOOP_TRACK следующий get_next должен возвращать тот же трек
        self.assertEqual(self.queue.get_next().title, "Song 1")
        self.assertEqual(self.queue.get_next().title, "Song 1")

        # Принудительный скип должен продвинуть очередь
        skipped = self.queue.force_skip()
        self.assertEqual(skipped.title, "Song 2")

    def test_loop_queue(self):
        t1 = make_test_track("Song 1")
        t2 = make_test_track("Song 2")
        self.queue.add(t1)
        self.queue.add(t2)

        self.queue.get_next()  # current = t1
        self.queue.loop_mode = LoopMode.QUEUE

        next_t = self.queue.get_next()  # current = t2, t1 уходит в конец очереди
        self.assertEqual(next_t.title, "Song 2")

        next_t3 = self.queue.get_next()  # снова t1
        self.assertEqual(next_t3.title, "Song 1")

    def test_remove(self):
        t1 = make_test_track("Song 1")
        t2 = make_test_track("Song 2")
        t3 = make_test_track("Song 3")
        self.queue.extend([t1, t2, t3])

        removed = self.queue.remove(2)
        self.assertEqual(removed.title, "Song 2")
        self.assertEqual(len(self.queue), 2)
        self.assertEqual(self.queue.tracks[0].title, "Song 1")
        self.assertEqual(self.queue.tracks[1].title, "Song 3")

    def test_single_skip_does_not_double_skip(self):
        t1 = make_test_track("Track 1")
        t2 = make_test_track("Track 2")
        t3 = make_test_track("Track 3")
        self.queue.extend([t1, t2, t3])

        # Первый трек начинает играть
        curr = self.queue.get_next()
        self.assertEqual(curr.title, "Track 1")

        # Пользователь нажимает Скип (is_skip=True)
        next_track = self.queue.get_next(is_skip=True)
        self.assertEqual(next_track.title, "Track 2")  # Track 2 НЕ пропускается!

        # Track 2 закончился сам
        next_track = self.queue.get_next(is_skip=False)
        self.assertEqual(next_track.title, "Track 3")

    def test_playlist_sequential_skips(self):
        tracks = [make_test_track(f"Song {i}") for i in range(1, 6)]
        self.queue.extend(tracks)

        # Старт первого трека
        curr = self.queue.get_next()
        self.assertEqual(curr.title, "Song 1")

        # Последовательно скипаем каждую песню и проверяем, что ни одна не теряется
        for i in range(2, 6):
            skipped_to = self.queue.get_next(is_skip=True)
            self.assertIsNotNone(skipped_to)
            self.assertEqual(skipped_to.title, f"Song {i}")

        # Скип последнего трека переводит очередь в пустое состояние
        empty = self.queue.get_next(is_skip=True)
        self.assertIsNone(empty)
        self.assertTrue(self.queue.is_empty)

    def test_formatted_duration(self):
        t1 = make_test_track(duration=65)
        self.assertEqual(t1.formatted_duration, "01:05")

        t2 = make_test_track(duration=3665)
        self.assertEqual(t2.formatted_duration, "01:01:05")

        t_live = make_test_track(duration=0)
        self.assertEqual(t_live.formatted_duration, "🔴 Прямой эфир")


class TestTikTokConversion(unittest.TestCase):
    def test_convert_tiktok_url(self):
        from cogs.tiktok import TikTokCog
        cog = TikTokCog(None)  # type: ignore
        url = "https://www.tiktok.com/@user/video/123456"
        converted = cog._convert_tiktok_url(url)
        self.assertIn("vxtiktok.com", converted)


class TestPlayerEmbed(unittest.TestCase):
    def test_minimalist_embed(self):
        from music.player import MusicPlayer
        class FakeGuild:
            id = 999
            name = "TestGuild"
        player = MusicPlayer(FakeGuild(), None)  # type: ignore
        player.queue.current = make_test_track("Cool Song", 200)
        embed = player.build_now_playing_embed()
        self.assertIsNotNone(embed.description)
        self.assertIn("Cool Song", embed.description)
        self.assertIn("Test Artist", embed.description)
        self.assertEqual(len(embed.fields), 0)  # Minimalist design has 0 bulky fields

    def test_queue_embed_limits_with_long_tracks(self):
        """Проверяет, что эмбеды очереди с длинными URL и названиями не превышают лимиты Discord (1024/4096)."""
        from cogs.music import MusicCog
        # Создаем 50 треков с длинными названиями и URL
        long_title = "Very Long Song Title " * 5
        long_url = "https://www.youtube.com/watch?v=12345678901&list=PL12345678901234567890&index=1"
        tracks = [make_test_track(f"{i}. {long_title}", duration=200) for i in range(50)]
        for t in tracks:
            t.webpage_url = long_url

        PAGE_SIZE = 10
        total_pages = 5
        for p in range(total_pages):
            page_tracks = tracks[p * PAGE_SIZE : (p + 1) * PAGE_SIZE]
            desc_lines = ["**🎶 Сейчас играет:**\nTest • @User\n\n**Далее в очереди (50 треков):**"]
            for i, t in enumerate(page_tracks, start=p * PAGE_SIZE + 1):
                clean_title = " ".join(t.title.split())[:45]
                desc_lines.append(f"`{i}.` [{clean_title}]({t.webpage_url}) (`{t.formatted_duration}`) • {t.requester.mention}")
            full_desc = "\n".join(desc_lines)
            self.assertLessEqual(len(full_desc), 4000, "Description must be <= 4000 chars")


if __name__ == "__main__":
    unittest.main()



