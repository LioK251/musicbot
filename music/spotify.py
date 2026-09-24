"""
Модуль интеграции со Spotify Web API.
Извлекает метаданные треков, альбомов и плейлистов для последующего стриминга через YouTube/SoundCloud.
"""

from __future__ import annotations

import logging
import re
from typing import Any
import aiohttp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from config import config
from core.errors import SpotifyConfigError, TrackFetchError

logger = logging.getLogger("DiscordBot.Spotify")

# Регулярные выражения для распознавания ссылок Spotify
SPOTIFY_URL_REGEX = re.compile(
    r"https?://open\.spotify\.com/(?P<type>track|playlist|album)/(?P<id>[a-zA-Z0-9]+)"
)


class SpotifyClient:
    """Обертка над Spotify API для асинхронного извлечения данных."""

    def __init__(self) -> None:
        self._sp: spotipy.Spotify | None = None
        self._init_client()

    def _init_client(self) -> None:
        """Инициализирует spotipy клиент при наличии валидных credentials."""
        if config.has_spotify_credentials:
            try:
                auth_manager = SpotifyClientCredentials(
                    client_id=config.spotify_client_id,
                    client_secret=config.spotify_client_secret,
                )
                self._sp = spotipy.Spotify(auth_manager=auth_manager)
                logger.info("Spotify API успешно подключен и готов к работе.")
            except Exception as e:
                logger.error(f"Ошибка при инициализации Spotify клиента: {e}")
                self._sp = None
        else:
            logger.info("Spotify credentials не заданы. Будет использоваться oEmbed fallback для треков.")

    @staticmethod
    def is_spotify_url(url: str) -> bool:
        """Проверяет, является ли строка ссылкой на Spotify."""
        return bool(SPOTIFY_URL_REGEX.search(url))

    async def extract_metadata(self, url: str) -> dict[str, Any]:
        """
        Извлекает данные по ссылке Spotify:
        Возвращает словарь:
        {
            "type": "track" | "playlist" | "album",
            "title": str,
            "thumbnail": str | None,
            "queries": list[str]  # Поисковые строки формата 'Artist - Title' для yt-dlp
        }
        """
        match = SPOTIFY_URL_REGEX.search(url)
        if not match:
            raise TrackFetchError("Некорректная ссылка на Spotify.")

        item_type = match.group("type")
        item_id = match.group("id")

        if self._sp:
            return await self._extract_with_api(item_type, item_id)
        else:
            # Fallback через oEmbed если нет ключей API
            if item_type == "track":
                return await self._extract_track_oembed(url)
            else:
                raise SpotifyConfigError(
                    "Для добавления альбомов и плейлистов Spotify необходимо настроить "
                    "`SPOTIFY_CLIENT_ID` и `SPOTIFY_CLIENT_SECRET` в `.env`."
                )

    async def _extract_with_api(self, item_type: str, item_id: str) -> dict[str, Any]:
        """Извлечение через официальный Spotify Web API."""
        try:
            if item_type == "track":
                track = self._sp.track(item_id)
                artists = ", ".join(artist["name"] for artist in track.get("artists", []))
                track_name = track.get("name", "Unknown Title")
                query = f"{artists} - {track_name}"
                images = track.get("album", {}).get("images", [])
                thumbnail = images[0]["url"] if images else None

                return {
                    "type": "track",
                    "title": f"{artists} — {track_name}",
                    "thumbnail": thumbnail,
                    "queries": [query],
                }

            elif item_type == "playlist":
                playlist = self._sp.playlist(item_id)
                playlist_name = playlist.get("name", "Spotify Playlist")
                images = playlist.get("images", [])
                thumbnail = images[0]["url"] if images else None

                queries: list[str] = []
                results = playlist.get("tracks", {})
                items = results.get("items", [])

                for item in items:
                    track = item.get("track")
                    if track and track.get("name"):
                        artists = ", ".join(a["name"] for a in track.get("artists", []))
                        queries.append(f"{artists} - {track['name']}")

                # Обработка пагинации для больших плейлистов (до 100 треков)
                while results.get("next") and len(queries) < 100:
                    results = self._sp.next(results)
                    for item in results.get("items", []):
                        track = item.get("track")
                        if track and track.get("name"):
                            artists = ", ".join(a["name"] for a in track.get("artists", []))
                            queries.append(f"{artists} - {track['name']}")

                return {
                    "type": "playlist",
                    "title": playlist_name,
                    "thumbnail": thumbnail,
                    "queries": queries,
                }

            elif item_type == "album":
                album = self._sp.album(item_id)
                album_name = album.get("name", "Spotify Album")
                images = album.get("images", [])
                thumbnail = images[0]["url"] if images else None
                album_artists = ", ".join(a["name"] for a in album.get("artists", []))

                queries = []
                for item in album.get("tracks", {}).get("items", []):
                    track_artists = ", ".join(a["name"] for a in item.get("artists", [])) or album_artists
                    queries.append(f"{track_artists} - {item.get('name')}")

                return {
                    "type": "album",
                    "title": f"{album_artists} — {album_name}",
                    "thumbnail": thumbnail,
                    "queries": queries,
                }

            else:
                raise TrackFetchError(f"Неподдерживаемый тип ссылки Spotify: {item_type}")

        except Exception as e:
            logger.error(f"Ошибка при запросе к Spotify API ({item_type}:{item_id}): {e}")
            raise TrackFetchError(f"Не удалось получить данные из Spotify: {e}")

    async def _extract_track_oembed(self, url: str) -> dict[str, Any]:
        """Запасной метод извлечения метаданных одного трека без API ключей."""
        oembed_url = f"https://open.spotify.com/oembed?url={url}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        raise TrackFetchError(f"Spotify oEmbed вернул статус {resp.status}")
                    data = await resp.json()

            title = data.get("title", "Unknown Track")
            thumbnail = data.get("thumbnail_url")
            return {
                "type": "track",
                "title": title,
                "thumbnail": thumbnail,
                "queries": [title],
            }
        except Exception as e:
            logger.error(f"Ошибка oEmbed Spotify: {e}")
            raise TrackFetchError("Не удалось получить информацию о треке Spotify.")


# Синглтон клиента Spotify
spotify_client = SpotifyClient()
