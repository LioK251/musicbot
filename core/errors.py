"""
Модуль пользовательских исключений и централизованной обработки ошибок.
"""

from __future__ import annotations

import logging
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("DiscordBot.Errors")


class MusicBotException(Exception):
    """Базовое исключение для музыкального бота."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotConnectedToVoice(MusicBotException):
    """Пользователь не находится в голосовом канале."""
    def __init__(self, message: str = "Вы должны находиться в голосовом канале для использования этой команды!"):
        super().__init__(message)


class BotNotConnectedToVoice(MusicBotException):
    """Бот не находится в голосовом канале."""
    def __init__(self, message: str = "Бот не подключен ни к одному голосовому каналу!"):
        super().__init__(message)


class DifferentVoiceChannel(MusicBotException):
    """Пользователь находится в другом голосовом канале, отличном от бота."""
    def __init__(self, message: str = "Вы должны находиться в том же голосовом канале, что и бот!"):
        super().__init__(message)


class MissingVoicePermissions(MusicBotException):
    """У бота нет прав для подключения или воспроизведения звука."""
    def __init__(self, message: str = "У бота нет прав на подключение (CONNECT) или разговор (SPEAK) в этом канале!"):
        super().__init__(message)


class TrackFetchError(MusicBotException):
    """Не удалось получить метаданные или аудиопоток трека."""
    def __init__(self, message: str = "Не удалось извлечь аудиопоток трека. Возможно, видео защищено авторскими правами или недоступно."):
        super().__init__(message)


class QueueEmptyError(MusicBotException):
    """Очередь воспроизведения пуста."""
    def __init__(self, message: str = "Очередь воспроизведения в данный момент пуста!"):
        super().__init__(message)


class SpotifyConfigError(MusicBotException):
    """Отсутствует или неверна конфигурация Spotify API."""
    def __init__(self, message: str = "Spotify API не настроен на стороне бота (требуются SPOTIFY_CLIENT_ID и SPOTIFY_CLIENT_SECRET в .env)."):
        super().__init__(message)


async def handle_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    """Централизованный обработчик ошибок для слэш-команд (App Commands)."""
    # Разворачиваем CommandInvokeError
    if isinstance(error, app_commands.CommandInvokeError):
        error = error.original

    # Пользовательские известные исключения
    if isinstance(error, MusicBotException):
        cmd = f"/{interaction.command.name}" if interaction.command else "unknown"
        user_info = f"{interaction.user} (ID: {interaction.user.id})"
        guild_info = f"{interaction.guild.name} (ID: {interaction.guild.id})" if interaction.guild else "DM"
        logger.warning(f"Ошибка в команде {cmd} от {user_info} на сервере {guild_info}: {error.message}")
        embed = discord.Embed(
            title="⚠️ Внимание",
            description=error.message,
            color=discord.Color.gold(),
        )
    elif isinstance(error, app_commands.MissingPermissions):
        missing = ", ".join(error.missing_permissions)
        embed = discord.Embed(
            title="⛔ Недостаточно прав",
            description=f"Вам не хватает следующих прав: **{missing}**",
            color=discord.Color.red(),
        )
    elif isinstance(error, app_commands.BotMissingPermissions):
        missing = ", ".join(error.missing_permissions)
        embed = discord.Embed(
            title="⛔ Боту не хватает прав",
            description=f"Боту необходимы права: **{missing}**",
            color=discord.Color.red(),
        )
    elif isinstance(error, app_commands.CommandOnCooldown):
        embed = discord.Embed(
            title="⏳ Кулдаун команды",
            description=f"Пожалуйста, подождите ещё **{error.retry_after:.1f} сек.** перед повторным вызовом.",
            color=discord.Color.orange(),
        )
    else:
        logger.error(f"Необработанная ошибка в команде /{interaction.command.name if interaction.command else 'unknown'}: {error}", exc_info=True)
        embed = discord.Embed(
            title="❌ Произошла ошибка",
            description=f"Во время выполнения команды произошла непредвиденная ошибка:\n`{error}`",
            color=discord.Color.red(),
        )

    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as send_err:
        logger.error(f"Не удалось отправить сообщение об ошибке пользователю: {send_err}")
