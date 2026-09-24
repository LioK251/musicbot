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
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, MusicPlayer] = {}
        self.autocomplete_cache: dict[str, list[app_commands.Choice[str]]] = {}

    def get_player(self, guild: discord.Guild) -> MusicPlayer:
        if guild.id not in self.players:
            self.players[guild.id] = MusicPlayer(self.bot, guild)
        return self.players[guild.id]

    async def _ensure_voice_client(self, interaction: discord.Interaction) -> tuple[MusicPlayer, discord.VoiceClient]:
        player = self.get_player(interaction.guild)
        user: discord.Member = interaction.user

        if not user.voice or not user.voice.channel:
            raise MusicBotException("You must be in a voice channel!")

        target_channel = user.voice.channel
        voice_client: discord.VoiceClient | None = interaction.guild.voice_client

        if not voice_client or not voice_client.is_connected():
            voice_client = await target_channel.connect(self_deaf=True)
            player.voice_client = voice_client
            logger.info(f"Bot connected to voice channel '{target_channel.name}' in guild '{interaction.guild.name}'")
        elif voice_client.channel.id != target_channel.id:
            await voice_client.move_to(target_channel)

        player.voice_client = voice_client
        player.text_channel = interaction.channel
        return player, voice_client

    @app_commands.command(name="play", description="Play audio by name or URL (YouTube, SoundCloud, Spotify)")
    @app_commands.describe(query="URL (YouTube/SoundCloud/Spotify) or search query")
    @ensure_voice_connection(check_bot_connected=False, require_same_channel=False)
    async def play_command(self, interaction: discord.Interaction, query: str) -> None:
        query = query.strip()
        if not query:
            await interaction.response.send_message("❌ Please provide a search query or track URL!", ephemeral=True)
            return

        if spotify_client.is_spotify_url(query):
            await interaction.response.defer()
            player, _ = await self._ensure_voice_client(interaction)
            await self._handle_spotify_query(interaction, player, query)
            return

        if query.startswith(("http://", "https://")):
            await interaction.response.defer()
            player, _ = await self._ensure_voice_client(interaction)

            if "playlist" in query or "list=" in query:
                await self._handle_url_playlist(interaction, player, query)
            else:
                await self._handle_single_track(interaction, player, query)
            return

        await interaction.response.defer()
        player, _ = await self._ensure_voice_client(interaction)
        await self._handle_text_query(interaction, player, query)

    @play_command.autocomplete("query")
    async def play_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        current = current.strip()
        if not current:
            return [
                app_commands.Choice(name="🎵 Rick Astley - Never Gonna Give You Up", value="Rick Astley Never Gonna Give You Up"),
                app_commands.Choice(name="🎵 Queen - Bohemian Rhapsody", value="Queen Bohemian Rhapsody"),
                app_commands.Choice(name="🎵 The Weeknd - Blinding Lights", value="The Weeknd Blinding Lights"),
            ]

        if current.startswith(("http://", "https://")):
            return [app_commands.Choice(name=f"🔗 Direct link: {current[:80]}", value=current)]

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
        try:
            await asyncio.sleep(delay)
            await msg.delete()
        except Exception:
            pass

    async def _handle_single_track(self, interaction: discord.Interaction, player: MusicPlayer, url: str) -> None:
        try:
            track = await YTDLSource.fetch_track(url, requester=interaction.user)
            player.queue.add(track)

            if not player.is_playing and not player.is_paused:
                msg = await interaction.followup.send(f"▶️ Playing: **[{track.title}]({track.webpage_url})**")
                asyncio.create_task(self._delete_after(msg, 4))
                player.start_loop()
            else:
                embed = discord.Embed(
                    description=f"➕ Added to queue (`#{len(player.queue)}`): **[{track.title}]({track.webpage_url})** (`{track.formatted_duration}`)",
                    color=discord.Color.green(),
                )
                msg = await interaction.followup.send(embed=embed)
                asyncio.create_task(self._delete_after(msg, 6))

        except Exception as e:
            logger.error(f"Error loading track: {e}")
            raise TrackFetchError(f"Failed to load track from URL: {e}")

    async def _handle_url_playlist(self, interaction: discord.Interaction, player: MusicPlayer, playlist_url: str) -> None:
        try:
            title, entries_data = await YTDLSource.fetch_playlist_entries(playlist_url)
            if not entries_data:
                raise TrackFetchError("Playlist is empty or unavailable.")

            tracks: list[Track] = []
            for item in entries_data:
                track = Track(
                    title=item["title"],
                    stream_url=None,
                    webpage_url=item["url"],
                    duration=item["duration"],
                    thumbnail=item["thumbnail"],
                    uploader=item["uploader"],
                    requester=interaction.user,
                    source_type="YouTube",
                )
                tracks.append(track)

            player.queue.extend(tracks)

            embed = discord.Embed(
                description=f"✅ Playlist **{title}** added (`{len(tracks)}` tracks).",
                color=discord.Color.purple(),
            )
            msg = await interaction.followup.send(embed=embed)
            asyncio.create_task(self._delete_after(msg, 6))

            if not player.is_playing and not player.is_paused:
                player.start_loop()

        except Exception as e:
            logger.error(f"Playlist error: {e}")
            raise TrackFetchError(f"Failed to process playlist: {e}")

    async def _handle_spotify_query(self, interaction: discord.Interaction, player: MusicPlayer, spotify_url: str) -> None:
        data = await spotify_client.extract_metadata(spotify_url)
        item_type = data["type"]
        queries = data["queries"]

        if not queries:
            raise TrackFetchError("No tracks found in the provided Spotify link.")

        if item_type == "track":
            track = await YTDLSource.fetch_track(queries[0], requester=interaction.user, source_type="Spotify")
            if data.get("thumbnail"):
                track.thumbnail = data["thumbnail"]
            player.queue.add(track)

            if not player.is_playing and not player.is_paused:
                msg = await interaction.followup.send(
                    f"▶️ Playing Spotify: **[{track.title}]({track.webpage_url})**"
                )
                asyncio.create_task(self._delete_after(msg, 4))
                player.start_loop()
            else:
                embed = discord.Embed(
                    description=f"➕ Added from Spotify (`#{len(player.queue)}`): **[{track.title}]({track.webpage_url})** (`{track.formatted_duration}`)",
                    color=discord.Color.from_rgb(30, 215, 96),
                )
                msg = await interaction.followup.send(embed=embed)
                asyncio.create_task(self._delete_after(msg, 6))
        else:
            tracks: list[Track] = []
            for q in queries:
                track = Track(
                    title=q,
                    stream_url=None,
                    webpage_url="",
                    duration=0,
                    thumbnail=data.get("thumbnail"),
                    uploader="Spotify",
                    requester=interaction.user,
                    source_type="Spotify",
                    query=q,
                )
                tracks.append(track)

            player.queue.extend(tracks)

            embed = discord.Embed(
                description=f"✅ Spotify **{data['title']}** added (`{len(tracks)}` tracks).",
                color=discord.Color.from_rgb(30, 215, 96),
            )
            msg = await interaction.followup.send(embed=embed)
            asyncio.create_task(self._delete_after(msg, 6))

            if not player.is_playing and not player.is_paused:
                player.start_loop()

    async def _handle_text_query(self, interaction: discord.Interaction, player: MusicPlayer, query: str) -> None:
        try:
            track = await YTDLSource.fetch_track(query, requester=interaction.user)
            player.queue.add(track)

            if not player.is_playing and not player.is_paused:
                msg = await interaction.followup.send(f"▶️ Playing: **[{track.title}]({track.webpage_url})**")
                asyncio.create_task(self._delete_after(msg, 4))
                player.start_loop()
            else:
                embed = discord.Embed(
                    description=f"➕ Added to queue (`#{len(player.queue)}`): **[{track.title}]({track.webpage_url})** (`{track.formatted_duration}`)",
                    color=discord.Color.green(),
                )
                msg = await interaction.followup.send(embed=embed)
                asyncio.create_task(self._delete_after(msg, 6))

        except Exception as e:
            logger.error(f"Error searching track '{query}': {e}", exc_info=True)
            raise TrackFetchError(f"Failed to find or load track for '{query}': {e}")

    @app_commands.command(name="search", description="Search YouTube tracks with top 5 selection menu")
    @app_commands.describe(query="Track search query")
    @ensure_voice_connection(check_bot_connected=False, require_same_channel=False)
    async def search_command(self, interaction: discord.Interaction, query: str) -> None:
        query = query.strip()
        if not query:
            await interaction.response.send_message("❌ Please provide a search query!", ephemeral=True)
            return

        await interaction.response.defer()
        player, _ = await self._ensure_voice_client(interaction)
        await self._handle_search_query(interaction, player, query)

    @search_command.autocomplete("query")
    async def search_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return await self.play_autocomplete(interaction, current)

    async def _handle_search_query(self, interaction: discord.Interaction, player: MusicPlayer, query: str) -> None:
        results = await YTDLSource.search_top5(query)
        if not results:
            await interaction.followup.send("❌ No results found for your query.")
            return

        embed = discord.Embed(
            title=f"🔎 Search Results: \"{query}\"",
            description="Select a track from the dropdown below within 60 seconds:",
            color=discord.Color.blurple(),
        )
        for i, item in enumerate(results, 1):
            embed.add_field(
                name=f"{i}. {item['title'][:65]}",
                value=f"👤 `{item['uploader']}` • ⏳ `{item['duration_str']}`",
                inline=False,
            )

        async def _on_select(select_interaction: discord.Interaction, selected_data: dict):
            loading_embed = discord.Embed(
                title="⏳ Loading selected track...",
                description=f"Fetching stream for: **{selected_data['title']}**",
                color=discord.Color.blue(),
            )
            await select_interaction.response.edit_message(embed=loading_embed, view=None)

            try:
                track = await YTDLSource.fetch_track(selected_data["url"], requester=select_interaction.user)
                player.queue.add(track)

                if not player.is_playing and not player.is_paused:
                    res_embed = discord.Embed(
                        title="🎶 Playing Selected Track",
                        description=f"**[{track.title}]({track.webpage_url})**",
                        color=discord.Color.green(),
                    )
                    player.start_loop()
                else:
                    res_embed = discord.Embed(
                        title="➕ Track Added to Queue",
                        description=f"**[{track.title}]({track.webpage_url})**",
                        color=discord.Color.green(),
                    )
                    res_embed.add_field(name="⏳ Duration", value=f"`{track.formatted_duration}`", inline=True)
                    res_embed.add_field(name="📊 Position in Queue", value=f"`#{len(player.queue)}`", inline=True)

                if track.thumbnail:
                    res_embed.set_thumbnail(url=track.thumbnail)

                await select_interaction.edit_original_response(embed=res_embed, view=None)
            except Exception as e:
                logger.error(f"Error loading selected track: {e}", exc_info=True)
                err_embed = discord.Embed(
                    title="❌ Loading Error",
                    description=f"Failed to load selected track: {e}",
                    color=discord.Color.red(),
                )
                await select_interaction.edit_original_response(embed=err_embed, view=None)

        view = SongSelectView(
            tracks=results,
            author=interaction.user,
            callback_coro=_on_select,
        )
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="pause", description="Pause music playback")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=True)
    async def pause_command(self, interaction: discord.Interaction) -> None:
        player = self.get_player(interaction.guild)
        if not player.voice_client or not player.voice_client.is_playing():
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
            return

        player.voice_client.pause()
        await interaction.response.send_message("⏸️ Playback paused.", delete_after=4)

    @app_commands.command(name="resume", description="Resume music playback")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=True)
    async def resume_command(self, interaction: discord.Interaction) -> None:
        player = self.get_player(interaction.guild)
        if not player.voice_client or not player.voice_client.is_paused():
            await interaction.response.send_message("❌ Player is not paused.", ephemeral=True)
            return

        player.voice_client.resume()
        await interaction.response.send_message("▶️ Playback resumed.", delete_after=4)

    @app_commands.command(name="skip", description="Skip current track")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=True)
    async def skip_command(self, interaction: discord.Interaction) -> None:
        player = self.get_player(interaction.guild)
        if not player.voice_client or not (player.voice_client.is_playing() or player.voice_client.is_paused()):
            await interaction.response.send_message("❌ Nothing is currently playing to skip.", ephemeral=True)
            return

        curr = player.skip()
        await interaction.response.send_message(f"⏭️ Skipped: **{curr.title if curr else 'Track'}**", delete_after=4)

    @app_commands.command(name="stop", description="Stop player, clear queue, and leave voice channel")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=True)
    async def stop_command(self, interaction: discord.Interaction) -> None:
        player = self.get_player(interaction.guild)
        await player.stop(disconnect=True)
        await interaction.response.send_message("⏹️ Player stopped and queue cleared.", delete_after=5)

    @app_commands.command(name="queue", description="Display current playback queue")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=False)
    async def queue_command(self, interaction: discord.Interaction) -> None:
        player = self.get_player(interaction.guild)
        tracks = player.queue.tracks
        current = player.queue.current

        if not current and not tracks:
            raise QueueEmptyError()

        PAGE_SIZE = 10
        total_pages = max(1, math.ceil(len(tracks) / PAGE_SIZE))
        pages: list[discord.Embed] = []

        for p in range(total_pages):
            embed = discord.Embed(
                title=f"📋 Playback Queue • Page {p + 1} of {total_pages}",
                color=discord.Color.purple(),
            )

            desc_lines: list[str] = []

            if current:
                curr_url = current.webpage_url if (current.webpage_url and current.webpage_url.startswith("http")) else ""
                clean_curr_title = " ".join(current.title.split())[:45]
                curr_title = f"[{clean_curr_title}]({curr_url})" if curr_url else f"**{clean_curr_title}**"
                desc_lines.append(
                    f"**🎶 Now Playing:**\n"
                    f"{curr_title} (`{current.formatted_duration}`) • {current.requester.mention}\n"
                )

            start_idx = p * PAGE_SIZE
            page_tracks = tracks[start_idx : start_idx + PAGE_SIZE]

            if not page_tracks:
                desc_lines.append("*No more tracks in queue.*")
            else:
                desc_lines.append(f"**Up Next ({len(tracks)} tracks):**")
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
                text=f"Loop: {player.queue.loop_mode.value} • Volume: {int(player.volume * 100)}%"
            )
            pages.append(embed)

        if len(pages) > 1:
            view = QueuePaginationView(pages, author=interaction.user)
            await interaction.response.send_message(embed=pages[0], view=view)
        else:
            await interaction.response.send_message(embed=pages[0])

    @app_commands.command(name="nowplaying", description="Show detailed card of current track with controls")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=False)
    async def nowplaying_command(self, interaction: discord.Interaction) -> None:
        player = self.get_player(interaction.guild)
        if not player.queue.current:
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
            return

        embed = player.build_now_playing_embed()
        from music.views import PlayerControlView
        view = PlayerControlView(player)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="loop", description="Toggle playback loop mode")
    @app_commands.describe(mode="Loop mode: off, track, queue")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=True)
    async def loop_command(
        self,
        interaction: discord.Interaction,
        mode: Literal["off", "track", "queue"] | None = None,
    ) -> None:
        player = self.get_player(interaction.guild)
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
            f"{current_mode.emoji} Loop mode: **{current_mode.value}**",
            delete_after=4,
        )

    @app_commands.command(name="shuffle", description="Shuffle tracks in queue")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=True)
    async def shuffle_command(self, interaction: discord.Interaction) -> None:
        player = self.get_player(interaction.guild)
        if len(player.queue) < 2:
            await interaction.response.send_message("❌ Not enough tracks in queue to shuffle.", ephemeral=True)
            return

        player.queue.shuffle()
        await interaction.response.send_message(f"🔀 Queue shuffled ({len(player.queue)} tracks).", delete_after=4)

    @app_commands.command(name="volume", description="Set music volume (0 - 100%)")
    @app_commands.describe(level="Volume level from 0 to 100")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=True)
    async def volume_command(self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]) -> None:
        player = self.get_player(interaction.guild)
        player.set_volume(level)
        await interaction.response.send_message(f"🔊 Volume: **{level}%**", delete_after=4)

    @app_commands.command(name="remove", description="Remove track from queue by position")
    @app_commands.describe(index="Track position in queue (/queue)")
    @ensure_voice_connection(check_bot_connected=True, require_same_channel=True)
    async def remove_command(self, interaction: discord.Interaction, index: int) -> None:
        player = self.get_player(interaction.guild)
        removed = player.queue.remove(index)
        if not removed:
            await interaction.response.send_message(f"❌ Track `#{index}` not found in queue.", ephemeral=True)
            return

        await interaction.response.send_message(f"🗑️ Removed `#{index}`: **{removed.title}**", delete_after=5)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        guild = member.guild
        voice_client: discord.VoiceClient | None = guild.voice_client

        if not voice_client or not voice_client.channel:
            return

        if member.id == self.bot.user.id and before.channel and not after.channel:
            logger.info(f"Bot was disconnected from voice channel in guild {guild.name}")
            player = self.players.get(guild.id)
            if player:
                await player.stop(disconnect=False)
            return

        non_bot_members = [m for m in voice_client.channel.members if not m.bot]
        if len(non_bot_members) == 0:
            logger.info(f"No users remaining in channel '{voice_client.channel.name}'. Starting leave timer...")
            await asyncio.sleep(30)
            if voice_client.is_connected() and len([m for m in voice_client.channel.members if not m.bot]) == 0:
                player = self.players.get(guild.id)
                if player:
                    if player.text_channel:
                        try:
                            await player.text_channel.send("👋 All users left the voice channel. Disconnected.")
                        except Exception:
                            pass
                    await player.stop(disconnect=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
