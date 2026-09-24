"""
Модуль управления воспроизведением звука на уровне гильдии (MusicPlayer).
Контролирует цикл очереди, таймер бездействия, UI-сообщения и прогресс-бар.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING
import discord

from config import config
from music.queue import LoopMode, MusicQueue
from music.source import Track
from music.views import PlayerControlView

if TYPE_CHECKING:
    from discord.ext import commands

logger = logging.getLogger("DiscordBot.Player")


class MusicPlayer:
    """Контроллер воспроизведения музыки для конкретного сервера (Guild)."""

    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.queue = MusicQueue()

        self.voice_client: discord.VoiceClient | None = None
        self.text_channel: discord.TextChannel | None = None
        self.now_playing_message: discord.Message | None = None
        self.current_source: discord.PCMVolumeTransformer | None = None

        self.volume: float = config.default_volume / 100.0
        self.is_looping: bool = False

        # Синхронизация и задачи воспроизведения
        self._current_play_id: int = 0
        self._skip_requested: bool = False
        self._playback_finished = asyncio.Event()
        self._player_task: asyncio.Task | None = None
        self._idle_task: asyncio.Task | None = None

        # Отслеживание времени для прогресс-бара
        self.track_start_time: float = 0.0
        self.pause_start_time: float = 0.0
        self.total_paused_seconds: float = 0.0

    @property
    def is_playing(self) -> bool:
        """Проверяет, воспроизводится ли аудио в данный момент."""
        return bool(self.voice_client and self.voice_client.is_playing())

    @property
    def is_paused(self) -> bool:
        """Проверяет, находится ли воспроизведение на паузе."""
        return bool(self.voice_client and self.voice_client.is_paused())

    def start_loop(self) -> None:
        """Запускает фоновую задачу цикла воспроизведения."""
        if self._player_task is None or self._player_task.done():
            self._player_task = asyncio.create_task(self._player_loop())

    @staticmethod
    async def _delete_temp_msg(msg: discord.Message, delay: float = 5.0) -> None:
        try:
            await asyncio.sleep(delay)
            await msg.delete()
        except Exception:
            pass

    async def _player_loop(self) -> None:
        """Основной асинхронный цикл извлечения и воспроизведения треков."""
        await self.bot.wait_until_ready()

        while True:
            # Получаем следующий трек с учетом флага явного пропуска
            is_skip = self._skip_requested
            self._skip_requested = False
            track = self.queue.get_next(is_skip=is_skip)

            if not track:
                # Очередь пуста: запускаем таймер бездействия
                self._start_idle_task()
                # Ждем, пока кто-нибудь не добавит трек или бот не отключится
                break

            # Отменяем таймер бездействия, если он работал
            self._cancel_idle_task()

            # Проверяем голосовое соединение и ждем завершения подключения при необходимости
            if self.voice_client and not self.voice_client.is_connected():
                try:
                    await asyncio.wait_for(self.voice_client.wait_until_connected(), timeout=5.0)
                except (asyncio.TimeoutError, Exception):
                    pass

            if not self.voice_client or not self.voice_client.is_connected():
                logger.warning(f"Голосовое соединение не активно в гильдии {self.guild.name}")
                break

            # Разрешаем прямой аудиопоток перед воспроизведением (ленивая подгрузка)
            try:
                await track.ensure_stream_url()
            except Exception as e:
                logger.warning(f"Не удалось получить аудиопоток для '{track.title}': {e}")
                if self.text_channel:
                    try:
                        msg = await self.text_channel.send(
                            f"⚠️ Пропуск недоступного трека: **{track.title}**"
                        )
                        asyncio.create_task(self._delete_temp_msg(msg, 5))
                    except Exception:
                        pass
                await asyncio.sleep(0.5)
                continue

            try:
                # Генерируем уникальный play_id для текущей сессии воспроизведения
                self._current_play_id += 1
                current_play_id = self._current_play_id
                self._playback_finished = asyncio.Event()

                # Если предыдущий источник еще активен, останавливаем его
                if self.voice_client.is_playing() or self.voice_client.is_paused():
                    self.voice_client.stop()
                    await asyncio.sleep(0.1)

                # Создаем аудиоисточник
                self.current_source = track.create_audio_source(volume=self.volume)
                self.track_start_time = time.time()
                self.pause_start_time = 0.0
                self.total_paused_seconds = 0.0

                def _after_callback(error: Exception | None, pid: int = current_play_id) -> None:
                    self.bot.loop.call_soon_threadsafe(self._handle_playback_finished, error, pid)

                # Запускаем воспроизведение через голосовой клиент
                self.voice_client.play(self.current_source, after=_after_callback)
                logger.info(f"Запущено воспроизведение: '{track.title}' на сервере '{self.guild.name}' (play_id={current_play_id})")

                # Отправляем / обновляем красивый Now Playing Embed с кнопками
                await self._send_now_playing(track)

                # Ожидаем завершения воспроизведения текущего трека
                await self._playback_finished.wait()

            except Exception as e:
                logger.error(f"Ошибка воспроизведения трека '{track.title}': {e}", exc_info=True)
                if self.text_channel:
                    try:
                        msg = await self.text_channel.send(
                            f"⚠️ Ошибка при воспроизведении `{track.title}`. Переход к следующему треку..."
                        )
                        asyncio.create_task(self._delete_temp_msg(msg, 5))
                    except Exception:
                        pass
                await asyncio.sleep(1)

        # Выход из цикла
        self._player_task = None

    def _handle_playback_finished(self, error: Exception | None, play_id: int) -> None:
        """Callback завершения воспроизведения трека с фильтрацией устаревших вызовов."""
        if play_id != self._current_play_id:
            logger.debug(f"Игнорирование устаревшего after-callback для play_id={play_id} (текущий: {self._current_play_id})")
            return

        if error:
            logger.error(f"FFmpeg ошибка воспроизведения: {error}")
        else:
            curr_title = self.queue.current.title if self.queue.current else "трек"
            logger.info(f"Воспроизведение завершено: {curr_title}")

        if self._playback_finished:
            self._playback_finished.set()

    async def _send_now_playing(self, track: Track) -> None:
        """Отправляет или обновляет карточку Now Playing с интерактивным UI."""
        if not self.text_channel:
            return

        embed = self.build_now_playing_embed()
        view = PlayerControlView(self)

        try:
            # Удаляем предыдущее сообщение Now Playing, чтобы не спамить в чат
            if self.now_playing_message:
                try:
                    await self.now_playing_message.delete()
                except Exception:
                    pass

            self.now_playing_message = await self.text_channel.send(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Не удалось отправить Now Playing сообщение: {e}")

    def get_elapsed_seconds(self) -> int:
        """Рассчитывает количество прошедших секунд текущего трека."""
        if not self.track_start_time:
            return 0

        now = time.time()
        if self.is_paused and self.pause_start_time > 0:
            current_pause = now - self.pause_start_time
        else:
            current_pause = 0.0

        elapsed = int(now - self.track_start_time - self.total_paused_seconds - current_pause)
        return max(0, elapsed)

    def _create_progress_bar(self, elapsed: int, total: int, bar_length: int = 15) -> str:
        """Генерирует визуальный прогресс-бар: 🔘▬▬▬▬▬▬▬▬ 01:23 / 03:45."""
        if total <= 0:
            return "🔴 **Прямой эфир (Live stream)**"

        progress = min(1.0, max(0.0, elapsed / total))
        circle_pos = int(progress * bar_length)

        bar = ""
        for i in range(bar_length):
            if i == circle_pos:
                bar += "🔘"
            else:
                bar += "▬"

        def fmt_time(seconds: int) -> str:
            m, s = divmod(seconds, 60)
            h, m = divmod(m, 60)
            return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

        return f"`{bar}` `{fmt_time(elapsed)} / {fmt_time(total)}`"

    def build_now_playing_embed(self, status_text: str | None = None) -> discord.Embed:
        """Создает стильный минималистичный Embed текущего воспроизводимого трека."""
        track = self.queue.current
        if not track:
            return discord.Embed(
                description="🎵 Очередь пуста. Воспользуйтесь `/play` для добавления музыки.",
                color=discord.Color.dark_grey(),
            )

        elapsed = self.get_elapsed_seconds()
        progress_bar = self._create_progress_bar(elapsed, track.duration)

        embed = discord.Embed(
            description=(
                f"### 🎶 [{track.title}]({track.webpage_url})\n"
                f"👤 `{track.uploader}` • 🎧 {track.requester.mention}\n\n"
                f"{progress_bar}"
            ),
            color=discord.Color.from_rgb(138, 43, 226),
        )

        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)

        status_prefix = f"{status_text} • " if status_text else ("⏸️ На паузе • " if self.is_paused else "")
        loop_str = f" • {self.queue.loop_mode.emoji} {self.queue.loop_mode.value}" if self.queue.loop_mode != LoopMode.OFF else ""
        queue_str = f" • В очереди: {len(self.queue)}" if len(self.queue) > 0 else ""
        embed.set_footer(text=f"{status_prefix}🔊 {int(self.volume * 100)}%{loop_str}{queue_str}")

        return embed

    def skip(self) -> Track | None:
        """Пропускает текущий трек и возвращает его."""
        current = self.queue.current
        self._skip_requested = True

        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()
        else:
            if self._playback_finished:
                self._playback_finished.set()

        return current

    def set_volume(self, volume: int) -> None:
        """Устанавливает уровень громкости воспроизведения (0 - 100)."""
        self.volume = max(0, min(100, volume)) / 100.0
        if self.current_source:
            self.current_source.volume = self.volume

    async def stop(self, disconnect: bool = True) -> None:
        """Полная остановка: очистка очереди, остановка звука и выход из войса."""
        self._current_play_id += 1  # Инвалидирует любые pending callbacks
        self._skip_requested = False
        self.queue.clear()
        self.queue.current = None

        if self.voice_client:
            if self.voice_client.is_playing() or self.voice_client.is_paused():
                self.voice_client.stop()

            if disconnect:
                await self.voice_client.disconnect()
                self.voice_client = None

        self._cancel_idle_task()
        if self._player_task and not self._player_task.done():
            self._player_task.cancel()
            self._player_task = None

    def _start_idle_task(self) -> None:
        """Запускает таймер бездействия (auto-disconnect)."""
        self._cancel_idle_task()
        self._idle_task = asyncio.create_task(self._idle_timeout())

    def _cancel_idle_task(self) -> None:
        """Отменяет таймер бездействия."""
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
            self._idle_task = None

    async def _idle_timeout(self) -> None:
        """Фоновый таймер выхода при отсутствии треков в очереди."""
        try:
            logger.info(f"Запущен таймер бездействия ({config.idle_timeout} сек.) в гильдии {self.guild.name}")
            await asyncio.sleep(config.idle_timeout)

            # Если треков так и не появилось, отключаемся
            if self.queue.is_empty and not self.is_playing:
                logger.info(f"Автоотключение из-за неактивности в гильдии {self.guild.name}")
                if self.text_channel:
                    embed = discord.Embed(
                        description="⏰ **Бот покинул голосовой канал из-за неактивности.**",
                        color=discord.Color.dark_grey(),
                    )
                    await self.text_channel.send(embed=embed)

                await self.stop(disconnect=True)

        except asyncio.CancelledError:
            # Таймер был прерван новым треком
            pass
