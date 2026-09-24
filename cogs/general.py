"""
Модуль общих команд бота (/help, /ping, /info).
"""

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
    """Общие команды и справка."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.time()

    @app_commands.command(name="ping", description="Проверить задержку (пинг) бота")
    async def ping_command(self, interaction: discord.Interaction) -> None:
        """Показывает задержку WebSocket и API."""
        start = time.perf_counter()
        await interaction.response.defer()
        end = time.perf_counter()

        ws_ping = round(self.bot.latency * 1000)
        api_ping = round((end - start) * 1000)

        embed = discord.Embed(
            title="🏓 Понг!",
            color=discord.Color.green(),
        )
        embed.add_field(name="🌐 WebSocket Gateway", value=f"`{ws_ping} мс`", inline=True)
        embed.add_field(name="⚡ REST API Roundtrip", value=f"`{api_ping} мс`", inline=True)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="help", description="Справка по всем командам и возможностям бота")
    async def help_command(self, interaction: discord.Interaction) -> None:
        """Интерактивное руководство по использованию бота."""
        embed = discord.Embed(
            title="📖 Справка и руководство по боту",
            description=(
                "Многофункциональный Discord-бот с продвинутой музыкальной системой "
                "и автоматической конвертацией TikTok ссылок.\n\n"
                "**Доступные команды:**"
            ),
            color=discord.Color.from_rgb(138, 43, 226),
        )

        music_cmds = (
            "`/play <запрос/ссылка>` — Воспроизвести трек (YouTube, SoundCloud, Spotify) с живым автодополнением\n"
            "`/search <запрос>` — Поиск треков с интерактивным выпадающим списком Топ-5\n"
            "`/pause` — Приостановить воспроизведение\n"
            "`/resume` — Возобновить воспроизведение\n"
            "`/skip` — Пропустить текущий трек\n"
            "`/stop` — Остановить плеер, очистить очередь и выйти из канала\n"
            "`/queue` — Показать список очереди с пагинацией\n"
            "`/nowplaying` — Карточка текущего трека с интерактивными кнопками\n"
            "`/loop [off|track|queue]` — Переключение режима зацикливания\n"
            "`/shuffle` — Перемешать очередь в случайном порядке\n"
            "`/volume <0-100>` — Настройка громкости воспроизведения\n"
            "`/remove <номер>` — Удалить трек из очереди по номеру"
        )
        embed.add_field(name="🎵 Музыкальный плеер", value=music_cmds, inline=False)

        tiktok_cmds = (
            "• **Автоперехват**: бот автоматически распознает ссылки `tiktok.com` и `vm.tiktok.com` "
            "в чате и заменяет их на зеркало с нативным видеоплеером Discord!\n"
            "• `/tiktok <ссылка>` — Ручная конвертация ссылки."
        )
        embed.add_field(name="📱 TikTok Автозамена", value=tiktok_cmds, inline=False)

        ui_info = (
            "Под сообщением играющего трека закреплены интерактивные кнопки:\n"
            "• ⏯️ — Пауза / Возобновить\n"
            "• ⏭️ — Пропустить трек\n"
            "• 🔁 — Переключение режима цикла (Выкл -> Трек -> Очередь)\n"
            "• ⏹️ — Остановка и выход из канала\n"
            "*Кнопки доступны только участникам текущего голосового канала!*"
        )
        embed.add_field(name="🎛️ Интерактивный UI", value=ui_info, inline=False)

        embed.set_footer(text="Создано на discord.py 2.x • Введите / перед командой для автозаполнения")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="info", description="Техническая информация о системе и боте")
    async def info_command(self, interaction: discord.Interaction) -> None:
        """Выводит информацию о версиях и потреблении ресурсов."""
        uptime_sec = int(time.time() - self.start_time)
        m, s = divmod(uptime_sec, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)
        uptime_str = f"{d}д {h}ч {m}м {s}с" if d else f"{h}ч {m}м {s}с"

        ffmpeg_path = shutil.which("ffmpeg") or "Не найден в PATH"

        embed = discord.Embed(
            title="ℹ️ Информация о боте",
            color=discord.Color.blue(),
        )
        embed.add_field(name="🐍 Python", value=f"`{platform.python_version()}`", inline=True)
        embed.add_field(name="🤖 discord.py", value=f"`{discord.__version__}`", inline=True)
        embed.add_field(name="⏱️ Uptime", value=f"`{uptime_str}`", inline=True)

        embed.add_field(name="🎬 FFmpeg", value=f"`{ffmpeg_path}`", inline=False)
        embed.add_field(name="🏰 Серверов", value=f"`{len(self.bot.guilds)}`", inline=True)
        embed.add_field(name="🔊 Голосовых подключений", value=f"`{len(self.bot.voice_clients)}`", inline=True)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GeneralCog(bot))
