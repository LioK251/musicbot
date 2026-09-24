from __future__ import annotations

import asyncio
import sys
import unittest

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

from music.source import YTDLSource


class TestYTDLSearch(unittest.IsolatedAsyncioTestCase):
    async def test_search_top5(self):
        results = await YTDLSource.search_top5("lofi hip hop beats")
        self.assertIsInstance(results, list)
        self.assertGreaterEqual(len(results), 1)
        first = results[0]
        self.assertIn("title", first)
        self.assertIn("url", first)
        self.assertIn("uploader", first)
        self.assertIn("duration_str", first)
        print(f"\n[OK] YTDL Top-1 Result: {first['title']} ({first['duration_str']}) by {first['uploader']}")


if __name__ == "__main__":
    unittest.main()
