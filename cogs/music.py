"""
Модуль Cogs для управления музыкальной системой (/play, /skip, /queue и т.д.).
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Literal
import discord
from discord import app_commands
from discord.ext import commands

from config import config
from core.checks import ensure_voice_connection
from core.errors import MusicBotException, QueueEmptyError, TrackFetchError
from music.player import MusicPlayer
from music.queue import LoopMode
from music.source import Track, YTDLSource
from music.spotify import spotify_client
from music.views import QueuePaginationView, SongSelectView

logger = logging.getLogger("DiscordBot.MusicCog")


class MusicCog(commands.Cog, name="Music"):
    """Основной ког музыкального плеера."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, MusicPlayer] = {}
        self.autocomplete_cache: dict[str, list[app_commands.Choice[str]]] = {}

    def get_player(self, guild: discord.Guild) -> MusicPlayer:
        """Получает или создает экземпляр MusicPlayer для сервера."""
        if guild.id not in self.players:
            self.players[guild.id] = MusicPlayer(self.bot, guild)
        return self.players[guild.id]

    async def _ensure_voice_client(self, interaction: discord.Interaction) -> tuple[MusicPlayer, discord.VoiceClient]:
        """Подключает бота к голосовому каналу пользователя при необходимости."""
        player = self.get_player(interaction.guild)  # type: ignore
        user: discord.Member = interaction.user  # type: ignore

        if not user.voice or not user.voice.channel:
            raise MusicBotException("Вы должны находиться в голосовом канале!")

        target_channel = user.voice.channel
        voice_client: discord.VoiceClient | None = interaction.guild.voice_client  # type: ignore

        if not voice_client or not voice_client.is_connected():
            voice_client = await target_channel.connect(self_deaf=True)
            player.voice_client = voice_client
            logger.info(f"Бот подключился к голосовому каналу '{target_channel.name}' на сервере '{interaction.guild.name}'")
        elif voice_client.channel.id != target_channel.id:
            await voice_client.move_to(target_channel)

        player.voice_client = voice_client
        player.text_channel = interaction.channel  # type: ignore
        return player, voice_client

    # --------------------------------------------------------------------------
    # Слэш-команда: /play
    # --------------------------------------------------------------------------
    @app_commands.command(name="play", description="Воспроизвести музыку по названию или ссылке (YouTube, SoundCloud, Spotify)")
    @app_commands.describe(query="Ссылка (YouTube/SoundCloud/Spotify) или поисковый запрос трека")
    @ensure_voice_connection(check_bot_connected=False, require_same_channel=False)
    async def play_command(self, interaction: discord.Interaction, query: str) -> None:
        """Обработка команды воспроизведения музыки."""
        query = query.strip()
        if not query:
            await interaction.response.send_message("❌ Укажите поисковый запрос или ссылку на трек!", ephemeral=True)
            return

        # 1. Spotify ссылки
        if spotify_client.is_spotify_url(query):
            await interaction.response.defer()
            player, _ = await self._ensure_voice_client(interaction)
            await self._handle_spotify_query(interaction, player, query)
            return

        # 2. Прямые ссылки на YouTube / SoundCloud
        if query.startswith(("http://", "https://")):
            await interaction.response.defer()
            player, _ = await self._ensure_voice_client(interaction)

            # Проверяем, является ли ссылка плейлистом
            if "playlist" in query or "list=" in query:
                await self._handle_url_playlist(interaction, player, query)
            else:
                await self._handle_single_track(interaction, player, query)
            return

        # 3. Текстовый поисковый запрос -> прямое воспроизведение лучшего совпадения
        await interaction.response.defer()
        player, _ = await self._ensure_voice_client(interaction)
        await self._handle_text_query(interaction, player, query)

    @play_command.autocomplete("query")
    async def play_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Автодополнение поиска треков YouTube прямо в интерфейсе Discord при вводе."""
        current = current.strip()
        if not current:
            return [
                app_commands.Choice(name="🎵 Rick Astley - Never Gonna Give You Up", value="Rick Astley Never Gonna Give You Up"),
                app_commands.Choice(name="🎵 Queen - Bohemian Rhapsody", value="Queen Bohemian Rhapsody"),
                app_commands.Choice(name="🎵 Смысловые Галлюцинации - Вечно Молодой", value="вечно молодой"),
            ]

        # Если вводится прямая ссылка
        if current.startswith(("http://", "https://")):
            return [app_commands.Choice(name=f"🔗 Прямая ссылка: {current[:80]}", value=current)]

        # Проверяем кэш
        cache_key = current.lower()
        if cache_key in self.autocomplete_cache:
            return self.autocomplete_cache[cache_key]

        try:
            results = await asyncio.wait_for(YTDLSource.search_top5(current), timeout=2.2)
            choices = []
            for item in results[:5]:
                name = f"🎵 {item['title'][:75]} ({item['duration_str']})"[:100]
                choices.append(app_commands.Choice(name=name, value=item["url"]))

            if len(self.autocomplete_cache) > 200:
                self.autocomplete_cache.clear()
            self.autocomplete_cache[cache_key] = choices
            return choices
        except Exception:
            return []

    @staticmethod
    async def _delete_after(msg: discord.Message | discord.WebhookMessage, delay: float = 5.0) -> None:
        """Безопасное удаление временного уведомления через указанное время."""
        try:
            await asyncio.sleep(delay)
            await msg.delete()
        except Exception:
            pass

    async def _handle_single_track(self, interaction: discord.Interaction, player: MusicPlayer, url: str) -> None:
        """Загрузка одиночного трека по прямой ссылке."""
        try:
            track = await YTDLSource.fetch_track(url, requester=interaction.user)  # type: ignore
            player.queue.add(track)

            if not player.is_playing and not player.is_paused:
                msg = await interaction.followup.send(f"▶️ Запуск: **[{track.title}]({track.webpage_url})**")
                asyncio.create_task(self._delete_after(msg, 4))
                player.start_loop()
            else:
                embed = discord.Embed(
                    description=f"➕ Добавлен в очередь (`#{len(player.queue)}`): **[{track.title}]({track.webpage_url})** (`{track.formatted_duration}`)",
                    color=discord.Color.green(),
                )
                msg = await interaction.followup.send(embed=embed)
                asyncio.create_task(self._delete_after(msg, 6))

        except Exception as e:
            logger.error(f"Ошибка загрузки трека: {e}")
            raise TrackFetchError(f"Не удалось загрузить трек по ссылке: {e}")

    async def _handle_url_playlist(self, interaction: discord.Interaction, player: MusicPlayer, playlist_url: str) -> None:
        """Загрузка плейлиста YouTube/SoundCloud с мгновенным добавлением всех треков."""
        try:
            title, entries_data = await YTDLSource.fetch_playlist_entries(playlist_url)
            if not entries_data:
                raise TrackFetchError("Плейлист пуст или закрыт для доступа.")

            tracks: list[Track] = []
            for item in entries_data:
                track = Track(
                    title=item["title"],
                    stream_url=None,  # Разрешается лениво перед воспроизведением
                    webpage_url=item["url"],
                    duration=item["duration"],
                    thumbnail=item["thumbnail"],
                    uploader=item["uploader"],
                    requester=interaction.user,  # type: ignore
                    source_type="YouTube",
                )
                tracks.append(track)

            player.queue.extend(tracks)

            embed = discord.Embed(
                description=f"✅ Плейлист **{title}** добавлен (`{len(tracks)}` треков).",
                color=discord.Color.purple(),
            )
            msg = await interaction.followup.send(embed=embed)
            asyncio.create_task(self._delete_after(msg, 6))

            if not player.is_playing and not player.is_paused:
                player.start_loop()

        except Exception as e:
            logger.error(f"Ошибка плейлиста: {e}")
            raise TrackFetchError(f"Не удалось обработать плейлист: {e}")

    async def _handle_spotify_query(self, interaction: discord.Interaction, player: MusicPlayer, spotify_url: str) -> None:
        """Обработка треков и плейлистов Spotify."""
        data = await spotify_client.extract_metadata(spotify_url)
        item_type = data["type"]
        queries = data["queries"]

        if not queries:
            raise TrackFetchError("В указанной ссылке Spotify не найдены треки.")

        if item_type == "track":
            track = await YTDLSource.fetch_track(queries[0], requester=interaction.user, source_type="Spotify")  # type: ignore
            if data.get("thumbnail"):
                track.thumbnail = data["thumbnail"]
            player.queue.add(track)

            if not player.is_playing and not player.is_paused:
                msg = await interaction.followup.send(
                    f"▶️ Запуск Spotify: **[{track.title}]({track.webpage_url})**"
                )
                asyncio.create_task(self._delete_after(msg, 4))
                player.start_loop()
            else:
                embed = discord.Embed(
                    description=f"➕ Добавлен из Spotify (`#{len(player.queue)}`): **[{track.title}]({track.webpage_url})** (`{track.formatted_duration}`)",
                    color=discord.Color.from_rgb(30, 215, 96),
                )
                msg = await interaction.followup.send(embed=embed)
                asyncio.create_task(self._delete_after(msg, 6))
        else:
            tracks: list[Track] = []
            for q in queries:
                track = Track(
                    title=q,
                    stream_url=None,  # Разрешается лениво перед воспроизведением
                    webpage_url="",
                    duration=0,
                    thumbnail=data.get("thumbnail"),
                    uploader="Spotify",
                    requester=interaction.user,  # type: ignore
                    source_type="Spotify",
                    query=q,
                )
                tracks.append(track)

            player.queue.extend(tracks)

            embed = discord.Embed(
                description=f"✅ Spotify **{data['title']}** добавлен (`{len(tracks)}` треков).",
                color=discord.Color.from_rgb(30, 215, 96),
            )
            msg = await interaction.followup.send(embed=embed)
            asyncio.create_task(self._delete_after(msg, 6))

            if not player.is_playing and not player.is_paused:
                player.start_loop()

    async def _handle_text_query(self, interaction: discord.Interaction, player: MusicPlayer, query: str) -> None:
        """Поиск и немедленное воспроизведение лучшего совпадения на YouTube."""
        try:
            track = await YTDLSource.fetch_track(query, requester=interaction.user)  # type: ignore
            player.queue.add(track)

            if not player.is_playing and not player.is_paused:
                msg = await interaction.followup.send(f"▶️ Запуск: **[{track.title}]({track.webpage_url})**")
                asyncio.create_task(self._delete_after(msg, 4))
                player.start_loop()
            else:
                embed = discord.Embed(
                    description=f"➕ Добавлен в очередь (`#{len(player.queue)}`): **[{track.title}]({track.webpage_url})** (`{track.formatted_duration}`)",
                    color=discord.Color.green(),
                )
                msg = await interaction.followup.send(embed=embed)
                asyncio.create_task(self._delete_after(msg, 6))

        except Exception as e:
            logger.error(f"Ошибка при поиске трека '{query}': {e}", exc_info=True)
            raise TrackFetchError(f"Не удалось найти или загрузить трек по запросу «{query}»: {e}")

    # --------------------------------------------------------------------------
    # Слэш-команда: /search
    # --------------------------------------------------------------------------
    @app_commands.command(name="search", description="Интерактивный поиск треков с меню выбора Топ-5")
    @app_commands.describe(query="Поисковый запрос трека на YouTube")
    @ensure_voice_connection(check_bot_connected=False, require_same_channel=False)
    async def search_command(self, interaction: discord.Interaction, query: str) -> None:
        """Поиск с интерактивным меню Топ-5 для ручного выбора трека."""
        query = query.strip()
        if not query:
            await interaction.response.send_message("❌ Укажите поисковый запрос!", ephemeral=True)
            return

        await interaction.response.defer()
        player, _ = await self._ensure_voice_client(interaction)
        await self._handle_search_query(interaction, player, query)

    @search_command.autocomplete("query")
    async def search_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return await self.play_autocomplete(interaction, current)

    async def _handle_search_query(self, interaction: discord.Interaction, player: MusicPlayer, query: str) -> None:
        """Поиск топ-5 результатов с отображением выпадающего списка Select Menu."""
        results = await YTDLSource.search_top5(query)
        if not results:
            await interaction.followup.send("❌ По вашему запросу ничего не найдено.")
            return

        embed = discord.Embed(
            title=f"🔎 Результаты поиска: «{query}»",
            description="Выберите трек из выпадающего списка ниже в течение 60 секунд:",
            color=discord.Color.blurple(),
        )
        for i, item in enumerate(results, 1):
            embed.add_field(
                name=f"{i}. {item['title'][:65]}",
                value=f"👤 `{item['uploader']}` • ⏳ `{item['duration_str']}`",
                inline=False,
            )

        async def _on_select(select_interaction: discord.Interaction, selected_data: dict):
            # Немедленно подтверждаем выбор в выпадающем списке
            loading_embed = discord.Embed(
                title="⏳ Загрузка выбранного трека...",
                description=f"Получение потока для: **{selected_data['title']}**",
                color=discord.Color.blue(),
            )
            await select_interaction.response.edit_message(embed=loading_embed, view=None)

            try:
                track = await YTDLSource.fetch_track(selected_data["url"], requester=select_interaction.user)  # type: ignore
                player.queue.add(track)

                if not player.is_playing and not player.is_paused:
                    res_embed = discord.Embed(
                        title="🎶 Выбранный трек запускается",
                        description=f"**[{track.title}]({track.webpage_url})**",
                        color=discord.Color.green(),
                    )
                    player.start_loop()
                else:
                    res_embed = discord.Embed(
                        title="➕ Трек добавлен в очередь",
                        description=f"**[{track.title}]({track.webpage_url})**",
                        color=discord.Color.green(),
                    )
                    res_embed.add_field(name="⏳ Длительность", value=f"`{track.formatted_duration}`", inline=True)
                    res_embed.add_field(name="📊 Позиция в очереди", value=f"`#{len(player.queue)}`", inline=True)

                if track.thumbnail:
                    res_embed.set_thumbnail(url=track.thumbnail)

                await select_interaction.edit_original_response(embed=res_embed, view=None)
            except Exception as e:
                logger.error(f"Ошибка при загрузке выбранного трека: {e}", exc_info=True)
                err_embed = discord.Embed(
                    title="❌ Ошибка загрузки",
                    description=f"Не удалось загрузить выбранный трек: {e}",
                    color=discord.Color.red(),
                )
                await select_interaction.edit_original_response(embed=err_embed, view=None)

        view = SongSelectView(
            tracks=results,
            author=interaction.user,  # type: ignore
            callback_coro=_on_select,
        )
        await interaction.followup.send(embed=embed, view=view)

    # --------------------------------------------------------------------------
    # Слэш-команды управления плеером
    # --------------------------------------------------------------------------
    @app_commands.command(name="pause", description="Приостановить воспроизведение музыки")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=True)
    async def pause_command(self, interaction: discord.Interaction) -> None:
        player = self.get_player(interaction.guild)  # type: ignore
        if not player.voice_client or not player.voice_client.is_playing():
            await interaction.response.send_message("❌ Сейчас ничего не воспроизводится.", ephemeral=True)
            return

        player.voice_client.pause()
        await interaction.response.send_message("⏸️ Воспроизведение приостановлено.", delete_after=4)

    @app_commands.command(name="resume", description="Возобновить воспроизведение музыки")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=True)
    async def resume_command(self, interaction: discord.Interaction) -> None:
        player = self.get_player(interaction.guild)  # type: ignore
        if not player.voice_client or not player.voice_client.is_paused():
            await interaction.response.send_message("❌ Плеер не находится на паузе.", ephemeral=True)
            return

        player.voice_client.resume()
        await interaction.response.send_message("▶️ Воспроизведение возобновлено.", delete_after=4)

    @app_commands.command(name="skip", description="Пропустить текущий трек")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=True)
    async def skip_command(self, interaction: discord.Interaction) -> None:
        player = self.get_player(interaction.guild)  # type: ignore
        if not player.voice_client or not (player.voice_client.is_playing() or player.voice_client.is_paused()):
            await interaction.response.send_message("❌ Сейчас ничего не играет для пропуска.", ephemeral=True)
            return

        curr = player.skip()
        await interaction.response.send_message(f"⏭️ Пропущен: **{curr.title if curr else 'Трек'}**", delete_after=4)

    @app_commands.command(name="stop", description="Остановить плеер, очистить очередь и выйти из канала")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=True)
    async def stop_command(self, interaction: discord.Interaction) -> None:
        player = self.get_player(interaction.guild)  # type: ignore
        await player.stop(disconnect=True)
        await interaction.response.send_message("⏹️ Плеер остановлен, очередь очищена.", delete_after=5)

    @app_commands.command(name="queue", description="Показать текущую очередь воспроизведения")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=False)
    async def queue_command(self, interaction: discord.Interaction) -> None:
        player = self.get_player(interaction.guild)  # type: ignore
        tracks = player.queue.tracks
        current = player.queue.current

        if not current and not tracks:
            raise QueueEmptyError()

        # Разбиваем очередь по страницам (по 10 треков)
        PAGE_SIZE = 10
        total_pages = max(1, math.ceil(len(tracks) / PAGE_SIZE))
        pages: list[discord.Embed] = []

        for p in range(total_pages):
            embed = discord.Embed(
                title=f"📋 Очередь воспроизведения • Страница {p + 1} из {total_pages}",
                color=discord.Color.purple(),
            )

            desc_lines: list[str] = []

            # Блок текущего трека
            if current:
                curr_url = current.webpage_url if (current.webpage_url and current.webpage_url.startswith("http")) else ""
                clean_curr_title = " ".join(current.title.split())[:45]
                curr_title = f"[{clean_curr_title}]({curr_url})" if curr_url else f"**{clean_curr_title}**"
                desc_lines.append(
                    f"**🎶 Сейчас играет:**\n"
                    f"{curr_title} (`{current.formatted_duration}`) • {current.requester.mention}\n"
                )

            start_idx = p * PAGE_SIZE
            page_tracks = tracks[start_idx : start_idx + PAGE_SIZE]

            if not page_tracks:
                desc_lines.append("*В очереди нет других треков.*")
            else:
                desc_lines.append(f"**Далее в очереди ({len(tracks)} треков):**")
                for i, t in enumerate(page_tracks, start=start_idx + 1):
                    t_url = t.webpage_url if (t.webpage_url and t.webpage_url.startswith("http")) else ""
                    clean_t_title = " ".join(t.title.split())[:45]
                    t_title = f"[{clean_t_title}]({t_url})" if t_url else f"**{clean_t_title}**"
                    desc_lines.append(f"`{i}.` {t_title} (`{t.formatted_duration}`) • {t.requester.mention}")

            full_desc = "\n".join(desc_lines)
            if len(full_desc) > 3900:
                full_desc = full_desc[:3890] + "\n..."
            embed.description = full_desc

            embed.set_footer(
                text=f"Режим цикла: {player.queue.loop_mode.value} • Громкость: {int(player.volume * 100)}%"
            )
            pages.append(embed)

        if len(pages) > 1:
            view = QueuePaginationView(pages, author=interaction.user)  # type: ignore
            await interaction.response.send_message(embed=pages[0], view=view)
        else:
            await interaction.response.send_message(embed=pages[0])

    @app_commands.command(name="nowplaying", description="Показать подробную информацию о текущем треке с кнопками")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=False)
    async def nowplaying_command(self, interaction: discord.Interaction) -> None:
        player = self.get_player(interaction.guild)  # type: ignore
        if not player.queue.current:
            await interaction.response.send_message("❌ В данный момент ничего не воспроизводится.", ephemeral=True)
            return

        embed = player.build_now_playing_embed()
        # Отправляем карточку
        from music.views import PlayerControlView
        view = PlayerControlView(player)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="loop", description="Переключить режим зацикливания воспроизведения")
    @app_commands.describe(mode="Режим: off (выкл), track (текущий трек), queue (вся очередь)")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=True)
    async def loop_command(
        self,
        interaction: discord.Interaction,
        mode: Literal["off", "track", "queue"] | None = None,
    ) -> None:
        player = self.get_player(interaction.guild)  # type: ignore
        if mode == "off":
            player.queue.loop_mode = LoopMode.OFF
        elif mode == "track":
            player.queue.loop_mode = LoopMode.TRACK
        elif mode == "queue":
            player.queue.loop_mode = LoopMode.QUEUE
        else:
            player.queue.cycle_loop_mode()

        current_mode = player.queue.loop_mode
        await interaction.response.send_message(
            f"{current_mode.emoji} Режим зацикливания: **{current_mode.value}**",
            delete_after=4,
        )

    @app_commands.command(name="shuffle", description="Перемешать треки в очереди")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=True)
    async def shuffle_command(self, interaction: discord.Interaction) -> None:
        player = self.get_player(interaction.guild)  # type: ignore
        if len(player.queue) < 2:
            await interaction.response.send_message("❌ В очереди недостаточно треков для перемешивания.", ephemeral=True)
            return

        player.queue.shuffle()
        await interaction.response.send_message(f"🔀 Очередь перемешана ({len(player.queue)} треков).", delete_after=4)

    @app_commands.command(name="volume", description="Изменить громкость воспроизведения музыки (0 - 100%)")
    @app_commands.describe(level="Уровень громкости от 0 до 100")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=True)
    async def volume_command(self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]) -> None:
        player = self.get_player(interaction.guild)  # type: ignore
        player.set_volume(level)
        await interaction.response.send_message(f"🔊 Громкость: **{level}%**", delete_after=4)

    @app_commands.command(name="remove", description="Удалить трек из очереди по номеру")
    @app_commands.describe(index="Номер трека в очереди (/queue)")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=True)
    async def remove_command(self, interaction: discord.Interaction, index: int) -> None:
        player = self.get_player(interaction.guild)  # type: ignore
        removed = player.queue.remove(index)
        if not removed:
            await interaction.response.send_message(f"❌ Трек с номером `#{index}` не найден в очереди.", ephemeral=True)
            return

        await interaction.response.send_message(f"🗑️ Удален трек `#{index}`: **{removed.title}**", delete_after=5)

    # --------------------------------------------------------------------------
    # Слушатель событий голосового канала (Auto-leave & Cleanup)
    # --------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Отслеживает отключение пользователей или кик бота из войса."""
        guild = member.guild
        voice_client: discord.VoiceClient | None = guild.voice_client

        if not voice_client or not voice_client.channel:
            return

        # 1. Если бота отключили вручную
        if member.id == self.bot.user.id and before.channel and not after.channel:
            logger.info(f"Бот был отключен от голосового канала на сервере {guild.name}")
            player = self.players.get(guild.id)
            if player:
                await player.stop(disconnect=False)
            return

        # 2. Если в канале остался один бот (все пользователи вышли)
        non_bot_members = [m for m in voice_client.channel.members if not m.bot]
        if len(non_bot_members) == 0:
            logger.info(f"В канале '{voice_client.channel.name}' не осталось людей. Запуск таймера выхода...")
            await asyncio.sleep(30)  # Даем 30 секунд, вдруг кто-то переподключается
            # Перепроверяем
            if voice_client.is_connected() and len([m for m in voice_client.channel.members if not m.bot]) == 0:
                player = self.players.get(guild.id)
                if player:
                    if player.text_channel:
                        try:
                            await player.text_channel.send("👋 Все участники вышли из голосового канала. Бот отключился.")
                        except Exception:
                            pass
                    await player.stop(disconnect=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
