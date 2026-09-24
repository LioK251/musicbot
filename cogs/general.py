from __future__ import annotations

import logging
import platform
import shutil
import time
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("DiscordBot.General")


class GeneralCog(commands.Cog, name="General"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.time()

    @app_commands.command(name="ping", description="Check bot latency")
    async def ping_command(self, interaction: discord.Interaction) -> None:
        start = time.perf_counter()
        await interaction.response.defer()
        end = time.perf_counter()

        ws_ping = round(self.bot.latency * 1000)
        api_ping = round((end - start) * 1000)

        embed = discord.Embed(
            title="🏓 Pong!",
            color=discord.Color.green(),
        )
        embed.add_field(name="🌐 WebSocket Gateway", value=f"`{ws_ping} ms`", inline=True)
        embed.add_field(name="⚡ REST API Roundtrip", value=f"`{api_ping} ms`", inline=True)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="help", description="Show bot commands and guide")
    async def help_command(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="📖 Bot Help & Commands",
            description=(
                "Feature-rich Discord bot with an advanced music player "
                "and automatic TikTok video embedding.\n\n"
                "**Available Commands:**"
            ),
            color=discord.Color.from_rgb(138, 43, 226),
        )

        music_cmds = (
            "`/play <query/url>` — Play audio (YouTube, SoundCloud, Spotify) with live autocomplete\n"
            "`/search <query>` — Search top 5 tracks with an interactive dropdown menu\n"
            "`/pause` — Pause playback\n"
            "`/resume` — Resume playback\n"
            "`/skip` — Skip current track\n"
            "`/stop` — Stop playback, clear queue, and leave voice channel\n"
            "`/queue` — Display playback queue with pagination\n"
            "`/nowplaying` — Show currently playing track card with interactive buttons\n"
            "`/loop [off|track|queue]` — Switch loop mode\n"
            "`/shuffle` — Shuffle tracks in queue\n"
            "`/volume <0-100>` — Adjust playback volume\n"
            "`/remove <index>` — Remove track from queue by position"
        )
        embed.add_field(name="🎵 Music Player", value=music_cmds, inline=False)

        tiktok_cmds = (
            "• **Auto-embed**: Automatically detects `tiktok.com` and `vm.tiktok.com` "
            "links in chat and sends the video file or embed mirror directly to chat!\n"
            "• `/tiktok <url>` — Manually download and send TikTok video."
        )
        embed.add_field(name="📱 TikTok Integration", value=tiktok_cmds, inline=False)

        ui_info = (
            "Interactive buttons attached under the Now Playing message:\n"
            "• ⏯️ — Pause / Resume\n"
            "• ⏭️ — Skip track\n"
            "• 🔁 — Cycle loop mode (Off -> Track -> Queue)\n"
            "• ⏹️ — Stop playback and leave channel\n"
            "*Buttons are available to members in the same voice channel!*"
        )
        embed.add_field(name="🎛️ Interactive Controls", value=ui_info, inline=False)

        embed.set_footer(text="Powered by discord.py 2.x • Type / for command autocomplete")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="info", description="Display system and bot technical information")
    async def info_command(self, interaction: discord.Interaction) -> None:
        uptime_sec = int(time.time() - self.start_time)
        m, s = divmod(uptime_sec, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)
        uptime_str = f"{d}d {h}h {m}m {s}s" if d else f"{h}h {m}m {s}s"

        ffmpeg_path = shutil.which("ffmpeg") or "Not found in PATH"

        embed = discord.Embed(
            title="ℹ️ Bot Information",
            color=discord.Color.blue(),
        )
        embed.add_field(name="🐍 Python", value=f"`{platform.python_version()}`", inline=True)
        embed.add_field(name="🤖 discord.py", value=f"`{discord.__version__}`", inline=True)
        embed.add_field(name="⏱️ Uptime", value=f"`{uptime_str}`", inline=True)

        embed.add_field(name="🎬 FFmpeg", value=f"`{ffmpeg_path}`", inline=False)
        embed.add_field(name="🏰 Guilds", value=f"`{len(self.bot.guilds)}`", inline=True)
        embed.add_field(name="🔊 Voice Connections", value=f"`{len(self.bot.voice_clients)}`", inline=True)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GeneralCog(bot))
