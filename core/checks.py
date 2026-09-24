"""
Модуль проверок прав (Permissions) и состояния голосовых каналов (Voice State).
"""

from __future__ import annotations

import discord
from discord import app_commands
from core.errors import (
    NotConnectedToVoice,
    BotNotConnectedToVoice,
    DifferentVoiceChannel,
    MissingVoicePermissions,
)


def ensure_voice_connection(check_bot_connected: bool = False, require_same_channel: bool = True):
    """
    Декоратор проверки голосового состояния пользователя и бота для слэш-команд:
    - Пользователь обязан быть в голосовом канале.
    - Проверка прав бота (CONNECT, SPEAK).
    - Если бот уже в войсе, пользователь должен быть в том же канале (если require_same_channel=True).
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            await interaction.response.send_message("❌ Эта команда доступна только на сервере!", ephemeral=True)
            return False

        # 1. Проверяем, находится ли пользователь в войсе
        user: discord.Member = interaction.user  # type: ignore
        if not user.voice or not user.voice.channel:
            raise NotConnectedToVoice()

        user_channel = user.voice.channel
        bot_voice: discord.VoiceClient | None = interaction.guild.voice_client

        # 2. Если требуется, чтобы бот уже был подключен
        if check_bot_connected and not bot_voice:
            raise BotNotConnectedToVoice()

        # 3. Если бот уже в голосовом канале, проверяем совпадение каналов
        if bot_voice and require_same_channel:
            if bot_voice.channel.id != user_channel.id:
                raise DifferentVoiceChannel(
                    f"Вы должны находиться в канале **{bot_voice.channel.name}**, где сейчас играет бот!"
                )

        # 4. Проверяем права бота на подключение и воспроизведение в целевом канале
        bot_member = interaction.guild.me
        permissions = user_channel.permissions_for(bot_member)
        if not permissions.connect or not permissions.speak:
            raise MissingVoicePermissions()

        return True

    return app_commands.check(predicate)


def is_user_in_same_voice(interaction: discord.Interaction) -> bool:
    """
    Вспомогательная функция для UI компонентов:
    Проверяет, находится ли пользователь в том же голосовом канале, что и бот.
    """
    if not interaction.guild:
        return False

    bot_voice: discord.VoiceClient | None = interaction.guild.voice_client
    if not bot_voice or not bot_voice.channel:
        return False

    user: discord.Member = interaction.user  # type: ignore
    if not user.voice or not user.voice.channel:
        return False

    return user.voice.channel.id == bot_voice.channel.id
