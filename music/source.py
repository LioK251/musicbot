"""
Модуль извлечения метаданных и создания аудиопотоков через yt-dlp и FFmpeg.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Any
import discord
import yt_dlp
from core.errors import TrackFetchError

logger = logging.getLogger("DiscordBot.AudioSource")

# Настройки yt-dlp для быстрого и стабильного извлечения аудиопотоков
YTDL_OPTIONS: dict[str, Any] = {
    "format": "bestaudio/best",
    "extractaudio": True,
    "audioformat": "opus/mp3",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",  # Принудительно IPv4 для обхода блокировок IPv6
}

# Настройки FFmpeg для стабильного стриминга через сеть с защитой от 403 Forbidden
FFMPEG_OPTIONS: dict[str, str] = {
    "before_options": (
        '-user_agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36" '
        "-reconnect 1 "
        "-reconnect_streamed 1 "
        "-reconnect_delay_max 5 "
        "-nostdin"
    ),
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


@dataclass
class Track:
    """Представление музыкального трека в очереди бота."""

    title: str
    stream_url: str | None
    webpage_url: str
    duration: int  # в секундах
    thumbnail: str | None
    uploader: str
    requester: discord.Member
    source_type: str = "YouTube"  # YouTube, SoundCloud, Spotify
    query: str | None = None

    @property
    def formatted_duration(self) -> str:
        """Форматирует длительность трека в строку MM:SS или HH:MM:SS."""
        if not self.duration or self.duration <= 0:
            return "🔴 Прямой эфир"

        minutes, seconds = divmod(self.duration, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    async def ensure_stream_url(self) -> str:
        """Ленивая загрузка прямого аудиопотока перед воспроизведением."""
        if self.stream_url:
            return self.stream_url

        target = self.webpage_url if (self.webpage_url and self.webpage_url.startswith("http")) else (self.query or self.title)
        resolved = await YTDLSource.fetch_track(target, requester=self.requester, source_type=self.source_type)
        self.stream_url = resolved.stream_url
        if not self.title or self.title == "Неизвестный трек":
            self.title = resolved.title
        if not self.duration:
            self.duration = resolved.duration
        if not self.thumbnail:
            self.thumbnail = resolved.thumbnail
        if not self.uploader or self.uploader == "Неизвестно":
            self.uploader = resolved.uploader
        return self.stream_url

    def create_audio_source(self, volume: float = 0.7) -> discord.PCMVolumeTransformer:
        """Создает оптимизированный аудиоисточник FFmpeg для воспроизведения."""
        if not self.stream_url:
            raise TrackFetchError("Аудиопоток не разрешен (stream_url is None).")
        ffmpeg_audio = discord.FFmpegPCMAudio(self.stream_url, **FFMPEG_OPTIONS)
        return discord.PCMVolumeTransformer(ffmpeg_audio, volume=volume)


class YTDLSource:
    """Менеджер извлечения информации через yt-dlp."""

    @classmethod
    async def fetch_track(cls, query_or_url: str, requester: discord.Member, source_type: str = "YouTube") -> Track:
        """
        Извлекает прямой аудиопоток и метаданные для одного трека.
        Выполняется в отдельном потоке (ThreadExecutor) без блокировки event loop.
        """
        loop = asyncio.get_running_loop()

        def _extract() -> dict[str, Any]:
            # Проверяем, является ли запрос URL или уже имеет явный префикс поиска
            if query_or_url.startswith(("http://", "https://", "ytsearch:", "ytsearch1:", "ytsearch5:", "scsearch:")):
                search_target = query_or_url
            else:
                search_target = f"ytsearch1:{query_or_url}"

            data = ytdl.extract_info(search_target, download=False)
            if "entries" in data:
                # Берем первый результат из поиска
                entries = data.get("entries")
                if not entries:
                    raise TrackFetchError(f"Ничего не найдено по запросу: {query_or_url}")
                data = entries[0]
            return data

        try:
            data = await loop.run_in_executor(None, _extract)
        except Exception as e:
            logger.error(f"Ошибка при извлечении трека '{query_or_url}': {e}")
            raise TrackFetchError(f"Не удалось загрузить трек: {e}")

        # Извлекаем прямой URL аудио
        stream_url = data.get("url")
        if not stream_url:
            raise TrackFetchError("Не найден прямой поток для воспроизведения.")

        return Track(
            title=data.get("title", "Неизвестный трек"),
            stream_url=stream_url,
            webpage_url=data.get("webpage_url") or query_or_url,
            duration=int(data.get("duration") or 0),
            thumbnail=data.get("thumbnail"),
            uploader=data.get("uploader", "Неизвестный автор"),
            requester=requester,
            source_type=source_type,
        )

    @classmethod
    async def search_top5(cls, query: str) -> list[dict[str, Any]]:
        """
        Выполняет поиск топ-5 результатов на YouTube для меню выбора и автодополнения.
        Возвращает чистые краткие метаданные каждого найденного трека.
        """
        loop = asyncio.get_running_loop()

        def _search() -> list[dict[str, Any]]:
            opts = {**YTDL_OPTIONS, "extract_flat": True}
            with yt_dlp.YoutubeDL(opts) as search_ytdl:
                data = search_ytdl.extract_info(f"ytsearch10:{query}", download=False)
                if not data or "entries" not in data:
                    return []
                valid_entries = []
                for entry in data.get("entries", []):
                    if not entry:
                        continue
                    # Исключаем каналы, вкладки и плейлисты
                    if entry.get("_type") in ("playlist", "channel") or entry.get("ie_key") == "YoutubeTab":
                        continue
                    vid_id = entry.get("id")
                    if not vid_id:
                        continue
                    valid_entries.append(entry)
                    if len(valid_entries) >= 5:
                        break
                return valid_entries

        try:
            entries = await loop.run_in_executor(None, _search)
            results = []
            for entry in entries:
                duration = int(entry.get("duration") or 0)
                minutes, seconds = divmod(duration, 60)
                hours, minutes = divmod(minutes, 60)
                dur_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"

                raw_title = entry.get("title") or "Без названия"
                clean_title = " ".join(raw_title.split())

                raw_uploader = entry.get("uploader") or "Неизвестно"
                clean_uploader = " ".join(raw_uploader.split())

                vid_id = entry.get("id")
                url = entry.get("url")
                if not url or not url.startswith("http"):
                    url = f"https://www.youtube.com/watch?v={vid_id}"

                results.append({
                    "id": vid_id,
                    "title": clean_title,
                    "url": url,
                    "uploader": clean_uploader,
                    "duration_str": dur_str if duration > 0 else "Прямой эфир",
                    "duration": duration,
                })
            return results
        except Exception as e:
            logger.error(f"Ошибка при поиске топ-5 по запросу '{query}': {e}")
            return []

    @classmethod
    async def fetch_playlist_entries(cls, playlist_url: str) -> tuple[str, list[dict[str, Any]]]:
        """
        Быстро извлекает список треков с метаданными из плейлиста без скачивания каждого потока.
        Возвращает (название плейлиста, список метаданных треков).
        """
        loop = asyncio.get_running_loop()

        def _extract_playlist() -> tuple[str, list[dict[str, Any]]]:
            opts = {
                **YTDL_OPTIONS,
                "extract_flat": True,
                "noplaylist": False,
                "playlistend": 50,  # Защита от зависаний на бесконечных YouTube Mix
            }
            with yt_dlp.YoutubeDL(opts) as pl_ytdl:
                data = pl_ytdl.extract_info(playlist_url, download=False)
                title = data.get("title", "Плейлист")
                entries = data.get("entries", [])
                results: list[dict[str, Any]] = []
                for item in entries:
                    if not item:
                        continue
                    vid_id = item.get("id")
                    if vid_id:
                        track_url = f"https://www.youtube.com/watch?v={vid_id}"
                    else:
                        track_url = item.get("url")
                        if track_url and not track_url.startswith("http"):
                            track_url = f"https://www.youtube.com/watch?v={track_url}"

                    if not track_url:
                        continue

                    thumb = item.get("thumbnail")
                    if not thumb and item.get("thumbnails"):
                        thumb = item["thumbnails"][-1].get("url")

                    results.append({
                        "title": item.get("title") or "Неизвестный трек",
                        "url": track_url,
                        "duration": int(item.get("duration") or 0),
                        "uploader": item.get("uploader") or item.get("channel") or "Неизвестно",
                        "thumbnail": thumb,
                    })
                return title, results

        try:
            return await loop.run_in_executor(None, _extract_playlist)
        except Exception as e:
            logger.error(f"Ошибка при извлечении плейлиста '{playlist_url}': {e}")
            raise TrackFetchError(f"Не удалось прочитать плейлист: {e}")
