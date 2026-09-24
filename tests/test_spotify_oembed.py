"""
Тестирование Spotify oEmbed извлечения.
"""

import sys
import unittest

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

from music.spotify import spotify_client


class TestSpotifyOEmbed(unittest.IsolatedAsyncioTestCase):
    async def test_extract_track_oembed(self):
        # Реальная ссылка на трек Spotify
        url = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
        data = await spotify_client.extract_metadata(url)
        self.assertEqual(data["type"], "track")
        self.assertTrue(len(data["queries"]) >= 1)
        print(f"\n[OK] Spotify metadata: title={data['title']}, queries={data['queries']}")


if __name__ == "__main__":
    unittest.main()
