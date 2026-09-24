from __future__ import annotations

import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock

from music.player import MusicPlayer
from music.queue import MusicQueue, LoopMode
from music.source import Track


def make_track(title="Song", duration=180):
    user = MagicMock()
    user.mention = "@User"
    user.display_name = "User"
    t = Track(
        title=title,
        stream_url="https://example.com/audio.mp3",
        webpage_url="https://youtube.com/watch?v=123",
        duration=duration,
        thumbnail=None,
        uploader="Artist",
        requester=user,
        source_type="YouTube",
    )
    t.create_audio_source = MagicMock(return_value=MagicMock())
    return t


class TestPlayerPlaybackLifecycle(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.loop = asyncio.get_running_loop()
        self.bot.wait_until_ready = AsyncMock()

        self.guild = MagicMock()
        self.guild.name = "TestGuild"
        self.guild.id = 12345

        self.player = MusicPlayer(self.bot, self.guild)
        self.player.voice_client = MagicMock()
        self.player.voice_client.is_connected.return_value = True
        self.player.voice_client.is_playing.return_value = False
        self.player.voice_client.is_paused.return_value = False
        self.player.text_channel = MagicMock()
        self.player.text_channel.send = AsyncMock()

    async def asyncTearDown(self):
        await self.player.stop(disconnect=False)

    async def test_skip_advances_only_one_track(self):
        t1 = make_track("Song 1")
        t2 = make_track("Song 2")
        t3 = make_track("Song 3")
        self.player.queue.extend([t1, t2, t3])

        played_tracks = []
        active_after_cb = None

        def fake_play(source, after=None):
            nonlocal active_after_cb
            active_after_cb = after
            self.player.voice_client.is_playing.return_value = True
            played_tracks.append(self.player.queue.current.title)

        def fake_stop():
            nonlocal active_after_cb
            self.player.voice_client.is_playing.return_value = False
            if active_after_cb:
                cb = active_after_cb
                active_after_cb = None
                cb(None)

        self.player.voice_client.play = fake_play
        self.player.voice_client.stop = fake_stop

        self.player.start_loop()
        await asyncio.sleep(0.05)

        self.assertEqual(self.player.queue.current.title, "Song 1")
        self.assertEqual(played_tracks, ["Song 1"])

        skipped = self.player.skip()
        self.assertEqual(skipped.title, "Song 1")
        await asyncio.sleep(0.05)

        self.assertEqual(self.player.queue.current.title, "Song 2")
        self.assertEqual(played_tracks, ["Song 1", "Song 2"])

        skipped2 = self.player.skip()
        self.assertEqual(skipped2.title, "Song 2")
        await asyncio.sleep(0.05)

        self.assertEqual(self.player.queue.current.title, "Song 3")
        self.assertEqual(played_tracks, ["Song 1", "Song 2", "Song 3"])

    async def test_playlist_skip_preserves_remaining_tracks(self):
        playlist_tracks = [make_track(f"Playlist Song {i}") for i in range(1, 11)]
        self.player.queue.extend(playlist_tracks)

        active_after_cb = None

        def fake_play(source, after=None):
            nonlocal active_after_cb
            active_after_cb = after
            self.player.voice_client.is_playing.return_value = True

        def fake_stop():
            nonlocal active_after_cb
            self.player.voice_client.is_playing.return_value = False
            if active_after_cb:
                cb = active_after_cb
                active_after_cb = None
                cb(None)

        self.player.voice_client.play = fake_play
        self.player.voice_client.stop = fake_stop

        self.player.start_loop()
        await asyncio.sleep(0.05)

        self.assertEqual(self.player.queue.current.title, "Playlist Song 1")
        self.assertEqual(len(self.player.queue), 9)

        self.player.skip()
        await asyncio.sleep(0.05)

        self.assertEqual(self.player.queue.current.title, "Playlist Song 2")
        self.assertEqual(len(self.player.queue), 8)
        self.assertEqual(self.player.queue.tracks[0].title, "Playlist Song 3")

    async def test_skip_with_loop_track_mode(self):
        t1 = make_track("Song 1")
        t2 = make_track("Song 2")
        self.player.queue.extend([t1, t2])
        self.player.queue.loop_mode = LoopMode.TRACK

        active_after_cb = None

        def fake_play(source, after=None):
            nonlocal active_after_cb
            active_after_cb = after
            self.player.voice_client.is_playing.return_value = True

        def fake_stop():
            nonlocal active_after_cb
            self.player.voice_client.is_playing.return_value = False
            if active_after_cb:
                cb = active_after_cb
                active_after_cb = None
                cb(None)

        self.player.voice_client.play = fake_play
        self.player.voice_client.stop = fake_stop

        self.player.start_loop()
        await asyncio.sleep(0.05)
        self.assertEqual(self.player.queue.current.title, "Song 1")

        fake_stop()
        await asyncio.sleep(0.05)
        self.assertEqual(self.player.queue.current.title, "Song 1")

        self.player.skip()
        await asyncio.sleep(0.05)
        self.assertEqual(self.player.queue.current.title, "Song 2")

    async def test_stale_callbacks_do_not_skip(self):
        t1 = make_track("Song 1")
        t2 = make_track("Song 2")
        self.player.queue.extend([t1, t2])

        self.player.start_loop()
        await asyncio.sleep(0.05)
        self.assertEqual(self.player.queue.current.title, "Song 1")

        self.player._handle_playback_finished(None, play_id=999)
        await asyncio.sleep(0.05)

        self.assertEqual(self.player.queue.current.title, "Song 1")


if __name__ == "__main__":
    unittest.main()
